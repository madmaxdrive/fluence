import functools
from decimal import Decimal
from enum import Enum
from typing import Union

import click
import pendulum
import pkg_resources
import pyrsistent
from aiohttp import web
from aiohttp.web_request import Request
from decouple import config
from eth_account import Account
from openapi_core import create_spec
from rororo import OperationTableDef, setup_openapi, openapi_context
from services.external_api.base_client import RetryConfig
from sqlalchemy import select, desc, null, false, true
from sqlalchemy.exc import NoResultFound, IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import functions
from starkware.crypto.signature.fast_pedersen_hash import pedersen_hash
from starkware.crypto.signature.signature import verify
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from web3 import Web3

from fluence.contracts.fluence import StarkFluence, LimitOrder, EtherFluence, ContractKind
from fluence.contracts.forwarder import Forwarder, ReqSchema
from fluence.utils import parse_int

operations = OperationTableDef()


class Status(Enum):
    NOT_RECEIVED = 'NOT_RECEIVED'
    RECEIVED = 'RECEIVED'
    PENDING = 'PENDING'
    REJECTED = 'REJECTED'
    ACCEPTED_ON_L2 = 'ACCEPTED_ON_L2'
    ACCEPTED_ON_L1 = 'ACCEPTED_ON_L1'


@operations.register
async def get_contracts(request: Request):
    return web.json_response({
        'fluence': request.config_dict['forwarder'].to_address,
        'forwarder': request.config_dict['forwarder'].address,
    })


@operations.register
async def register_client(request: Request):
    with openapi_context(request) as context:
        tx = await request.config_dict['fluence']. \
            register_client(context.data['stark_key'],
                            context.data['address'],
                            context.data['nonce'],
                            context.parameters.query['signature'])

        return web.json_response({'transaction_hash': tx})


@operations.register
async def get_client(request: Request):
    with openapi_context(request) as context:
        stark_key = await request.config_dict['fluence']. \
            get_client(context.parameters.path['address'])
        if stark_key == 0:
            return web.HTTPNotFound()

        return web.json_response({'stark_key': str(stark_key)})


@operations.register
async def create_blueprint(request: Request):
    with openapi_context(request) as context:
        minter = Decimal(context.data['minter'])
        if not authenticate(
                [context.data['permanent_id'].encode()],
                context.parameters.query['signature'],
                int(minter)):
            return web.HTTPUnauthorized()

        async with request.config_dict['async_session']() as session:
            from fluence.models import Account, Blueprint, BlueprintSchema

            try:
                account = (await session.execute(
                    select(Account).
                    where(Account.stark_key == minter))).scalar_one()
            except NoResultFound:
                account = Account(stark_key=minter)
                session.add(account)

            try:
                blueprint = Blueprint(
                    permanent_id=context.data['permanent_id'],
                    minter=account,
                    expire_at=pendulum.now().add(days=7))
                session.add(blueprint)
                await session.commit()
            except IntegrityError:
                return web.HTTPBadRequest()

            return web.json_response(BlueprintSchema().dump(blueprint))


@operations.register
async def find_collections(request: Request):
    with openapi_context(request) as context:
        page = context.parameters.query.get('page', 1)
        size = context.parameters.query.get('size', 100)
        owner = context.parameters.query.get('owner')

        async with request.config_dict['async_session']() as session:
            from fluence.models import TokenContract, TokenContractSchema, Account, Blueprint

            def augment(stmt):
                stmt = stmt.where(TokenContract.fungible == false())
                if owner:
                    stmt = stmt.join(TokenContract.blueprint). \
                        join(Blueprint.minter). \
                        where(Account.address == owner)

                return stmt

            query = augment(select(TokenContract)). \
                order_by(desc(TokenContract.id)). \
                limit(size). \
                offset(size * (page - 1))
            count = augment(select(functions.count()).select_from(TokenContract))

            return web.json_response({
                'data': list(map(
                    TokenContractSchema().dump,
                    (await session.execute(
                        query.options(
                            selectinload(TokenContract.blueprint).
                            selectinload(Blueprint.minter)))).scalars())),
                'total': (await session.execute(count)).scalar_one(),
            })


