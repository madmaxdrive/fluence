from uuid import uuid4

import pkg_resources
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from py_eth_sig_utils.signing import v_r_s_to_signature, sign_typed_data
from web3 import Web3

EIP712Domain = [
    {'name': 'name', 'type': 'string'},
    {'name': 'version', 'type': 'string'},
    {'name': 'chainId', 'type': 'uint256'},
    {'name': 'verifyingContract', 'type': 'address'},
]

types = {
    'EIP712Domain': EIP712Domain,
    'ForwardRequest': [
        {'name': 'from', 'type': 'address'},
        {'name': 'to', 'type': 'address'},
        {'name': 'value', 'type': 'uint256'},
        {'name': 'gas', 'type': 'uint256'},
        {'name': 'batch', 'type': 'uint256'},
        {'name': 'nonce', 'type': 'uint256'},
        {'name': 'data', 'type': 'bytes'},
    ],
}


class Forwarder:
    def __init__(
            self,
            name: str,
            version: str,
            contract_address: ChecksumAddress,
            to_address: ChecksumAddress,
            account: LocalAccount,
            w3: Web3):
        self._account = account
        self._to_address = to_address
        self._contract = w3.eth.contract(
            contract_address,
            abi=pkg_resources.resource_string(__name__, 'abi/FluenceForwarder.abi').decode())
        self._domain = {
            'name': name,
            'version': version,
            'chainId': w3.eth.chain_id,
            'verifyingContract': contract_address,
        }

    @property
    def address(self):
        return self._contract.address

    @property
    def to_address(self):
        return self._to_address

    def forward(self, calldata, gas: int):
        batch = uuid4().int
        nonce = self._contract.functions['getNonce'](self._account.address, batch).call()
        req = {
            'from': self._account.address,
            'to': self._to_address,
            'value': 0,
            'gas': gas,
            'batch': batch,
            'nonce': nonce,
            'data': calldata,
        }
        data = {
            'types': types,
            'domain': self._domain,
            'primaryType': 'ForwardRequest',
            'message': req,
        }
        signature = v_r_s_to_signature(*sign_typed_data(data, self._account.key))

        return req, Web3.toHex(signature)
