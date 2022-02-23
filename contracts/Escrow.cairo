%lang starknet
%builtins pedersen range_check ecdsa

from starkware.cairo.common.alloc import alloc
from starkware.cairo.common.cairo_builtins import (HashBuiltin, SignatureBuiltin)
from starkware.cairo.common.hash import hash2
from starkware.cairo.common.math import assert_nn, assert_not_zero
from starkware.cairo.common.signature import verify_ecdsa_signature
from starkware.starknet.common.syscalls import get_tx_signature, get_contract_address, get_block_timestamp

struct Asset:
    member amount_or_token_id : felt
    member contract : felt
    member owner : felt
end

struct Escrow:
    member client_asset : Asset
    member vendor_asset : Asset
    member expire_at : felt
    member fulfilled_at : felt
    member canceled_at : felt
    member ended_at : felt
end

@contract_interface
namespace IFluence:
    func escrow_transfer(
        from_ : felt,
        to_ : felt,
        amount_or_token_id : felt,
        contract : felt):
    end
end

@storage_var
func escrows(escrow_id : felt) -> (escrow : Escrow):
end

@storage_var
func admin() -> (adm : felt):
end

@storage_var
func fluence_address() -> (fluence : felt):
end

@storage_var
func auto_commit_deadline() -> (deadline : felt):
end

@constructor
func constructor{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    fluence : felt,
    adm : felt,
    deadline : felt):
    fluence_address.write(fluence)
    admin.write(adm)
    auto_commit_deadline.write(deadline)

    return ()
end

@view
func get_escrow{
    syscall_ptr : felt*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt) -> (
    esc : Escrow):
    return escrows.read(escrow_id)
end

@external
func create_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    client_address : felt,
    client_amount_or_token_id : felt,
    client_contract : felt,
    vendor_address : felt,
    vendor_amount_or_token_id : felt,
    vendor_contract : felt,
    expire_at : felt,
    nonce : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = client_amount_or_token_id
    inputs[2] = client_contract
    inputs[3] = vendor_address
    inputs[4] = vendor_amount_or_token_id
    inputs[5] = vendor_contract
    inputs[6] = expire_at
    inputs[7] = nonce
    verify_inputs_by_signature(client_address, 8, inputs)

    assert_nn(client_amount_or_token_id)
    assert_nn(vendor_amount_or_token_id)
    assert_nn(expire_at)

    let (esc) = escrows.read(escrow_id)
    assert esc.client_asset.owner = 0

    let (fluence) = fluence_address.read()
    let (addr) = get_contract_address()

    escrows.write(escrow_id, Escrow(
        Asset(client_amount_or_token_id, client_contract, client_address),
        Asset(vendor_amount_or_token_id, vendor_contract, vendor_address),
        expire_at, 0, 0, 0))

    IFluence.escrow_transfer(contract_address=fluence, from_=client_address, to_=addr, amount_or_token_id=client_amount_or_token_id, contract=client_contract)

    return ()
end


@external
func fulfill_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    nonce : felt):
    alloc_locals

    let (esc) = escrows.read(escrow_id)

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = nonce
    verify_inputs_by_signature(esc.vendor_asset.owner, 2, inputs)

    let (fluence) = fluence_address.read()
    let (timestamp) = get_block_timestamp()
    let (addr) = get_contract_address()

    assert_not_zero(esc.client_asset.owner)
    assert_nn(esc.expire_at - timestamp)
    assert esc.fulfilled_at = 0
    assert esc.ended_at = 0

    escrows.write(escrow_id, Escrow(esc.client_asset,
                    esc.vendor_asset,
                    esc.expire_at,
                    timestamp,
                    esc.canceled_at,
                    esc.ended_at))

    IFluence.escrow_transfer(contract_address=fluence, from_=esc.vendor_asset.owner, to_=addr, amount_or_token_id=esc.vendor_asset.amount_or_token_id, contract=esc.vendor_asset.contract)

    return ()
end