@operations.register
async def register_collection(request: Request):
    with openapi_context(request) as context:
        async with request.config_dict['async_session']() as session:
            from fluence.models import TokenContract, Account, Blueprint

            if 'blueprint' in context.data:
                blueprint = (await session.execute(
                    select(Blueprint).
                    where(Blueprint.permanent_id == context.data['blueprint']).
                    options(
                        selectinload(Blueprint.minter),
                        selectinload(Blueprint.contract)))).scalar_one()
                if blueprint.contract:
                    return web.HTTPBadRequest()
            else:
                minter = parse_int(context.data['minter'])
                try:
                    account = (await session.execute(
                        select(Account).
                        where(Account.address == minter))).scalar_one()
                except NoResultFound:
                    account = Account(stark_key=minter)
                    session.add(account)

                blueprint = Blueprint(account)
                session.add(blueprint)

            if not authenticate(
                    [context.data['address'],
                     context.data['name'].encode(),
                     context.data['symbol'].encode(),
                     context.data['base_uri'].encode(),
                     context.data['image'].encode()],
                    context.parameters.query['signature'],
                    int(blueprint.minter.stark_key)):
                return web.HTTPUnauthorized()

            token_contract = TokenContract(
                address=context.data['address'],
                fungible=False,
                blueprint=blueprint,
                name=context.data['name'],
                symbol=context.data['symbol'],
                decimals=0,
                base_uri=context.data['base_uri'],
                image=context.data['image'])
            session.add(token_contract)

            req, signature = request.config_dict['forwarder'].forward(
                *request.config_dict['ether_fluence'].register_contract(
                    token_contract.address, ContractKind.ERC721, int(blueprint.minter.stark_key)))
            await session.commit()

            return web.json_response({
                'req': ReqSchema().dump(req),
                'signature': signature,
            })


@operations.register
async def get_metadata_by_permanent_id(request: Request):
    with openapi_context(request) as context:
        async with request.config_dict['async_session']() as session:
            from fluence.models import Token, TokenContract, Blueprint

            try:
                token = (await session.execute(
                    select(Token).
                    join(Token.contract).
                    join(TokenContract.blueprint).
                    where(Token.token_id == parse_int(context.parameters.path['token_id'])).
                    where(Blueprint.permanent_id == context.parameters.path['permanent_id']))).scalar_one()

                return web.json_response(token.asset_metadata)
            except NoResultFound:
                return web.HTTPNotFound()


@operations.register
async def get_metadata(request: Request):
    with openapi_context(request) as context:
        token_id = parse_int(context.parameters.path['token_id'])
        address = Web3.toChecksumAddress(context.parameters.path['address'])
        async with request.config_dict['async_session']() as session:
            from fluence.models import TokenContract, Token

            try:
                token = (await session.execute(
                    select(Token).
                    join(Token.contract).
                    where(Token.token_id == token_id).
                    where(TokenContract.address == address))).scalar_one()

                return web.json_response(token.asset_metadata)
            except NoResultFound:
                return web.HTTPNotFound()


@operations.register
async def update_metadata(request: Request):
    with openapi_context(request) as context:
        token_id = parse_int(request.match_info['token_id'])
        address = Web3.toChecksumAddress(context.parameters.path['address'])
        async with request.config_dict['async_session']() as session:
            from fluence.models import TokenContract, Blueprint, Token, TokenSchema

            try:
                token_contract = (await session.execute(
                    select(TokenContract).
                    where(TokenContract.address == address).
                    where(TokenContract.blueprint != null()).
                    options(
                        selectinload(TokenContract.blueprint).
                        selectinload(Blueprint.minter)))).scalar_one()
            except NoResultFound:
                return web.HTTPNotFound()

            try:
                token = (await session.execute(
                    select(Token).
                    where(Token.token_id == token_id).
                    where(Token.contract == token_contract).
                    options(selectinload(Token.contract)))).scalar_one()
            except NoResultFound:
                token = Token(contract=token_contract, token_id=token_id, nonce=0)
                session.add(token)

            if not authenticate(
                    [token_contract.address, token_id, token.nonce],
                    context.parameters.query['signature'],
                    int(token_contract.blueprint.minter.stark_key)):
                return web.HTTPUnauthorized()

            token.name = context.data['name']
            token.description = context.data['description']
            token.image = context.data['image']
            token.asset_metadata = pyrsistent.thaw(context.data)
            token.nonce += 1

            await session.commit()

            return web.json_response(TokenSchema().dump(token))


