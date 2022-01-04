import os
import time
from collections import namedtuple
from uuid import uuid4

import pytest
from starkware.crypto.signature.signature import private_to_stark_key
from starkware.starknet.testing.contract import StarknetContract
from starkware.starknet.testing.starknet import Starknet
from starkware.starkware_utils.error_handling import StarkException

CONTRACT_FILE = os.path.join(os.path.dirname(__file__), 'Fluence.cairo')
DEPOSIT_SELECTOR = 0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01
STAKE_SELECTOR = 0x3a04795accb4b73d12f13b05a1e0e240cefeb9a89d008676730867a819d2f79
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
        [STARK_KEY, 5050, ERC20_CONTRACT_ADDRESS, uuid4().int])

async def stake(contract: StarknetContract, starknet: Starknet):
    await starknet.send_message_to_l2(
        L1_CONTRACT_ADDRESS,
        contract.contract_address,
        STAKE_SELECTOR,
        [STARK_KEY, 1000000000000000000, 1641150065 * 1000])

async def mint(contract: StarknetContract):
    await contract. \
        mint(STARK_KEY, 2, ERC721_CONTRACT_ADDRESS, 217292281291434132331442126937200208805). \
        invoke(signature=[1306249451098060094130075384669962757666348863185487228714287782531787341172,
                          2629852198967806542895315382808772828330779288973913156891915964395480058716])


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
async def test_stake():
    (contract, starknet) = await deploy()
    await stake(contract, starknet)
    exec_info = await contract.get_staked_balance(STARK_KEY, 0).call()
    assert exec_info.result[0].amount == 1000000000000000000

@pytest.mark.asyncio
async def test_unstake():
    (contract, starknet) = await deploy()
    await stake(contract, starknet)
    await contract. \
        unstake(user=STARK_KEY,
                stakeId=0,
                timestamp=1641150565 * 1000 + 864000000, # 10 days after staking
                address=L1_ACCOUNT_ADDRESS,
                nonce=338608066247168814322678008602989124261). \
        invoke(signature=[876935290743563885213297606353723079534093378583213021840330351513321845141,
                          936102956039466073993061508392329875300525871586498971538269245046554420634])
    exec_info = await contract.get_staked_balance(STARK_KEY, 0).call()
    assert exec_info.result[0].amount == 0

    starknet.consume_message_from_l2(
        contract.contract_address,
        L1_CONTRACT_ADDRESS,
        [1, L1_ACCOUNT_ADDRESS, 1001000450120021001, 338608066247168814322678008602989124261])

