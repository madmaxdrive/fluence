from aiohttp import web
from aiohttp.web_request import Request
from decouple import config
from eth_account import Account
from services.external_api.base_client import RetryConfig
from sqlalchemy import select, null
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import functions
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from web3 import Web3

from fluence.contracts.fluence import StarkFluence, LimitOrder, EtherFluence, ContractKind
from fluence.contracts.forwarder import Forwarder
from fluence.utils import parse_int

routes = web.RouteTableDef()


@routes.get('/contracts')
async def get_contracts(request: Request):
    return web.json_response({
        'fluence': request.config_dict['forwarder'].to_address,
        'forwarder': request.config_dict['forwarder'].address,
    })


@routes.post('/contracts')
async def register_contract(request: Request):
    data = await request.json()
    req, signature = request.config_dict['forwarder'].forward(
        *request.config_dict['ether_fluence'].register_contract(
            data['contract'],
            ContractKind.ERC721,
            parse_int(data['minter'])))

    return web.json_response({
        'req': {k: str(v) for k, v in req.items()},
        'signature': signature,
    })


@routes.get('/clients')
async def get_client(request: Request):
    stark_key = await request.config_dict['fluence']. \
        get_client(request.query['address'])

    return web.json_response({'stark_key': str(stark_key)})


@routes.post('/clients')
async def register_client(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].register_client(
        data['stark_key'],
        data['address'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/balance')
async def get_balance(request: Request):
    balance = await request.config_dict['fluence'].get_balance(
        request.query['user'],
        request.query['contract'])

    return web.json_response({'balance': str(balance)})


@routes.get('/owner')
async def get_owner(request: Request):
    owner = await request.config_dict['fluence'].get_owner(
        request.query['token_id'],
        request.query['contract'])

    return web.json_response({'owner': str(owner)})


@routes.post('/mint')
async def mint(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].mint(
        data['user'],
        data['amount_or_token_id'],
        data['contract'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.post('/withdraw')
async def withdraw(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].withdraw(
        data['user'],
        data['amount_or_token_id'],
        data['contract'],
        data['address'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/orders')
async def get_orders(request: Request):
    from fluence.models import LimitOrder, LimitOrderSchema, State, Account, Token, TokenContract

    page = parse_int(request.query.get('page', '1'))
    size = parse_int(request.query.get('size', '100'))
    user = request.query.get('user')
    collection = request.query.get('collection')
    side = request.query.get('side')
    state = request.query.get('state')

    async with request.config_dict['async_session']() as session:
        def augment(stmt):
            if user:
                stmt = stmt.join(LimitOrder.user). \
                    where(Account.address == user)
            if collection:
                stmt = stmt.join(LimitOrder.token). \
                    join(Token.contract). \
                    where(TokenContract.address == collection)
            if side in ['ask', 'bid']:
                stmt = stmt.where(LimitOrder.bid == (side == 'bid'))
            if state:
                stmt = stmt.where(LimitOrder.fulfilled == [null(), True, False][State(parse_int(state))])

            return stmt

        query = augment(select(LimitOrder)).limit(size).offset(size * (page - 1))
        count = augment(select(functions.count()).select_from(LimitOrder))

        return web.json_response({
            'data': list(map(
                LimitOrderSchema().dump,
                (await session.execute(
                    query.options(
                        selectinload(LimitOrder.user),
                        selectinload(LimitOrder.token).selectinload(Token.contract),
                        selectinload(LimitOrder.quote_contract)))).scalars())),
            'total': (await session.execute(count)).scalar_one(),
        })


@routes.get('/orders/{id}')
async def get_order(request: Request):
    limit_order = await request.config_dict['fluence']. \
        get_order(request.match_info['id'])

    return web.json_response(limit_order._asdict())


@routes.put('/orders/{id}')
async def create_order(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].create_order(
        request.match_info['id'],
        LimitOrder(**data, state=0),
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.delete('/orders/{id}')
async def cancel_order(request: Request):
    tx = await request.config_dict['fluence'].cancel_order(
        request.match_info['id'],
        request.query['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.post('/orders/{id}')
async def fulfill_order(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].fulfill_order(
        request.match_info['id'],
        data['user'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/tx/{hash}/_status')
async def get_tx_status(request: Request):
    status = await request.config_dict['feeder_gateway']. \
        get_transaction_status(request.match_info['hash'])

    return web.json_response(status)


def serve():
    from .services import async_session

    app = web.Application()
    w3 = Web3()
    app['ether_fluence'] = EtherFluence(
        config('STARK_FLUENCE_CONTRACT_ADDRESS', cast=parse_int), w3)
    app['forwarder'] = Forwarder(
        'FluenceForwarder',
        '0.1.0',
        config('ETHER_FORWARDER_CONTRACT_ADDRESS'),
        config('ETHER_FLUENCE_CONTRACT_ADDRESS'),
        Account.from_key(config('ETHER_PRIVATE_KEY')),
        w3)
    app['feeder_gateway'] = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    app['fluence'] = StarkFluence(
        config('STARK_FLUENCE_CONTRACT_ADDRESS', cast=parse_int),
        app['feeder_gateway'],
        GatewayClient(
            url=config('GATEWAY_URL'),
            retry_config=RetryConfig(n_retries=1)))
    app['async_session'] = async_session

    v1 = web.Application()
    v1.add_routes(routes)
    app.add_subapp('/api/v1', v1)

    web.run_app(app, port=4000)