@operations.register
async def find_tokens(request: Request):
    with openapi_context(request) as context:
        page = context.parameters.query.get('page', 1)
        size = context.parameters.query.get('size', 100)
        owner = context.parameters.query.get('owner')
        collection = context.parameters.query.get('collection')

        async with request.config_dict['async_session']() as session:
            from fluence.models import Token, TokenSchema, TokenContract, Account, Blueprint

            def augment(stmt):
                if owner:
                    stmt = stmt.join(Token.owner). \
                        where(Account.address == owner)
                if collection:
                    stmt = stmt.join(Token.contract). \
                        where(TokenContract.address == collection)

                return stmt

            query = augment(select(Token)). \
                order_by(desc(Token.id)). \
                limit(size). \
                offset(size * (page - 1))
            count = augment(select(functions.count()).select_from(Token))

            return web.json_response({
                'data': list(map(
                    TokenSchema().dump,
                    (await session.execute(
                        query.options(
                            selectinload(Token.contract).
                            selectinload(TokenContract.blueprint).
                            selectinload(Blueprint.minter)))).scalars())),
                'total': (await session.execute(count)).scalar_one(),
            })


@operations.register
async def get_balance(request: Request):
    with openapi_context(request) as context:
        balance = await request.config_dict['fluence'].get_balance(
            context.parameters.query['user'],
            context.parameters.query['contract'])

        return web.json_response({'balance': str(balance)})


@operations.register
async def get_owner(request: Request):
    with openapi_context(request) as context:
        owner = await request.config_dict['fluence'].get_owner(
            context.parameters.query['token_id'],
            context.parameters.query['contract'])

        return web.json_response({'owner': str(owner)})


@operations.register
async def mint(request: Request):
    with openapi_context(request) as context:
        tx = await request.config_dict['fluence'].mint(
            context.data['user'],
            context.data['token_id'],
            context.data['contract'],
            context.data['nonce'],
            context.parameters.query['signature'])

        return web.json_response({'transaction_hash': tx})


@operations.register
async def withdraw(request: Request):
    with openapi_context(request) as context:
        tx = await request.config_dict['fluence'].withdraw(
            context.data['user'],
            context.data['amount_or_token_id'],
            context.data['contract'],
            context.data['address'],
            context.data['nonce'],
            context.parameters.query['signature'])

        return web.json_response({'transaction_hash': tx})


@operations.register
async def transfer(request: Request):
    with openapi_context(request) as context:
        tx = await request.config_dict['fluence'].transfer(
            context.data['from'],
            context.data['to'],
            context.data['amount_or_token_id'],
            context.data['contract'],
            context.data['nonce'],
            context.parameters.query['signature'])

        return web.json_response({'transaction_hash': tx})


@operations.register
async def find_orders(request: Request):
    with openapi_context(request) as context:
        page = context.parameters.query.get('page', 1)
        size = context.parameters.query.get('size', 100)
        user = context.parameters.query.get('user')
        collection = context.parameters.query.get('collection')
        side = context.parameters.query.get('side')
        state = context.parameters.query.get('state')

    async with request.config_dict['async_session']() as session:
        from fluence.models import LimitOrder, LimitOrderSchema, Account, Token, TokenContract

        def augment(stmt):
            if user:
                stmt = stmt.join(LimitOrder.user). \
                    where(Account.address == user)
            if collection:
                stmt = stmt.join(LimitOrder.token). \
                    join(Token.contract). \
                    where(TokenContract.address == collection)
            if side:
                stmt = stmt.where(LimitOrder.bid == (side == 'bid'))
            if state:
                stmt = stmt.where(LimitOrder.fulfilled == [null(), true(), false()][state])

            return stmt

        query = augment(select(LimitOrder)). \
            order_by(desc(LimitOrder.id)). \
            limit(size). \
            offset(size * (page - 1))
        count = augment(select(functions.count()).select_from(LimitOrder))

        return web.json_response({
            'data': list(map(
                LimitOrderSchema().dump,
                (await session.execute(
                    query.options(
                        selectinload(LimitOrder.user),
                        selectinload(LimitOrder.token).selectinload(Token.contract),
                        selectinload(LimitOrder.quote_contract)))).scalars())),
            'total': (await session.execute(count)).scalar_one(),
        })


@operations.register
async def create_order(request: Request):
    with openapi_context(request) as context:
        tx = await request.config_dict['fluence'].create_order(
            context.data['order_id'],
            LimitOrder(**context.data.discard('order_id'), state=0),
            context.parameters.query['signature'])

        return web.json_response({'transaction_hash': tx})


@operations.register
async def get_order(request: Request):
    with openapi_context(request) as context:
        from fluence.contracts import LimitOrderSchema

        limit_order = await request.config_dict['fluence'].get_order(context.parameters.path['id'])
        if parse_int(limit_order.user) == 0:
            return web.HTTPNotFound()

        return web.json_response(LimitOrderSchema().dump(limit_order))


