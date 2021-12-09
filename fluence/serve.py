import functools
from typing import Union

from aiohttp import web
from aiohttp.web_request import Request
from decouple import config
from services.external_api.base_client import RetryConfig
from starkware.crypto.signature.fast_pedersen_hash import pedersen_hash
from starkware.crypto.signature.signature import sign
from starkware.starknet.compiler.compile import get_selector_from_name
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from starkware.starknet.services.api.gateway.transaction import InvokeFunction
from web3 import Web3

routes = web.RouteTableDef()


def integer(x: Union[int, str]) -> int:
    if type(x) is int:
        return x

    if x.startswith('0x'):
        return int(x, 16)

    return int(x)


ABI = '[{"inputs":[{"internalType":"address","name":"to","type":"address"},' \
      '{"internalType":"uint256","name":"tokenId","type":"uint256"}],' \
      '"name":"mint","outputs":[],"stateMutability":"nonpayable","type":"function"}]'


@routes.post('/api/v1/mint')
async def mint(request: Request):
    data = await request.json()
    user = data['user']
    amount_or_token_id = integer(data['amount_or_token_id'])
    contract = data['contract']
    token = data['token']
    if token in [0, 1]:
        w3 = Web3()
        contract = w3.eth.contract(contract, abi=ABI)
        fn = contract.functions['mint'](user, amount_or_token_id)
        account = w3.eth.account.from_key(config('L1_MINT_PRIVATE_KEY'))
        tx = fn.buildTransaction({
            'gas': 200000,
            'gasPrice': int(1.05 * w3.eth.gas_price),
            'nonce': w3.eth.get_transaction_count(account.address),
        })
        signed = w3.eth.account.sign_transaction(tx, account.key)
        txn = w3.eth.send_raw_transaction(signed.rawTransaction)

        return web.json_response({'transaction_hash': w3.toHex(txn)})

    if token in [2]:
        user = integer(user)
        contract = integer(contract)
        message_hash = functools.reduce(
            lambda x, y: pedersen_hash(y, x),
            reversed([user, amount_or_token_id, contract]), 0)
        tx = InvokeFunction(
            contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
            entry_point_selector=get_selector_from_name('mint'),
            calldata=[user, amount_or_token_id, contract],
            signature=list(sign(msg_hash=message_hash, priv_key=config('L2_MINT_PRIVATE_KEY', cast=integer))))

        gateway_client = GatewayClient(
            url=config('GATEWAY_URL'),
            retry_config=RetryConfig(n_retries=1))
        gateway_response = await gateway_client.add_transaction(tx)

        return web.json_response({'transaction_hash': gateway_response['transaction_hash']})

@routes.post('/api/v1/register/client')
async def register_client(request: Request):
    signature = list(map(integer, request.query['signature'].split(',')))
    data = await request.json()
    public_key = integer(data['public_key'])
    address = integer(data['address'])
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('register_client'),
        calldata=[public_key, address],
        signature=signature)

    gateway_client = GatewayClient(
        url=config('GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await gateway_client.add_transaction(tx)
    return web.json_response({'transaction_hash': gateway_response['transaction_hash']})


@routes.get('/api/v1/get/client')
async def get_client(request: Request):
    address = integer(request.query['address'])
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('get_client'),
        calldata=[address],
        signature=[])
    feeder_client = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await feeder_client.call_contract(tx)
    return web.json_response({'public_key': gateway_response['result'][0]})


@routes.get('/api/v1/balance')
async def get_balance(request: Request):
    user = integer(request.query['user'])
    contract = integer(request.query['contract'])
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('get_balance'),
        calldata=[user, contract],
        signature=[])

    feeder_client = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await feeder_client.call_contract(tx)

    return web.json_response({'balance': int(gateway_response['result'][0], 16)})


@routes.get('/api/v1/owner')
async def get_owner(request: Request):
    token_id = integer(request.query['token_id'])
    contract = integer(request.query['contract'])
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('get_owner'),
        calldata=[token_id, contract],
        signature=[])

    feeder_client = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await feeder_client.call_contract(tx)

    return web.json_response({'owner': gateway_response['result'][0]})


@routes.post('/api/v1/withdraw')
async def withdraw(request: Request):
    signature = list(map(integer, request.query['signature'].split(',')))
    data = await request.json()
    user = integer(data['user'])
    amount_or_token_id = integer(data['amount_or_token_id'])
    contract = integer(data['contract'])
    address = integer(data['address'])
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('withdraw'),
        calldata=[user, amount_or_token_id, contract, address],
        signature=signature)

    gateway_client = GatewayClient(
        url=config('GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await gateway_client.add_transaction(tx)

    return web.json_response({'transaction_hash': gateway_response['transaction_hash']})


@routes.get('/api/v1/orders/{id}')
async def get_order(request: Request):
    oid = integer(request.match_info['id'])
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('get_order'),
        calldata=[oid],
        signature=[])

    feeder_client = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await feeder_client.call_contract(tx)
    result = gateway_response['result']

    return web.json_response({
        'user': result[0],
        'bid': integer(result[1]),
        'base_contract': result[2],
        'base_token_id': integer(result[3]),
        'quote_contract': result[4],
        'quote_amount': integer(result[5]),
        'state': integer(result[6]),
    })


@routes.put('/api/v1/orders/{id}')
async def create_order(request: Request):
    signature = list(map(integer, request.query['signature'].split(',')))
    oid = integer(request.match_info['id'])
    data = await request.json()
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('create_order'),
        calldata=[
            oid,
            integer(data['user']),
            integer(data['bid']),
            integer(data['base_contract']),
            integer(data['base_token_id']),
            integer(data['quote_contract']),
            integer(data['quote_amount']),
        ],
        signature=signature)

    gateway_client = GatewayClient(
        url=config('GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await gateway_client.add_transaction(tx)

    return web.json_response({'transaction_hash': gateway_response['transaction_hash']})


@routes.delete('/api/v1/orders/{id}')
async def cancel_order(request: Request):
    signature = list(map(integer, request.query['signature'].split(',')))
    oid = integer(request.match_info['id'])
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('cancel_order'),
        calldata=[oid],
        signature=signature)

    gateway_client = GatewayClient(
        url=config('GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await gateway_client.add_transaction(tx)

    return web.json_response({'transaction_hash': gateway_response['transaction_hash']})


@routes.post('/api/v1/orders/{id}')
async def fulfill_order(request: Request):
    signature = list(map(integer, request.query['signature'].split(',')))
    oid = integer(request.match_info['id'])
    data = await request.json()
    tx = InvokeFunction(
        contract_address=config('L2_CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('fulfill_order'),
        calldata=[oid, integer(data['user'])],
        signature=signature)

    gateway_client = GatewayClient(
        url=config('GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await gateway_client.add_transaction(tx)

    return web.json_response({'transaction_hash': gateway_response['transaction_hash']})


def serve():
    app = web.Application()
    app.add_routes(routes)

    web.run_app(app, port=4000)
