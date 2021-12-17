from aiohttp import web
from aiohttp.web_request import Request
from decouple import config
from eth_account import Account
from services.external_api.base_client import RetryConfig
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from web3 import Web3

from fluence.contracts.fluence import StarkFluence, LimitOrder, EtherFluence, ContractKind
from fluence.contracts.forwarder import Forwarder
from fluence.contracts.utils import parse_int

routes = web.RouteTableDef()


@routes.get('/api/v1/contracts')
async def get_contracts():
    return web.json_response({
        'fluence': config('L1_CONTRACT_ADDRESS'),
        'forwarder': config('L1_VERIFYING_CONTRACT'),
    })


@routes.post('/api/v1/contracts')
async def register_contract(request: Request):
    data = await request.json()
    req, signature = request.app['forwarder'].forward(
        *request.app['ether_fluence'].registerContract(
            data['contract'],
            ContractKind.ERC721,
            parse_int(data['minter'])))

    return web.json_response({
        'req': {k: str(v) for k, v in req.items()},
        'signature': signature,
    })


@routes.get('/api/v1/clients')
async def get_client(request: Request):
    stark_key = await request.app['fluence'].get_client(request.query['address'])

    return web.json_response({'stark_key': stark_key})


@routes.post('/api/v1/clients')
async def register_client(request: Request):
    data = await request.json()
    tx = await request.app['fluence'].register_client(
        data['stark_key'],
        data['address'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/api/v1/balance')
async def get_balance(request: Request):
    balance = await request.app['fluence'].get_balance(
        request.query['user'],
        request.query['contract'])

    return web.json_response({'balance': balance})


@routes.get('/api/v1/owner')
async def get_owner(request: Request):
    owner = await request.app['fluence'].get_owner(
        request.query['token_id'],
        request.query['contract'])

    return web.json_response({'owner': owner})


@routes.post('/api/v1/mint')
async def mint(request: Request):
    data = await request.json()
    tx = await request.app['fluence'].mint(
        data['user'],
        data['amount_or_token_id'],
        data['contract'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.post('/api/v1/withdraw')
async def withdraw(request: Request):
    data = await request.json()
    tx = await request.app['fluence'].withdraw(
        data['user'],
        data['amount_or_token_id'],
        data['contract'],
        data['address'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/api/v1/orders/{id}')
async def get_order(request: Request):
    limit_order = await request.app['fluence'].get_order(request.match_info['id'])

    return web.json_response(limit_order._asdict())


@routes.put('/api/v1/orders/{id}')
async def create_order(request: Request):
    data = await request.json()
    tx = await request.app['fluence'].create_order(
        request.match_info['id'],
        LimitOrder(**data, state=0),
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.delete('/api/v1/orders/{id}')
async def cancel_order(request: Request):
    tx = await request.app['fluence'].cancel_order(
        request.match_info['id'],
        request.query['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.post('/api/v1/orders/{id}')
async def fulfill_order(request: Request):
    data = await request.json()
    tx = await request.app['fluence'].fulfill_order(
        request.match_info['id'],
        data['user'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/api/v1/tx/{hash}/_status')
async def get_tx_status(request: Request):
    status = await request.app['feeder_gateway'].get_transaction_status(request.match_info['hash'])

    return web.json_response(status)


def serve():
    app = web.Application()
    w3 = Web3()
    app['ether_fluence'] = EtherFluence(config('L2_CONTRACT_ADDRESS', cast=parse_int), w3)
    app['forwarder'] = Forwarder(
        'FluenceForwarder',
        '0.1.0',
        config('L1_VERIFYING_CONTRACT'),
        config('L1_CONTRACT_ADDRESS'),
        Account.from_key(config('L1_MINT_PRIVATE_KEY')),
        w3)
    app['feeder_gateway'] = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    app['fluence'] = StarkFluence(
        config('L2_CONTRACT_ADDRESS', cast=parse_int),
        app['feeder_gateway'],
        GatewayClient(
            url=config('GATEWAY_URL'),
            retry_config=RetryConfig(n_retries=1)))
    app.add_routes(routes)

    web.run_app(app, port=4000)
