from collections import namedtuple
from enum import IntEnum

import pkg_resources
from eth_typing import ChecksumAddress, HexStr
from starkware.starknet.public.abi import get_selector_from_name
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from starkware.starknet.services.api.gateway.transaction import InvokeFunction
from web3 import Web3

from fluence.utils import parse_int

LimitOrder = namedtuple('LimitOrder', [
    'user',
    'bid',
    'base_contract',
    'base_token_id',
    'quote_contract',
    'quote_amount',
    'state',
])


class ContractKind(IntEnum):
    ERC20 = 1
    ERC721 = 2


class EtherFluence:
    def __init__(self, stark_address: int, w3: Web3):
        self._stark_address = stark_address
        self._contract = w3.eth.contract(
            abi=pkg_resources.resource_string(__name__, 'abi/Fluence.abi').decode())

    def register_contract(
            self,
            contract: ChecksumAddress,
            kind: ContractKind,
            minter: int) -> tuple[HexStr, int]:
        return self._contract.encodeABI('registerContract', [
            self._stark_address,
            contract,
            kind,
            minter,
        ]), 100000


class StarkFluence:
    def __init__(self, stark_address: int, feeder: FeederGatewayClient, gateway: GatewayClient):
        self._address = stark_address
        self._feeder = feeder
        self._gateway = gateway

    async def get_client(self, address):
        stark_key, = await self._estimate('get_client', [address])

        return stark_key

    def register_client(self, stark_key, address, nonce, signature):
        return self._transact('register_client', [stark_key, address, nonce], signature)

    async def get_balance(self, user, contract):
        balance, = await self._estimate('get_balance', [user, contract])

        return balance

    async def get_owner(self, token_id, contract):
        owner, = await self._estimate('get_owner', [token_id, contract])

        return owner

    def mint(self, user, amount_or_token_id, contract, nonce, signature):
        return self._transact('mint', [user, amount_or_token_id, contract, nonce], signature)

    def withdraw(self, user, amount_or_token_id, contract, address, nonce, signature):
        return self._transact('withdraw', [user, amount_or_token_id, contract, address, nonce], signature)

    def transfer(self, from_, to_, amount_or_token_id, contract, nonce, signature):
        return self._transact('transfer', [from_, to_, amount_or_token_id, contract, nonce], signature)

    async def get_order(self, order_id):
        result = await self._estimate('get_order', [order_id])

        return LimitOrder._make(result)

    def create_order(self, order_id, limit_order: LimitOrder, signature):
        return self._transact('create_order', [order_id, *limit_order][:-1], signature)

    def cancel_order(self, order_id, nonce, signature):
        return self._transact('cancel_order', [order_id, nonce], signature)

    def fulfill_order(self, order_id, user, nonce, signature):
        return self._transact('fulfill_order', [order_id, user, nonce], signature)

    async def _estimate(self, name: str, calldata: list):
        response = await self._feeder.call_contract(self._invoke(name, calldata))

        return map(parse_int, response['result'])

    async def _transact(self, name: str, calldata: list, signature):
        response = await self._gateway.add_transaction(self._invoke(name, calldata, list(map(parse_int, signature))))

        return response['transaction_hash']

    def _invoke(self, name, calldata, signature=None):
        return InvokeFunction(
            contract_address=self._address,
            entry_point_selector=get_selector_from_name(name),
            calldata=list(map(parse_int, calldata)),
            signature=signature or [])
