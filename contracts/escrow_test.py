import os
from collections import namedtuple
from time import sleep
from uuid import uuid4
import functools

import pytest
from starkware.crypto.signature.fast_pedersen_hash import pedersen_hash
from starkware.crypto.signature.signature import private_to_stark_key, sign
from starkware.starknet.testing.contract import StarknetContract
from starkware.starknet.testing.starknet import Starknet
from starkware.starkware_utils.error_handling import StarkException
from starkware.starknet.business_logic.state import BlockInfo

FLUENCE_CONTRACT_FILE = os.path.join(os.path.dirname(__file__), 'Fluence.cairo')
ESCROW_CONTRACT_FILE = os.path.join(os.path.dirname(__file__), 'Escrow.cairo')
DEPOSIT_SELECTOR = 0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01
STAKE_SELECTOR = 0x3a04795accb4b73d12f13b05a1e0e240cefeb9a89d008676730867a819d2f79
REGISTER_CONTRACT_SELECTOR = 0xe3f5e9e1456ffa52a3fbc7e8c296631d4cc2120c0be1e2829301c0d8fa026b
L1_ACCOUNT_ADDRESS = 0xFe02793B075106bFC519d6EE667fAcBB11fBB373
L1_CONTRACT_ADDRESS = 0x13095e61fC38a06041f2502FcC85ccF4100FDeFf
ERC20_CONTRACT_ADDRESS = 0x4A26C7daCcC90434693de4b8bede3151884cab89
ERC721_CONTRACT_ADDRESS = 0xfAfC4Ec8ca3Eb374fbde6e9851134816Aada912a
STARK_KEY = private_to_stark_key(1234567)
STARK_KEY2 = private_to_stark_key(7654321)
DEFAULT_NONCE = 173273242714120071103187695001323147281

ContractDescription = namedtuple('ContractDescription', [
    'kind', 'mint'])
LimitOrder = namedtuple('LimitOrder', [
    'user', 'bid', 'base_contract', 'base_token_id', 'quote_contract', 'quote_amount', 'state'])


async def deploy() -> (StarknetContract, Starknet):
    starknet = await Starknet.empty()
    fluence_contract = await starknet.deploy(
        source=FLUENCE_CONTRACT_FILE,
        constructor_calldata=[L1_CONTRACT_ADDRESS, STARK_KEY])
    escrow_contract = await starknet.deploy(
        source=ESCROW_CONTRACT_FILE,
        constructor_calldata=[fluence_contract.contract_address, STARK_KEY, 5])
    await fluence_contract. \
        set_escrow_contract(contract=escrow_contract.contract_address,
                            nonce=338608066247168814322678008602989124261). \
        invoke(signature=sign_stark_inputs(1234567, [str(escrow_contract.contract_address),'338608066247168814322678008602989124261']))

    return fluence_contract, escrow_contract, starknet

def sign_stark_inputs(private_key: int, inputs: [str]):
    message_hash = functools.reduce(
        lambda x, y: pedersen_hash(y, x),
        reversed([int(x, 16) if x.startswith('0x') else int(x) for x in inputs]), 0)
    return sign(msg_hash=message_hash, priv_key=private_key)


def set_block_timestamp(starknet_state, timestamp):
    starknet_state.state.block_info = BlockInfo(
        starknet_state.state.block_info.block_number, timestamp
    )


async def register_erc20(contract: StarknetContract, starknet: Starknet):
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        REGISTER_CONTRACT_SELECTOR,
        [ERC20_CONTRACT_ADDRESS, 1, 0])


async def deposit_erc20(contract: StarknetContract, starknet: Starknet, user: any):
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        DEPOSIT_SELECTOR,
        [user, 5000, ERC20_CONTRACT_ADDRESS, uuid4().int])


async def create_escrow() -> (StarknetContract, Starknet):
    (fluence_contract, escrow_contract, starknet) = await deploy()
    set_block_timestamp(starknet.state, 1)
    await register_erc20(fluence_contract, starknet)
    await deposit_erc20(fluence_contract, starknet, STARK_KEY)
    await deposit_erc20(fluence_contract, starknet, STARK_KEY2)
    set_block_timestamp(starknet.state, 2)
    await escrow_contract. \
        create_escrow(escrow_id=1,
                     client_address=STARK_KEY,
                     client_amount_or_token_id=50,
                     client_contract=ERC20_CONTRACT_ADDRESS,
                     vendor_address=STARK_KEY2,
                     vendor_amount_or_token_id=100,
                     vendor_contract=ERC20_CONTRACT_ADDRESS,
                     expire_at=5,
                     nonce=DEFAULT_NONCE). \
        invoke(signature=sign_stark_inputs(1234567, ['1', '50', '0x4A26C7daCcC90434693de4b8bede3151884cab89', str(private_to_stark_key(7654321)), '100', '0x4A26C7daCcC90434693de4b8bede3151884cab89', '5', str(DEFAULT_NONCE)]))

    return fluence_contract, escrow_contract, starknet

