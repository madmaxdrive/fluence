from typing import Union

from eth_typing import ChecksumAddress
from web3 import Web3


def parse_int(n: Union[int, str]):
    return n if isinstance(n, int) else int(n, 0)


def to_address(address) -> ChecksumAddress:
    return Web3.toChecksumAddress('%040x' % parse_int(address))


ZERO_ADDRESS = to_address(0)
IERC721_METADATA = '0x5b5e139f'