@pytest.mark.asyncio
async def test_withdraw():
    (contract, starknet) = await deploy()
    await register_erc20(contract, starknet)
    await deposit_erc20(contract, starknet)
    await contract. \
        withdraw(user=STARK_KEY,
                 amount_or_token_id=5050,
                 contract=ERC20_CONTRACT_ADDRESS,
                 address=L1_ACCOUNT_ADDRESS,
                 nonce=338608066247168814322678008602989124260). \
        invoke(signature=[2322320031199937621382164855179171324829388658558534430031773384874928285644,
                          2070325902313014673871594772287523004539112227316507563051466754981777192045])
    exec_info = await contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    starknet.consume_message_from_l2(
        contract.contract_address,
        L1_CONTRACT_ADDRESS,
        [0, L1_ACCOUNT_ADDRESS, 5050, ERC20_CONTRACT_ADDRESS, 0, 338608066247168814322678008602989124260])


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
                 amount_or_token_id=2,
                 contract=ERC721_CONTRACT_ADDRESS,
                 address=L1_ACCOUNT_ADDRESS,
                 nonce=173273242714120071103187695001323147281). \
        invoke(signature=[2678535620875345501668678371217928510013548776639414167699069934972524379781,
                          2732731440659982305657295441234382329772881433630859609902844746940886014120])
    exec_info = await contract.get_owner(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    exec_info = await contract.get_origin(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    starknet.consume_message_from_l2(
        contract.contract_address,
        L1_CONTRACT_ADDRESS,
        [0, L1_ACCOUNT_ADDRESS, 2, ERC721_CONTRACT_ADDRESS, 1, 173273242714120071103187695001323147281])


@pytest.mark.asyncio
async def test_transfer():
    (contract, starknet) = await deploy()
    await register_erc20(contract, starknet)
    await deposit_erc20(contract, starknet)
    await contract. \
        transfer(from_=STARK_KEY,
                 to_=STARK_KEY2,
                 amount_or_token_id=550,
                 contract=ERC20_CONTRACT_ADDRESS,
                 nonce=314449833170878049331847307766204685521). \
        invoke(signature=[467262548791535994682896466084327736580627222684837650067132059832051326515,
                          2582294054667657726949995064852086317426519424135885492175379122003100977749])
    exec_info = await contract.get_balance(STARK_KEY, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (4500,)
    exec_info = await contract.get_balance(STARK_KEY2, ERC20_CONTRACT_ADDRESS).call()
    assert exec_info.result == (550,)


@pytest.mark.asyncio
async def test_mint_transfer_withdraw():
    (contract, starknet) = await deploy()
    await register_erc721(contract, starknet)
    await mint(contract)
    await contract. \
        transfer(from_=STARK_KEY,
                 to_=STARK_KEY2,
                 amount_or_token_id=2,
                 contract=ERC721_CONTRACT_ADDRESS,
                 nonce=315888931651348871603397923743325615410). \
        invoke(signature=[2595214859632820632033438041468827058621421006079346309735406417353221952053,
                          618755873950903086286298903898444062644955181319230998910538047318072994585])
    exec_info = await contract.get_owner(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (STARK_KEY2,)
    await contract. \
        withdraw(user=STARK_KEY2,
                 amount_or_token_id=2,
                 contract=ERC721_CONTRACT_ADDRESS,
                 address=L1_ACCOUNT_ADDRESS,
                 nonce=50407069358279106007299077293281382102). \
        invoke(signature=[2508422384692550302034669989321115916146514271177796617609844688973317530029,
                          629021342378951084317970143722523714353581710022074652925254975225419591359])
    exec_info = await contract.get_owner(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    exec_info = await contract.get_origin(2, ERC721_CONTRACT_ADDRESS).call()
    assert exec_info.result == (0,)
    starknet.consume_message_from_l2(
        contract.contract_address,
        L1_CONTRACT_ADDRESS,
        [0, L1_ACCOUNT_ADDRESS, 2, ERC721_CONTRACT_ADDRESS, 1, 50407069358279106007299077293281382102])


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
        [stark_key2, 1, ERC721_CONTRACT_ADDRESS, uuid4().int])
    await contract. \
        fulfill_order(id=13, user=stark_key2, nonce=272432959850731251252854066178611669564). \
        invoke(signature=[321387143302878114952006499206549208486670715585015193735783076552567548299,
                          3398326251082476600958583921386602733415015918027941476560645323118374856725])
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
        [stark_key2, 1, ERC721_CONTRACT_ADDRESS, uuid4().int])
    with pytest.raises(StarkException):
        await contract. \
            fulfill_order(id=13, user=stark_key2, nonce=272432959850731251252854066178611669564). \
            invoke(signature=[3099844777896423566313244533041173744197403653087717556680642636268377158704,
                              2305745516407173259381298230646736970464161483090057054847608490188660711970])


@pytest.mark.asyncio
async def test_cancel_order():
    (contract, starknet) = await create_order()
    await contract. \
        cancel_order(id=13, nonce=158889073326537563656079938065157675041). \
        invoke(signature=[2650767131421198863105211231598636999147167781552928706499636054741643869930,
                          225496531335167625508834977728215331883459242940619785400861814095149514686])
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
            cancel_order(id=13, nonce=158889073326537563656079938065157675041). \
            invoke(signature=[1225333364571694102780966770274162498671319402832892393464878774231250771955,
                              1057704955418873148055702905195964974402056683545758651742227714526147095681])
