%lang starknet
%builtins pedersen range_check ecdsa

from starkware.cairo.common.alloc import alloc
from starkware.cairo.common.cairo_builtins import (HashBuiltin, SignatureBuiltin)
from starkware.cairo.common.hash import hash2
from starkware.cairo.common.math import assert_nn, assert_not_zero
from starkware.cairo.common.signature import verify_ecdsa_signature
from starkware.starknet.common.messages import send_message_to_l1
from starkware.starknet.common.syscalls import get_tx_signature

const TYPE_ERC20 = 1
const TYPE_ERC721 = 2
const WITHDRAW = 0

const ASK = 0
const BID = 1

const STATE_NEW = 0
const STATE_FULFILLED = 1
const STATE_CANCELLED = 2

const L1_CONTRACT_ADDRESS = (0x13095e61fC38a06041f2502FcC85ccF4100FDeFf)

struct LimitOrder:
    member user : felt
    member bid : felt
    member base_contract : felt
    member base_token_id : felt
    member quote_contract : felt
    member quote_amount : felt
    member state : felt
end

@storage_var
func admin() -> (adm : felt):
end

@storage_var
func contract_type(contract : felt) -> (typ : felt):
end

@storage_var
func balance(user : felt, contract : felt) -> (bal : felt):
end

@storage_var
func owner(token_id : felt, contract : felt) -> (usr : felt):
end

@storage_var
func order(id : felt) -> (ord : LimitOrder):
end

@constructor
func constructor{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    adm : felt):
    admin.write(value=adm)

    return ()
end

@view
func get_type{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    contract : felt) -> (
    typ : felt):
    return contract_type.read(contract=contract)
end

@view
func get_balance{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    user : felt,
    contract : felt) -> (
    bal : felt):
    return balance.read(user=user, contract=contract)
end

@view
func get_owner{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    token_id : felt,
    contract : felt) -> (
    usr : felt):
    return owner.read(token_id=token_id, contract=contract)
end

@view
func get_order{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    id : felt) -> (
    ord : LimitOrder):
    return order.read(id=id)
end

@l1_handler
func register_contract{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    from_address : felt,
    contract : felt,
    typ : felt):

    #check from_addres
    let (l1 : felt) = l1_contract_address.read()
    assert from_address = l1

    #check type
    assert (typ - TYPE_ERC20) * (typ - TYPE_ERC721) = 0

    #check if contract if exist already
    let (typ0) = contract_type.read(contract=contract)
    assert typ0 = 0

    #check signature
    #let (adm) = admin.read()
    #let inputs : felt* = alloc()
    #inputs[0] = contract
    #inputs[1] = typ
    #verify_inputs_by_signature(adm, 2, inputs)

    #write contract
    contract_type.write(contract, typ)

    return ()
end

