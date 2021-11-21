// SPDX-License-Identifier: MIT

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC721/IERC721.sol";

interface IMintable is IERC721 {
    function mintFor(address to, uint256 tokenId) external;
}
