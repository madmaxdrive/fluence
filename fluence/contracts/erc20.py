import pkg_resources
from eth_typing import ChecksumAddress
from web3 import Web3


class ERC20:
    def __init__(self, address: ChecksumAddress, w3: Web3):
        self.contract = w3.eth.contract(
            address,
            abi=pkg_resources.resource_string(__name__, 'abi/ERC20.abi').decode())

    def identify(self) -> tuple[str, str, int]:
        return (
            self.contract.functions['name']().call(),
            self.contract.functions['symbol']().call(),
            self.contract.functions['decimals']().call())