@external
func withdraw{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    user : felt,
    amountOrId : felt,
    contract : felt,
    address : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = amountOrId
    inputs[1] = contract
    inputs[2] = address
    verify_inputs_by_signature(user, 3, inputs)

    local ecdsa_ptr : SignatureBuiltin* = ecdsa_ptr
    let (typ) = contract_type.read(contract=contract)
    assert (typ - TYPE_ERC20) * (typ - TYPE_ERC721) = 0

    if typ == TYPE_ERC20:
        assert_nn(amountOrId)

        let (bal) = balance.read(user=user, contract=contract)
        let new_balance = bal - amountOrId
        assert_nn(new_balance)

        balance.write(user, contract, new_balance)
    else:
        let (usr) = owner.read(token_id=amountOrId, contract=contract)
        assert usr = user

        owner.write(amountOrId, contract, 0)
    end

    let (payload : felt*) = alloc()
    assert payload[0] = WITHDRAW
    assert payload[1] = address
    assert payload[2] = amountOrId
    assert payload[3] = contract
    send_message_to_l1(
        to_address=L1_CONTRACT_ADDRESS,
        payload_size=4,
        payload=payload)

    return ()
end

@l1_handler
func deposit{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    from_address : felt,
    user : felt,
    amountOrId : felt,
    contract : felt):
    assert from_address = L1_CONTRACT_ADDRESS

    let (typ) = contract_type.read(contract=contract)
    assert (typ - TYPE_ERC20) * (typ - TYPE_ERC721) = 0

    if typ == TYPE_ERC20:
        let (bal) = balance.read(user=user, contract=contract)

        balance.write(user, contract, bal + amountOrId)
    else:
        let (usr) = owner.read(token_id=amountOrId, contract=contract)
        assert usr = 0

        owner.write(amountOrId, contract, user)
    end

    return ()
end

@external
func create_order{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    id : felt,
    user : felt,
    bid : felt,
    base_contract : felt,
    base_token_id : felt,
    quote_contract : felt,
    quote_amount : felt):
    alloc_locals

    let (ord) = order.read(id=id)
    assert ord.user = 0

    let (typ) = contract_type.read(contract=base_contract)
    assert typ = TYPE_ERC721
    let (typ) = contract_type.read(contract=quote_contract)
    assert typ = TYPE_ERC20

    let inputs : felt* = alloc()
    inputs[0] = id
    inputs[1] = bid
    inputs[2] = base_contract
    inputs[3] = base_token_id
    inputs[4] = quote_contract
    inputs[5] = quote_amount
    verify_inputs_by_signature(user, 6, inputs)

    local ecdsa_ptr : SignatureBuiltin* = ecdsa_ptr
    if bid == ASK:
        let (usr) = owner.read(token_id=base_token_id, contract=base_contract)
        assert usr = user

        owner.write(base_token_id, base_contract, 0)
    else:
        let (bal) = balance.read(user=user, contract=quote_contract)
        let new_balance = bal - quote_amount
        assert_nn(new_balance)

        balance.write(user, quote_contract, new_balance)
    end

    order.write(id, LimitOrder(
        user=user,
        bid=bid,
        base_contract=base_contract,
        base_token_id=base_token_id,
        quote_contract=quote_contract,
        quote_amount=quote_amount,
        state=STATE_NEW))

    return ()
end

@external
func fulfill_order{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    id : felt,
    user : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = id
    verify_inputs_by_signature(user, 1, inputs)

    let (local ord) = order.read(id)
    assert_not_zero(ord.user)
    assert ord.state = STATE_NEW

    local ecdsa_ptr : SignatureBuiltin* = ecdsa_ptr
    if ord.bid == ASK:
        let (bal) = balance.read(user=user, contract=ord.quote_contract)
        let new_balance = bal - ord.quote_amount
        assert_nn(new_balance)
        balance.write(user, ord.quote_contract, new_balance)
        
        let (bal) = balance.read(user=ord.user, contract=ord.quote_contract)
        balance.write(ord.user, ord.quote_contract, bal + ord.quote_amount)
        
        let (usr) = owner.read(token_id=ord.base_token_id, contract=ord.base_contract)
        assert usr = 0
        owner.write(ord.base_token_id, ord.base_contract, user)
    else:
        let (usr) = owner.read(token_id=ord.base_token_id, contract=ord.base_contract)
        assert usr = user
        owner.write(ord.base_token_id, ord.base_contract, ord.user)

        let (bal) = balance.read(user=user, contract=ord.quote_contract)
        balance.write(user, ord.quote_contract, bal + ord.quote_amount)
    end

    order.write(id, LimitOrder(
        user=ord.user,
        bid=ord.bid,
        base_contract=ord.base_contract,
        base_token_id=ord.base_token_id,
        quote_contract=ord.quote_contract,
        quote_amount=ord.quote_amount,
        state=STATE_FULFILLED))

    return ()
end

@external
func cancel_order{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    id : felt):
    alloc_locals

    let (local ord) = order.read(id)
    assert_not_zero(ord.user)
    assert ord.state = STATE_NEW

    let inputs : felt* = alloc()
    inputs[0] = id
    verify_inputs_by_signature(ord.user, 1, inputs)

    local ecdsa_ptr : SignatureBuiltin* = ecdsa_ptr
    if ord.bid == ASK:
        let (usr) = owner.read(token_id=ord.base_token_id, contract=ord.base_contract)
        assert usr = 0

        owner.write(ord.base_token_id, ord.base_contract, ord.user)
    else:
        let (bal) = balance.read(user=ord.user, contract=ord.quote_contract)
        let new_balance = bal + ord.quote_amount
        assert_nn(new_balance)

        balance.write(ord.user, ord.quote_contract, new_balance)
    end

    order.write(id, LimitOrder(
        user=ord.user,
        bid=ord.bid,
        base_contract=ord.base_contract,
        base_token_id=ord.base_token_id,
        quote_contract=ord.quote_contract,
        quote_amount=ord.quote_amount,
        state=STATE_CANCELLED))

    return ()
end

func verify_inputs_by_signature{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    user : felt,
    n : felt,
    inputs : felt*):
    alloc_locals

    let (n_sig : felt, local sig : felt*) = get_tx_signature()
    assert n_sig = 2

    local syscall_ptr : felt* = syscall_ptr
    let (res) = hash_inputs(n, inputs)
    verify_ecdsa_signature(
        message=res,
        public_key=user,
        signature_r=sig[0],
        signature_s=sig[1])

    return ()
end

func hash_inputs{
    pedersen_ptr : HashBuiltin*}(
    n : felt, inputs : felt*) -> (
    result : felt):
    if n == 1:
        let (res) = hash2{hash_ptr=pedersen_ptr}(inputs[0], 0)

        return (result=res)
    end

    let (res) = hash_inputs(n - 1, inputs + 1)
    let (res) = hash2{hash_ptr=pedersen_ptr}(inputs[0], res)

    return (result=res)
end