@pytest.mark.asyncio
async def test_successful_escrow():
    fluence_contract, escrow_contract, starknet = await create_escrow()

    set_block_timestamp(starknet.state, 3)
    await escrow_contract.fulfill_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(7654321, ['1', str(DEFAULT_NONCE)]))

    set_block_timestamp(starknet.state, 4)
    await escrow_contract.client_commit_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(1234567, ['1', str(DEFAULT_NONCE)]))

    exec_info = await escrow_contract.get_escrow(1).call()
    assert exec_info.result[0].fulfilled_at == 3
    assert exec_info.result[0].canceled_at == 0
    assert exec_info.result[0].ended_at == 4
    
    exec_info = await fluence_contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 5050
    exec_info = await fluence_contract.get_balance(STARK_KEY2, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 4950


@pytest.mark.asyncio
async def test_early_cancelation():
    fluence_contract, escrow_contract, starknet = await create_escrow()

    set_block_timestamp(starknet.state, 3)
    await escrow_contract.cancel_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(1234567, ['1', str(DEFAULT_NONCE)]))

    exec_info = await escrow_contract.get_escrow(1).call()
    assert exec_info.result[0].fulfilled_at == 0
    assert exec_info.result[0].canceled_at == 3
    assert exec_info.result[0].ended_at == 3
    
    exec_info = await fluence_contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 5000
    exec_info = await fluence_contract.get_balance(STARK_KEY2, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 5000


@pytest.mark.asyncio
async def test_approved_cancelation():
    fluence_contract, escrow_contract, starknet = await create_escrow()

    set_block_timestamp(starknet.state, 3)
    await escrow_contract.fulfill_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(7654321, ['1', str(DEFAULT_NONCE)]))

    set_block_timestamp(starknet.state, 4)
    await escrow_contract.cancel_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(1234567, ['1', str(DEFAULT_NONCE)]))

    set_block_timestamp(starknet.state, 5)
    await escrow_contract.approve_cancelation_request(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(7654321, ['1', str(DEFAULT_NONCE)]))

    exec_info = await escrow_contract.get_escrow(1).call()
    assert exec_info.result[0].fulfilled_at == 3
    assert exec_info.result[0].canceled_at == 4
    assert exec_info.result[0].ended_at == 5
    
    exec_info = await fluence_contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 5000
    exec_info = await fluence_contract.get_balance(STARK_KEY2, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 5000

@pytest.mark.asyncio
async def test_declined_cancelation():
    fluence_contract, escrow_contract, starknet = await create_escrow()

    set_block_timestamp(starknet.state, 3)
    await escrow_contract.fulfill_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(7654321, ['1', str(DEFAULT_NONCE)]))

    set_block_timestamp(starknet.state, 4)
    await escrow_contract.cancel_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(1234567, ['1', str(DEFAULT_NONCE)]))

    set_block_timestamp(starknet.state, 5)
    await escrow_contract.decline_cancelation_request(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(7654321, ['1', str(DEFAULT_NONCE)]))

    exec_info = await escrow_contract.get_escrow(1).call()
    assert exec_info.result[0].fulfilled_at == 3
    assert exec_info.result[0].canceled_at == 4
    assert exec_info.result[0].ended_at == 5
    
    exec_info = await fluence_contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 5050
    exec_info = await fluence_contract.get_balance(STARK_KEY2, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 4950


@pytest.mark.asyncio
async def test_vendor_deadline_commit():
    fluence_contract, escrow_contract, starknet = await create_escrow()

    set_block_timestamp(starknet.state, 3)
    await escrow_contract.fulfill_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(7654321, ['1', str(DEFAULT_NONCE)]))

    set_block_timestamp(starknet.state, 9)
    await escrow_contract.vendor_commit_escrow(escrow_id=1, nonce=DEFAULT_NONCE).invoke(signature=sign_stark_inputs(7654321, ['1', str(DEFAULT_NONCE)]))

    exec_info = await escrow_contract.get_escrow(1).call()
    assert exec_info.result[0].fulfilled_at == 3
    assert exec_info.result[0].canceled_at == 0
    assert exec_info.result[0].ended_at == 9
    
    exec_info = await fluence_contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 5050
    exec_info = await fluence_contract.get_balance(STARK_KEY2, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result[0] == 4950