@external
func cancel_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    nonce : felt):
    alloc_locals

    let (esc) = escrows.read(escrow_id)

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = nonce
    verify_inputs_by_signature(esc.client_asset.owner, 2, inputs)

    assert_not_zero(esc.client_asset.owner)
    assert esc.canceled_at = 0
    assert esc.ended_at = 0

    let (fluence) = fluence_address.read()
    let (timestamp) = get_block_timestamp()

    if esc.fulfilled_at == 0:
        let (addr) = get_contract_address()
        IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.client_asset.owner, amount_or_token_id=esc.client_asset.amount_or_token_id, contract=esc.client_asset.contract)
        escrows.write(escrow_id, Escrow(esc.client_asset,
                    esc.vendor_asset,
                    esc.expire_at,
                    esc.fulfilled_at,
                    timestamp,
                    timestamp))
    else:
        escrows.write(escrow_id, Escrow(esc.client_asset,
                    esc.vendor_asset,
                    esc.expire_at,
                    esc.fulfilled_at,
                    timestamp,
                    esc.ended_at))
    end

    return ()
end

@external
func approve_cancelation_request{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    nonce : felt):
    alloc_locals

    let (esc) = escrows.read(escrow_id)

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = nonce
    verify_inputs_by_signature(esc.vendor_asset.owner, 2, inputs)

    assert_not_zero(esc.fulfilled_at)
    assert_not_zero(esc.canceled_at)
    assert esc.ended_at = 0

    let (fluence) = fluence_address.read()
    let (timestamp) = get_block_timestamp()
    let (addr) = get_contract_address()

    escrows.write(escrow_id, Escrow(esc.client_asset,
                    esc.vendor_asset,
                    esc.expire_at,
                    esc.fulfilled_at,
                    esc.canceled_at,
                    timestamp))
                    
    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.client_asset.owner, amount_or_token_id=esc.client_asset.amount_or_token_id, contract=esc.client_asset.contract)
    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.vendor_asset.owner, amount_or_token_id=esc.vendor_asset.amount_or_token_id, contract=esc.vendor_asset.contract)
    
    return ()
end

@external
func decline_cancelation_request{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    nonce : felt):
    alloc_locals

    let (esc) = escrows.read(escrow_id)

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = nonce
    verify_inputs_by_signature(esc.vendor_asset.owner, 2, inputs)

    assert_not_zero(esc.fulfilled_at)
    assert_not_zero(esc.canceled_at)
    assert esc.ended_at = 0

    commit_escrow(escrow_id, esc)

    return ()
end

@external
func client_commit_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    nonce : felt):
    alloc_locals

    let (esc) = escrows.read(escrow_id)

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = nonce
    verify_inputs_by_signature(esc.client_asset.owner, 2, inputs)

    assert_not_zero(esc.fulfilled_at)
    assert esc.canceled_at = 0
    assert esc.ended_at = 0

    commit_escrow(escrow_id, esc)

    return ()
end

@external
func vendor_commit_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    nonce : felt):
    alloc_locals

    let (esc) = escrows.read(escrow_id)

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = nonce
    verify_inputs_by_signature(esc.vendor_asset.owner, 2, inputs)

    assert_not_zero(esc.fulfilled_at)
    assert esc.canceled_at = 0
    assert esc.ended_at = 0

    let (timestamp) = get_block_timestamp()
    let (deadline) = auto_commit_deadline.read()
    assert_nn(timestamp - (esc.fulfilled_at + deadline))

    commit_escrow(escrow_id, esc)

    return ()
end

func commit_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    esc : Escrow):

    let (timestamp) = get_block_timestamp()
    let (fluence) = fluence_address.read()
    let (addr) = get_contract_address()
    escrows.write(escrow_id, Escrow(esc.client_asset,
                        esc.vendor_asset,
                        esc.expire_at,
                        esc.fulfilled_at,
                        esc.canceled_at,
                        timestamp))

    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.client_asset.owner, amount_or_token_id=esc.vendor_asset.amount_or_token_id, contract=esc.vendor_asset.contract)
    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.vendor_asset.owner, amount_or_token_id=esc.client_asset.amount_or_token_id, contract=esc.client_asset.contract)

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