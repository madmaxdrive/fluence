from typing import Union

from aiohttp import web
from aiohttp.web_request import Request
from decouple import config
from services.external_api.base_client import RetryConfig
from starkware.starknet.compiler.compile import get_selector_from_name
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from starkware.starknet.services.api.gateway.transaction import InvokeFunction
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starkware_utils.error_handling import StarkErrorCode

routes = web.RouteTableDef()


def integer(x: Union[int, str]) -> int:
    if type(x) is int:
        return x

    if x.startswith('0x'):
        return int(x, 16)

    return int(x)


@routes.get('/api/v1/balance')
async def get_balance(request: Request):
    user = integer(request.query['user'])
    contract = integer(request.query['contract'])
    tx = InvokeFunction(
        contract_address=config('CONTRACT_ADDRESS', cast=integer),
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
        contract_address=config('CONTRACT_ADDRESS', cast=integer),
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
    data = await request.json()
    user = integer(data['user'])
    amount_or_token_id = integer(data['amount_or_token_id'])
    contract = integer(data['contract'])
    address = integer(data['address'])
    tx = InvokeFunction(
        contract_address=config('CONTRACT_ADDRESS', cast=integer),
        entry_point_selector=get_selector_from_name('withdraw'),
        calldata=[user, amount_or_token_id, contract, address],
        signature=[])

    gateway_client = GatewayClient(
        url=config('GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await gateway_client.add_transaction(tx)

    return web.json_response({'transaction_hash': gateway_response['transaction_hash']})


def serve():
    app = web.Application()
    app.add_routes(routes)

    web.run_app(app, port=4000)
