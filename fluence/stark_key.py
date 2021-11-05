import functools
from hashlib import sha256
from struct import pack

import click
from eth_account import Account
from eth_account.hdaccount.deterministic import HDPath, SECP256K1_N
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from starkware.crypto.signature.fast_pedersen_hash import pedersen_hash
from starkware.crypto.signature.signature import EC_ORDER, private_to_stark_key, sign


def derive_stark_private_key(account: LocalAccount, layer: str, application: str, seed: bytes) -> int:
    hd = HDPath(derive_path(account, layer, application, 1))
    derived = hd.derive(seed)

    n = SECP256K1_N - SECP256K1_N % EC_ORDER
    i = 0
    while True:
        h = sha256(derived)
        h.update(pack('B', i))
        k = int(h.hexdigest(), 16)
        if k < n:
            return k % EC_ORDER

        i += 1


def derive_path(account: LocalAccount, layer: str, application: str, index: int) -> str:
    purpose = 2645
    layer = int.from_bytes(sha256(layer.encode('ascii')).digest(), byteorder='big') & ((1 << 31) - 1)
    application = int.from_bytes(sha256(application.encode('ascii')).digest(), byteorder='big') & ((1 << 31) - 1)
    address = int(account.address, 16)
    address = (address & ((1 << 31) - 1), (address >> 31) & ((1 << 31) - 1))

    return f"m/{purpose}'/{layer}'/{application}'/{address[0]}'/{address[1]}'/{index}"


def derive_seed(account: Account, message: str) -> bytes:
    signature = account.sign_message(encode_defunct(text=message))

    return signature.s.to_bytes(32, byteorder='big')


@click.group()
def cli():
    pass


@cli.command('derive')
@click.option('--layer', default='starknet')
@click.option('--application', default='fluence')
@click.argument('private_key')
@click.argument('seed', required=False)
def derive_stark_key(layer, application, private_key, seed):
    Account.enable_unaudited_hdwallet_features()
    account = Account.from_key(private_key)
    seed = derive_seed(account, seed) if seed is not None else account.key
    private_key = derive_stark_private_key(account, layer, application, seed)

    print("private key: 0x%064x" % private_key)
    print("stark key: 0x%064x" % private_to_stark_key(private_key))


@cli.command('sign')
@click.argument('private_key', type=int)
@click.argument('inputs', nargs=-1, required=False)
def sign_stark_inputs(private_key: int, inputs: [str]):
    message_hash = functools.reduce(
        lambda x, y: pedersen_hash(y, x),
        reversed([int(x, 16) if x.startswith('0x') else int(x) for x in inputs]), 0)
    print(sign(msg_hash=message_hash, priv_key=private_key))
