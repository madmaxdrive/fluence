import os
from collections import namedtuple

import pytest
from starkware.crypto.signature.signature import private_to_stark_key
from starkware.starknet.testing.contract import StarknetContract
from starkware.starknet.testing.starknet import Starknet
from starkware.starkware_utils.error_handling import StarkException

CONTRACT_FILE = os.path.join(os.path.dirname(__file__), 'Fluence.cairo')
DEPOSIT_SELECTOR = 0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01
REGISTER_CONTRACT_SELECTOR = 0xe3f5e9e1456ffa52a3fbc7e8c296631d4cc2120c0be1e2829301c0d8fa026b
L1_ACCOUNT_ADDRESS = 0xFe02793B075106bFC519d6EE667fAcBB11fBB373
L1_CONTRACT_ADDRESS = 0x13095e61fC38a06041f2502FcC85ccF4100FDeFf
ERC20_CONTRACT_ADDRESS = 0x4A26C7daCcC90434693de4b8bede3151884cab89
ERC721_CONTRACT_ADDRESS = 0xfAfC4Ec8ca3Eb374fbde6e9851134816Aada912a
STARK_KEY = private_to_stark_key(1234567)
STARK_KEY2 = private_to_stark_key(7654321)

ContractDescription = namedtuple('ContractDescription', [
    'kind', 'mint'])
LimitOrder = namedtuple('LimitOrder', [
    'user', 'bid', 'base_contract', 'base_token_id', 'quote_contract', 'quote_amount', 'state'])


async def deploy() -> (StarknetContract, Starknet):
    starknet = await Starknet.empty()
    contract = await starknet.deploy(
        source=CONTRACT_FILE,
        constructor_calldata=[L1_CONTRACT_ADDRESS, STARK_KEY])

    return contract, starknet


async def register_erc20(contract: StarknetContract, starknet: Starknet):
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        REGISTER_CONTRACT_SELECTOR,
        [ERC20_CONTRACT_ADDRESS, 1, 0])


async def register_erc721(contract: StarknetContract, starknet: Starknet):
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        REGISTER_CONTRACT_SELECTOR,
        [ERC721_CONTRACT_ADDRESS, 2, STARK_KEY2])


async def deposit_erc20(contract: StarknetContract, starknet: Starknet):
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        DEPOSIT_SELECTOR,
        [STARK_KEY, 5050, ERC20_CONTRACT_ADDRESS])


async def mint(contract: StarknetContract):
    await contract. \
        mint(STARK_KEY, 2, ERC721_CONTRACT_ADDRESS). \
        invoke(signature=[186133091381967715060574296421691771496874853225679541778423831297163257904,
                          2159522423434182066701336061301412973753235491998190210493057288484499386391])


async def create_order() -> (StarknetContract, Starknet):
    (contract, starknet) = await deploy()
    await register_erc20(contract, starknet)
    await register_erc721(contract, starknet)
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
    (contract, starknet) = await deploy()
    await register_erc20(contract, starknet)
    exec_info = await contract.describe(ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (ContractDescription(1, 0),)


@pytest.mark.asyncio
async def test_deposit():
    (contract, starknet) = await deploy()
    await register_erc20(contract, starknet)
    await deposit_erc20(contract, starknet)
    exec_info = await contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (5050,)


@pytest.mark.asyncio
async def test_withdraw():
    (contract, starknet) = await deploy()
    await register_erc20(contract, starknet)
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
        [0, L1_ACCOUNT_ADDRESS, 5050, ERC20_CONTRACT_ADDRESS, 0])


@pytest.mark.asyncio
async def test_mint():
    (contract, starknet) = await deploy()
    await register_erc721(contract, starknet)
    await mint(contract)
    exec_info = await contract.get_owner(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (STARK_KEY,)
    exec_info = await contract.get_origin(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (1,)


@pytest.mark.asyncio
async def test_withdraw_mint():
    (contract, starknet) = await deploy()
    await register_erc721(contract, starknet)
    await mint(contract)
    await contract. \
        withdraw(user=STARK_KEY,
                 amountOrId=2,
                 contract=ERC721_CONTRACT_ADDRESS,
                 address=L1_ACCOUNT_ADDRESS). \
        invoke(signature=[1642192099095322148379545134162194596936316127722794512339176035097185090822,
                          2932877095941959433960526984124930482177706603597483135592024064524137230233])
    exec_info = await contract.get_owner(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    exec_info = await contract.get_origin(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    starknet.consume_message_from_l2(
        contract.contract_address,
        L1_CONTRACT_ADDRESS,
        [0, L1_ACCOUNT_ADDRESS, 2, ERC721_CONTRACT_ADDRESS, 1])


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
async def test_create_order_signature_error():
    (contract, starknet) = await deploy()
    await register_erc20(contract, starknet)
    await register_erc721(contract, starknet)
    await deposit_erc20(contract, starknet)
    with pytest.raises(StarkException):
        await contract. \
            create_order(id=13,
                         user=STARK_KEY,
                         bid=1,
                         base_contract=ERC721_CONTRACT_ADDRESS,
                         base_token_id=1,
                         quote_contract=ERC20_CONTRACT_ADDRESS,
                         quote_amount=1000). \
            invoke(signature=[2465446976930601613313290689566494744681330957706968178237697175223930491083,
                              1006396189397407373593107424743909871951296920275078297313951054563784940344])


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
async def test_fulfill_order_signature_error():
    (contract, starknet) = await create_order()
    stark_key2 = private_to_stark_key(7654321)
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        DEPOSIT_SELECTOR,
        [stark_key2, 1, ERC721_CONTRACT_ADDRESS])
    with pytest.raises(StarkException):
        await contract. \
            fulfill_order(id=13, user=stark_key2). \
            invoke(signature=[3099844777896423566313244533041173744197403653087717556680642636268377158704,
                              2305745516407173259381298230646736970464161483090057054847608490188660711971])


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


@pytest.mark.asyncio
async def test_cancel_order_signature_error():
    (contract, starknet) = await create_order()
    with pytest.raises(StarkException):
        await contract. \
            cancel_order(id=13). \
            invoke(signature=[1225333364571694102780966770274162498671319402832892393464878774231250771955,
                              1057704955418873148055702905195964974402056683545758651742227714526147095681])
