// SPDX-License-Identifier: MIT

pragma solidity ^0.8.0;

import "./IERC20.sol";
import "./IERC721.sol";
import "./IERC721Receiver.sol";
import "./IStarknetCore.sol";

contract Fluence is IERC721Receiver {
    enum TokenType { Z, ERC20, ERC721 }

    uint256 constant WITHDRAW = 0;
    uint256 constant DEPOSIT = 0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01;
    uint256 constant REGISTER_CONTRACT = 0xe3f5e9e1456ffa52a3fbc7e8c296631d4cc2120c0be1e2829301c0d8fa026b;

    IStarknetCore starknetCore;
    mapping(address => TokenType) public contracts;
    address admin;

    constructor(IStarknetCore starknetCore_, address admin_) {
        starknetCore = starknetCore_;
        admin = admin_;
    }

    function register_contract_ERC20(uint256 toContract, address token_address) external {
        register_contract(toContract, token_address, 1,TokenType.ERC20);
    }

    function register_contract_ERC721(uint256 toContract, address token_address) external {
        register_contract(toContract, token_address, 2, TokenType.ERC721);
    }

    function register_contract(uint256 toContract, address token_address, uint8 type_, TokenType tt) internal {
        require(admin == msg.sender, "Unauthorized.");

        contracts[address(token_address)] = tt;

        uint256[] memory payload = new uint256[](2);
        payload[0] = uint160(token_address);
        payload[1] = type_;
        starknetCore.sendMessageToL2(toContract, REGISTER_CONTRACT, payload);
    }

    function deposit(uint256 toContract, uint256 user, uint256 amountOrId, address fromContract) external {
        TokenType typ_ = contracts[fromContract];
        require(typ_ != TokenType.Z, "Unregistered contract.");

        if (typ_ == TokenType.ERC20) {
            IERC20 erc20 = IERC20(fromContract);
            erc20.transferFrom(msg.sender, address(this), amountOrId);
        } else {
            IERC721 erc721 = IERC721(fromContract);
            erc721.safeTransferFrom(msg.sender, address(this), amountOrId);
        }

        uint256[] memory payload = new uint256[](3);
        payload[0] = user;
        payload[1] = amountOrId;
        payload[2] = uint160(fromContract);
        starknetCore.sendMessageToL2(toContract, DEPOSIT, payload);
    }

    function withdraw(uint256 fromContract, address user, uint256 amountOrId, address toContract) external {
        TokenType typ_ = contracts[toContract];
        require(typ_ != TokenType.Z, "Unregistered contract.");

        uint256[] memory payload = new uint256[](4);
        payload[0] = WITHDRAW;
        payload[1] = uint160(msg.sender);
        payload[2] = amountOrId;
        payload[3] = uint160(toContract);
        starknetCore.consumeMessageFromL2(fromContract, payload);

        if (typ_ == TokenType.ERC20) {
            IERC20(toContract).transfer(user, amountOrId);
        } else {
            IERC721(toContract).safeTransferFrom(address(this), user, amountOrId);
        }
    }

    function onERC721Received(
        address /* operator */,
        address /* from */,
        uint256 /* tokenId */,
        bytes calldata /* data */
    ) override external pure returns (bytes4) {
        return IERC721Receiver.onERC721Received.selector;
    }
}