@operations.register
async def fulfill_order(request: Request):
    with openapi_context(request) as context:
        tx = await request.config_dict['fluence'].fulfill_order(
            context.parameters.path['id'],
            context.data['user'],
            context.data['nonce'],
            context.parameters.query['signature'])

        return web.json_response({'transaction_hash': tx})


@operations.register
async def cancel_order(request: Request):
    with openapi_context(request) as context:
        tx = await request.config_dict['fluence'].cancel_order(
            context.parameters.path['id'],
            context.parameters.query['nonce'],
            context.parameters.query['signature'])

        return web.json_response({'transaction_hash': tx})


@operations.register
async def get_tx_status(request: Request):
    status = await request.config_dict['feeder_gateway']. \
        get_transaction_status(tx_hash=request.match_info['hash'])
    if status['tx_status'] == Status.NOT_RECEIVED.value:
        return web.HTTPNotFound()

    return web.json_response(status)


@operations.register
async def inspect_tx(request: Request):
    from starkware.starknet.public.abi import get_selector_from_name

    tx = await request.config_dict['feeder_gateway']. \
        get_transaction(tx_hash=request.match_info['hash'])
    if tx['status'] == Status.NOT_RECEIVED.value or \
            parse_int(tx['transaction']['entry_point_selector']) != get_selector_from_name('transfer') or \
            tx['transaction']['entry_point_type'] != 'EXTERNAL':
        return web.HTTPNotFound()

    return web.json_response({
        'function': 'transfer',
        'inputs': dict(zip(
            ['from', 'to', 'amount_or_token_id', 'contract', 'nonce'],
            tx['transaction']['calldata'])),
        'status': tx['status'],
    })


async def upload(request: Request):
    import hashlib
    import mimetypes
    import aiohttp.hdrs

    reader = await request.multipart()
    part = await reader.next()
    if part.name != 'asset':
        return web.HTTPBadRequest()

    extension = mimetypes.guess_extension(part.headers[aiohttp.hdrs.CONTENT_TYPE])
    if not extension:
        return web.HTTPBadRequest()

    data = await part.read()
    asset = f'{hashlib.sha1(data).hexdigest()}{extension}'
    file = request.config_dict['bucket_root'] / asset[:2] / asset[2:4] / asset
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open('wb') as f:
        f.write(data)

    return web.json_response({'asset': asset})


def authenticate(message: list[Union[int, str, bytes]], signature: list[str], stark_key: int) -> bool:
    import hashlib

    message_hash = functools.reduce(
        lambda a, b: pedersen_hash(b, a),
        map(lambda x:
            parse_int(x) if not isinstance(x, bytes) else
            int.from_bytes(hashlib.sha1(x).digest(), byteorder='big'),
            reversed(message)), 0)
    r, s = map(parse_int, signature)

    return verify(message_hash, r, s, stark_key)


@click.command()
@click.option('--port', default=4000, type=int)
def serve(port: int):
    from pathlib import Path
    from .services import async_session

    app = web.Application()
    w3 = Web3()
    app['ether_fluence'] = EtherFluence(
        config('STARK_FLUENCE_CONTRACT_ADDRESS', cast=parse_int), w3)
    app['forwarder'] = Forwarder(
        'FluenceForwarder',
        '0.1.0',
        config('ETHER_FORWARDER_CONTRACT_ADDRESS'),
        config('ETHER_FLUENCE_CONTRACT_ADDRESS'),
        Account.from_key(config('ETHER_PRIVATE_KEY')),
        w3)
    app['feeder_gateway'] = FeederGatewayClient(
        url=config('FEEDER_GATEWAY_URL'),
        retry_config=RetryConfig(n_retries=1))
    app['fluence'] = StarkFluence(
        config('STARK_FLUENCE_CONTRACT_ADDRESS', cast=parse_int),
        app['feeder_gateway'],
        GatewayClient(
            url=config('GATEWAY_URL'),
            retry_config=RetryConfig(n_retries=1)))
    app['async_session'] = async_session

    app['bucket_root'] = Path(config('BUCKET_ROOT'))
    app.add_routes([web.post('/fs', upload),
                    web.static('/fs', app['bucket_root'])])

    from yaml import load
    try:
        from yaml import CLoader as Loader
    except ImportError:
        from yaml import Loader

    schema = load(pkg_resources.resource_string(__name__, 'openapi.yaml'), Loader=Loader)
    setup_openapi(
        app,
        operations,
        schema=schema,
        spec=create_spec(schema),
        cors_middleware_kwargs=dict(allow_all=True))

    web.run_app(app, port=port)
