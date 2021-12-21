// SPDX-License-Identifier: MIT

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/metatx/ERC2771Context.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721Receiver.sol";
import "@openzeppelin/contracts/utils/Strings.sol";
import "@imtbl/imx-contracts/contracts/IMintable.sol";
import "./IStarknetCore.sol";

contract Fluence is IERC721Receiver, ERC2771Context {
    enum TokenType { Z, ERC20, ERC721 }

    uint256 constant WITHDRAW = 0;
    uint256 constant DEPOSIT = 0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01;
    uint256 constant REGISTER_CONTRACT = 0xe3f5e9e1456ffa52a3fbc7e8c296631d4cc2120c0be1e2829301c0d8fa026b;

    IStarknetCore starknetCore;
    address admin;
    uint nonce;

    mapping(address => TokenType) public contracts;

    constructor(IStarknetCore starknetCore_, address trustedForwarder) ERC2771Context(trustedForwarder) {
        starknetCore = starknetCore_;
        admin = msg.sender;
    }

    function registerContract(uint256 toContract, address tokenContract, TokenType tokenType, uint256 minter) external {
        require(admin == _msgSender(), "Unauthorized.");
        require(tokenType == TokenType.ERC20 || tokenType == TokenType.ERC721, "Bad token type.");
        require(contracts[tokenContract] == TokenType.Z, "Registered contract.");

        contracts[tokenContract] = tokenType;

        uint256[] memory payload = new uint256[](3);
        payload[0] = uint160(tokenContract);
        payload[1] = uint(tokenType);
        payload[2] = minter;
        starknetCore.sendMessageToL2(toContract, REGISTER_CONTRACT, payload);
    }

    function deposit(uint256 toContract, uint256 user) external payable {
        uint256[] memory payload = new uint256[](4);
        payload[0] = user;
        payload[1] = msg.value;
        payload[2] = 0;
        payload[3] = nonce++;
        starknetCore.sendMessageToL2(toContract, DEPOSIT, payload);
    }

    function deposit(uint256 toContract, uint256 user, uint256 amountOrId, address fromContract) external {
        TokenType typ_ = contracts[fromContract];
        require(typ_ != TokenType.Z, "Unregistered contract.");

        if (typ_ == TokenType.ERC20) {
            IERC20 erc20 = IERC20(fromContract);
            bool succeeded = erc20.transferFrom(_msgSender(), address(this), amountOrId);

            require(succeeded, "Transfer failure.");
        } else {
            IERC721 erc721 = IERC721(fromContract);
            erc721.safeTransferFrom(_msgSender(), address(this), amountOrId);
        }

        uint256[] memory payload = new uint256[](4);
        payload[0] = user;
        payload[1] = amountOrId;
        payload[2] = uint160(fromContract);
        payload[3] = nonce++;
        starknetCore.sendMessageToL2(toContract, DEPOSIT, payload);
    }

    function withdraw(uint256 fromContract, address payable user, uint256 amountOrId, address toContract, bool mint, uint256 nonce_) external {
        TokenType typ_ = contracts[toContract];
        require(toContract == address(0) || typ_ != TokenType.Z, "Unregistered contract.");

        uint256[] memory payload = new uint256[](6);
        payload[0] = WITHDRAW;
        payload[1] = uint160(_msgSender());
        payload[2] = amountOrId;
        payload[3] = uint160(toContract);
        payload[4] = mint ? 1 : 0;
        payload[5] = nonce_;
        starknetCore.consumeMessageFromL2(fromContract, payload);

        if (toContract == address(0)) {
            user.transfer(amountOrId);
        } else if (typ_ == TokenType.ERC20) {
            IERC20(toContract).transfer(user, amountOrId);
        } else if (mint) {
            IMintable(toContract).mintFor(user, 1, abi.encodePacked("{", Strings.toString(amountOrId), "}:{}"));
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
