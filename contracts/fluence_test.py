import os

import pytest
from starkware.crypto.signature.signature import private_to_stark_key
from starkware.starknet.testing.starknet import Starknet

CONTRACT_FILE = os.path.join(os.path.dirname(__file__), "Fluence.cairo")


@pytest.mark.asyncio
async def test_register():
    starknet = await Starknet.empty()
    private_key = 1234567
    stark_key = private_to_stark_key(private_key)
    contract = await starknet.deploy(source=CONTRACT_FILE, constructor_calldata=[stark_key])
    await contract. \
        register_contract(contract=0x4A26C7daCcC90434693de4b8bede3151884cab89, typ=1). \
        invoke(signature=[3188315614659720123310799887586131750511758198878983852700075419903551604210,
                          1706800001146843434779782924327663269365358863779377684961653390919935534593])
    exec_info = await contract.get_type(0x4A26C7daCcC90434693de4b8bede3151884cab89).call()
    assert exec_info.result == (1,)


@pytest.mark.asyncio
async def test_deposit():
    starknet = await Starknet.empty()
    private_key = 1234567
    stark_key = private_to_stark_key(private_key)
    contract = await starknet.deploy(source=CONTRACT_FILE, constructor_calldata=[stark_key])
    await contract. \
        register_contract(contract=0x4A26C7daCcC90434693de4b8bede3151884cab89, typ=1). \
        invoke(signature=[3188315614659720123310799887586131750511758198878983852700075419903551604210,
                          1706800001146843434779782924327663269365358863779377684961653390919935534593])
    await starknet.send_message_to_l2(
        0x13095e61fC38a06041f2502FcC85ccF4100FDeFf,
        contract.contract_address,
        0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01,
        [stark_key, 5050, 0x4A26C7daCcC90434693de4b8bede3151884cab89])
    exec_info = await contract.get_balance(stark_key, 0x4A26C7daCcC90434693de4b8bede3151884cab89).call()
    assert exec_info.result == (5050,)


@pytest.mark.asyncio
async def test_withdraw():
    starknet = await Starknet.empty()
    private_key = 1234567
    stark_key = private_to_stark_key(private_key)
    contract = await starknet.deploy(source=CONTRACT_FILE, constructor_calldata=[stark_key])
    await contract. \
        register_contract(contract=0x4A26C7daCcC90434693de4b8bede3151884cab89, typ=1). \
        invoke(signature=[3188315614659720123310799887586131750511758198878983852700075419903551604210,
                          1706800001146843434779782924327663269365358863779377684961653390919935534593])
    await starknet.send_message_to_l2(
        0x13095e61fC38a06041f2502FcC85ccF4100FDeFf,
        contract.contract_address,
        0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01,
        [stark_key, 5050, 0x4A26C7daCcC90434693de4b8bede3151884cab89])
    await contract. \
        withdraw(user=stark_key,
                 amountOrId=5050,
                 contract=0x4A26C7daCcC90434693de4b8bede3151884cab89,
                 address=0xFe02793B075106bFC519d6EE667fAcBB11fBB373). \
        invoke(signature=[87673833450390839569929612959841103865923396157049195288164988847475965107,
                          3519614127471173618987865569496329168415332144565312339513347592811067563185])
    exec_info = await contract.get_balance(stark_key, 0x4A26C7daCcC90434693de4b8bede3151884cab89).call()
    assert exec_info.result == (0,)
    starknet.consume_message_from_l2(
        contract.contract_address,
        0x13095e61fC38a06041f2502FcC85ccF4100FDeFf,
        [0, 0xFe02793B075106bFC519d6EE667fAcBB11fBB373, 5050, 0x4A26C7daCcC90434693de4b8bede3151884cab89])
