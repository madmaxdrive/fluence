%lang starknet
%builtins pedersen range_check ecdsa

from starkware.cairo.common.alloc import alloc
from starkware.cairo.common.cairo_builtins import (HashBuiltin, SignatureBuiltin)
from starkware.cairo.common.hash import hash2
from starkware.cairo.common.math import assert_nn, assert_not_zero
from starkware.cairo.common.signature import verify_ecdsa_signature
from starkware.starknet.common.syscalls import get_tx_signature, get_contract_address, get_block_timestamp

struct Escrow:
    member escrow_id : felt
    member client_address : felt
    member client_amount_or_token_id : felt
    member client_contract : felt
    member vendor_address : felt
    member vendor_amount_or_token_id : felt
    member vendor_contract : felt
    member time_limit : felt
    member time_created : felt
    member time_fulfilled : felt
    member time_canceled : felt
    member time_ended : felt
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
func transfer_to_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    sender_address : felt,
    sender_amount_or_token_id : felt,
    sender_contract : felt,
    recipient_address : felt,
    recipient_amount_or_token_id : felt,
    recipient_contract : felt,
    time_limit : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    inputs[1] = sender_amount_or_token_id
    inputs[2] = sender_contract
    inputs[3] = recipient_address
    inputs[4] = recipient_amount_or_token_id
    inputs[5] = recipient_contract
    inputs[6] = time_limit
    verify_inputs_by_signature(sender_address, 7, inputs)

    assert_nn(sender_amount_or_token_id)
    assert_nn(recipient_amount_or_token_id)

    let (fluence) = fluence_address.read()
    let (esc) = escrows.read(escrow_id)
    let (timestamp) = get_block_timestamp()
    let (addr) = get_contract_address()

    if esc.client_address == 0:
        # CREATE NEW ESCROW
        escrows.write(escrow_id, Escrow(escrow_id,
                        sender_address,
                        sender_amount_or_token_id,
                        sender_contract,
                        recipient_address,
                        recipient_amount_or_token_id,
                        recipient_contract,
                        time_limit,
                        timestamp,
                        0,
                        0,
                        0))
    else:
        # FULFILL EXISTING ESCROW
        assert esc.client_address = recipient_address
        assert esc.client_amount_or_token_id = recipient_amount_or_token_id
        assert esc.client_contract = recipient_contract
        assert esc.time_ended = 0
        assert_not_zero(esc.time_created)
        assert_nn(esc.time_created + esc.time_limit - timestamp)

        escrows.write(escrow_id, Escrow(esc.escrow_id,
                        esc.client_address,
                        esc.client_amount_or_token_id,
                        esc.client_contract,
                        esc.vendor_address,
                        esc.vendor_amount_or_token_id,
                        esc.vendor_contract,
                        esc.time_limit,
                        esc.time_created,
                        timestamp,
                        esc.time_canceled,
                        esc.time_ended))
    end

    IFluence.escrow_transfer(contract_address=fluence, from_=sender_address, to_=addr, amount_or_token_id=sender_amount_or_token_id, contract=sender_contract)

    return ()
end

