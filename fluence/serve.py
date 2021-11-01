from aiohttp import web
from aiohttp.web_request import Request
from decouple import config
from services.external_api.base_client import RetryConfig
from starkware.starknet.compiler.compile import get_selector_from_name
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from starkware.starknet.services.api.gateway.transaction import InvokeFunction
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starkware_utils.error_handling import StarkErrorCode


async def get_transaction(request: Request):
    hash = request.match_info.get('hash')

    feeder_client = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    status = await feeder_client.get_transaction_status(hash)

    return web.json_response(status)


async def get_balance(request: Request):
    user = int(request.match_info.get('user'))
    tx = InvokeFunction(
        contract_address=config('CONTRACT_ADDRESS', cast=lambda x: int(x, 16) if x.startswith('0x') else int(value)),
        entry_point_selector=get_selector_from_name('get_balance'),
        calldata=[user],
        signature=[])

    feeder_client = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await feeder_client.call_contract(tx)

    return web.json_response({'balance': int(gateway_response['result'][0], 16)})


async def post_balance(request: Request):
    data = await request.post()
    user = int(request.match_info.get('user'))
    amount = int(data['amount'])
    tx = InvokeFunction(
        contract_address=config('CONTRACT_ADDRESS', cast=lambda x: int(x, 16) if x.startswith('0x') else int(value)),
        entry_point_selector=get_selector_from_name('inc_balance' if amount > 0 else 'withdraw'),
        calldata=[user, abs(amount)],
        signature=[])

    gateway_client = GatewayClient(
        url=config('GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    gateway_response = await gateway_client.add_transaction(tx)
    assert gateway_response["code"] == StarkErrorCode.TRANSACTION_RECEIVED.name, \
        f"Failed to send transaction. Response: {gateway_response}."

    return web.json_response({'transaction_hash': gateway_response['transaction_hash']})


def serve():
    app = web.Application()
    app.add_routes([
        web.get('/tx/{hash}', get_transaction),
        web.get('/{user}/balance', get_balance),
        web.post('/{user}/balance', post_balance),
    ])

    web.run_app(app)
