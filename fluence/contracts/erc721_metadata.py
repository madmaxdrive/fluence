import jsonschema
import pkg_resources
from eth_typing import ChecksumAddress
from web3 import Web3

IERC721_METADATA = '0x5b5e139f'
ERC721_METADATA_JSON_SCHEMA = {
    "title": "Asset Metadata",
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Identifies the asset to which this NFT represents"
        },
        "description": {
            "type": "string",
            "description": "Describes the asset to which this NFT represents"
        },
        "image": {
            "type": "string",
            "description": "A URI pointing to a resource with mime type image/* representing the asset to which this NFT represents. Consider making any images at a width between 320 and 1080 pixels and aspect ratio between 1.91:1 and 4:5 inclusive."
        }
    }
}


class ERC721Metadata:
    @staticmethod
    def validate(instance):
        jsonschema.validate(instance, ERC721_METADATA_JSON_SCHEMA)

    def __init__(self, address: ChecksumAddress, w3: Web3):
        self.contract = w3.eth.contract(
            address,
            abi=pkg_resources.resource_string(__name__, 'abi/IERC721Metadata.abi').decode())

    def identify(self) -> tuple[str, str, int]:
        return (
            self.contract.functions['name']().call(),
            self.contract.functions['symbol']().call(),
            0)

    def token_uri(self, token_id: int) -> str:
        return self.contract.functions['tokenURI'](token_id).call()