@external
func cancel_escrow{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    sender_address : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    verify_inputs_by_signature(sender_address, 1, inputs)

    let (esc) = escrows.read(escrow_id)
    assert sender_address = esc.client_address
    assert esc.time_ended = 0
    assert esc.time_canceled = 0
    assert_not_zero(esc.time_created)

    let (fluence) = fluence_address.read()
    let (timestamp) = get_block_timestamp()

    if esc.time_fulfilled == 0:
        let (addr) = get_contract_address()
        IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.client_address, amount_or_token_id=esc.client_amount_or_token_id, contract=esc.client_contract)
        escrows.write(escrow_id, Escrow(esc.escrow_id,
                    esc.client_address,
                    esc.client_amount_or_token_id,
                    esc.client_contract,
                    esc.vendor_address,
                    esc.vendor_amount_or_token_id,
                    esc.vendor_contract,
                    esc.time_limit,
                    esc.time_created,
                    esc.time_fulfilled,
                    timestamp,
                    timestamp))
    else:
        escrows.write(escrow_id, Escrow(esc.escrow_id,
                    esc.client_address,
                    esc.client_amount_or_token_id,
                    esc.client_contract,
                    esc.vendor_address,
                    esc.vendor_amount_or_token_id,
                    esc.vendor_contract,
                    esc.time_limit,
                    esc.time_created,
                    esc.time_fulfilled,
                    timestamp,
                    esc.time_ended))
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
    sender_address : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    verify_inputs_by_signature(sender_address, 1, inputs)

    let (esc) = escrows.read(escrow_id)
    assert sender_address = esc.vendor_address
    assert esc.time_ended = 0
    assert_not_zero(esc.time_created)
    assert_not_zero(esc.time_fulfilled)
    assert_not_zero(esc.time_canceled)

    let (fluence) = fluence_address.read()
    let (timestamp) = get_block_timestamp()
    let (addr) = get_contract_address()

    escrows.write(escrow_id, Escrow(esc.escrow_id,
                    esc.client_address,
                    esc.client_amount_or_token_id,
                    esc.client_contract,
                    esc.vendor_address,
                    esc.vendor_amount_or_token_id,
                    esc.vendor_contract,
                    esc.time_limit,
                    esc.time_created,
                    esc.time_fulfilled,
                    esc.time_canceled,
                    timestamp))
                    
    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.client_address, amount_or_token_id=esc.client_amount_or_token_id, contract=esc.client_contract)
    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.vendor_address, amount_or_token_id=esc.vendor_amount_or_token_id, contract=esc.vendor_contract)
    
    return ()
end

@external
func decline_cancelation_request{
    syscall_ptr : felt*,
    ecdsa_ptr : SignatureBuiltin*,
    pedersen_ptr : HashBuiltin*,
    range_check_ptr}(
    escrow_id : felt,
    sender_address : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    verify_inputs_by_signature(sender_address, 1, inputs)

    let (esc) = escrows.read(escrow_id)
    assert sender_address = esc.vendor_address
    assert esc.time_ended = 0
    assert_not_zero(esc.time_created)
    assert_not_zero(esc.time_fulfilled)
    assert_not_zero(esc.time_canceled)

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
    sender_address : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    verify_inputs_by_signature(sender_address, 1, inputs)

    let (esc) = escrows.read(escrow_id)
    assert esc.client_address = sender_address
    assert esc.time_ended = 0
    assert esc.time_canceled = 0
    assert_not_zero(esc.time_created)
    assert_not_zero(esc.time_fulfilled)

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
    sender_address : felt):
    alloc_locals

    let inputs : felt* = alloc()
    inputs[0] = escrow_id
    verify_inputs_by_signature(sender_address, 1, inputs)

    let (timestamp) = get_block_timestamp()
    let (deadline) = auto_commit_deadline.read()
    let (esc) = escrows.read(escrow_id)
    assert esc.vendor_address = sender_address
    assert esc.time_ended = 0
    assert esc.time_canceled = 0
    assert_not_zero(esc.time_created)
    assert_not_zero(esc.time_fulfilled)
    assert_nn(timestamp - esc.time_fulfilled + deadline)

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
    escrows.write(escrow_id, Escrow(esc.escrow_id,
                        esc.client_address,
                        esc.client_amount_or_token_id,
                        esc.client_contract,
                        esc.vendor_address,
                        esc.vendor_amount_or_token_id,
                        esc.vendor_contract,
                        esc.time_limit,
                        esc.time_created,
                        esc.time_fulfilled,
                        esc.time_canceled,
                        timestamp))

    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.client_address, amount_or_token_id=esc.vendor_amount_or_token_id, contract=esc.vendor_contract)
    IFluence.escrow_transfer(contract_address=fluence, from_=addr, to_=esc.vendor_address, amount_or_token_id=esc.client_amount_or_token_id, contract=esc.client_contract)

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