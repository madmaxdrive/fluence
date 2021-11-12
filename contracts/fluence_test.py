import os
from collections import namedtuple

import pytest
from starkware.crypto.signature.signature import private_to_stark_key
from starkware.starknet.testing.contract import StarknetContract
from starkware.starknet.testing.starknet import Starknet

CONTRACT_FILE = os.path.join(os.path.dirname(__file__), "Fluence.cairo")
DEPOSIT_SELECTOR = 0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01
L1_ACCOUNT_ADDRESS = 0xFe02793B075106bFC519d6EE667fAcBB11fBB373
L1_CONTRACT_ADDRESS = 0x13095e61fC38a06041f2502FcC85ccF4100FDeFf
ERC721_CONTRACT_ADDRESS = 0xfAfC4Ec8ca3Eb374fbde6e9851134816Aada912a
ERC20_CONTRACT_ADDRESS = 0x4A26C7daCcC90434693de4b8bede3151884cab89
STARK_KEY = private_to_stark_key(1234567)

LimitOrder = namedtuple('LimitOrder', [
    'user', 'bid', 'base_contract', 'base_token_id', 'quote_contract', 'quote_amount', 'state'])


async def deploy() -> (StarknetContract, Starknet):
    starknet = await Starknet.empty()
    contract = await starknet.deploy(source=CONTRACT_FILE, constructor_calldata=[STARK_KEY])

    return contract, starknet


async def register_erc20(contract: StarknetContract):
    await contract. \
        register_contract(contract=ERC20_CONTRACT_ADDRESS, typ=1). \
        invoke(signature=[3188315614659720123310799887586131750511758198878983852700075419903551604210,
                          1706800001146843434779782924327663269365358863779377684961653390919935534593])


async def register_erc721(contract: StarknetContract):
    await contract. \
        register_contract(contract=ERC721_CONTRACT_ADDRESS, typ=2). \
        invoke(signature=[808731533420606349233674497012527795909213560809485398069975900119853328419,
                          2281033206651113054775327363648920689785861244160638966768093762692185778336])


async def deposit_erc20(contract: StarknetContract, starknet: Starknet):
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        DEPOSIT_SELECTOR,
        [STARK_KEY, 5050, ERC20_CONTRACT_ADDRESS])


async def create_order() -> (StarknetContract, Starknet):
    (contract, starknet) = await deploy()
    await register_erc20(contract)
    await register_erc721(contract)
    await deposit_erc20(contract, starknet)
    await contract. \
        create_order(id=13,
                     user=STARK_KEY,
                     bid=1,
                     base_contract=ERC721_CONTRACT_ADDRESS,
                     base_token_id=1,
                     quote_contract=ERC20_CONTRACT_ADDRESS,
                     quote_amount=1000). \
        invoke(signature=[2465446976930601613313290689566494744681330957706968178237697175223930491083,
                          1006396189397407373593107424743909871951296920275078297313951054563784940343])

    return contract, starknet


@pytest.mark.asyncio
async def test_register():
    (contract, _) = await deploy()
    await register_erc20(contract)
    exec_info = await contract.get_type(ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (1,)


@pytest.mark.asyncio
async def test_deposit():
    (contract, starknet) = await deploy()
    await register_erc20(contract)
    await deposit_erc20(contract, starknet)
    exec_info = await contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (5050,)


@pytest.mark.asyncio
async def test_withdraw():
    (contract, starknet) = await deploy()
    await register_erc20(contract)
    await deposit_erc20(contract, starknet)
    await contract. \
        withdraw(user=STARK_KEY,
                 amountOrId=5050,
                 contract=ERC20_CONTRACT_ADDRESS,
                 address=L1_ACCOUNT_ADDRESS). \
        invoke(signature=[87673833450390839569929612959841103865923396157049195288164988847475965107,
                          3519614127471173618987865569496329168415332144565312339513347592811067563185])
    exec_info = await contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    starknet.consume_message_from_l2(
        contract.contract_address,
        L1_CONTRACT_ADDRESS,
        [0, L1_ACCOUNT_ADDRESS, 5050, ERC20_CONTRACT_ADDRESS])


@pytest.mark.asyncio
async def test_create_order():
    (contract, starknet) = await create_order()
    exec_info = await contract.get_order(id=13).call()
    assert exec_info.result == (LimitOrder(
        user=STARK_KEY,
        bid=1,
        base_contract=ERC721_CONTRACT_ADDRESS,
        base_token_id=1,
        quote_contract=ERC20_CONTRACT_ADDRESS,
        quote_amount=1000,
        state=0),)
    exec_info = await contract.get_balance(user=STARK_KEY, contract=ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (4050,)


@pytest.mark.asyncio
async def test_fulfill_order():
    (contract, starknet) = await create_order()
    stark_key2 = private_to_stark_key(7654321)
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        DEPOSIT_SELECTOR,
        [stark_key2, 1, ERC721_CONTRACT_ADDRESS])
    await contract. \
        fulfill_order(id=13, user=stark_key2). \
        invoke(signature=[3099844777896423566313244533041173744197403653087717556680642636268377158704,
                          2305745516407173259381298230646736970464161483090057054847608490188660711970])
    exec_info = await contract.get_balance(user=STARK_KEY, contract=ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (4050,)
    exec_info = await contract.get_balance(user=stark_key2, contract=ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (1000,)
    exec_info = await contract.get_owner(token_id=1, contract=ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (STARK_KEY,)


@pytest.mark.asyncio
async def test_cancel_order():
    (contract, starknet) = await create_order()
    await contract. \
        cancel_order(id=13). \
        invoke(signature=[1225333364571694102780966770274162498671319402832892393464878774231250771955,
                          1057704955418873148055702905195964974402056683545758651742227714526147095680])
    exec_info = await contract.get_order(id=13).call()
    assert exec_info.result == (LimitOrder(
        user=STARK_KEY,
        bid=1,
        base_contract=ERC721_CONTRACT_ADDRESS,
        base_token_id=1,
        quote_contract=ERC20_CONTRACT_ADDRESS,
        quote_amount=1000,
        state=2),)
    exec_info = await contract.get_balance(user=STARK_KEY, contract=ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (5050,)
