import functools
from typing import Union

from aiohttp import web
from aiohttp.web_request import Request
from decouple import config
from eth_account import Account
from jsonschema.exceptions import ValidationError
from services.external_api.base_client import RetryConfig
from sqlalchemy import select, null, true
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import functions
from starkware.crypto.signature.fast_pedersen_hash import pedersen_hash
from starkware.crypto.signature.signature import verify
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient
from starkware.starknet.services.api.gateway.gateway_client import GatewayClient
from web3 import Web3

from fluence.contracts import ERC721Metadata
from fluence.contracts.fluence import StarkFluence, LimitOrder, EtherFluence, ContractKind
from fluence.contracts.forwarder import Forwarder, ReqSchema
from fluence.utils import parse_int

routes = web.RouteTableDef()


@routes.get('/contracts')
async def get_contracts(request: Request):
    return web.json_response({
        'fluence': request.config_dict['forwarder'].to_address,
        'forwarder': request.config_dict['forwarder'].address,
    })


@routes.post('/blueprints')
async def create_blueprint(request: Request):
    data = await request.json()
    if not authenticate(
            [data['permanent_id'].encode()],
            request.query['signature'],
            data['minter']):
        return web.HTTPUnauthorized()

    async with request.config_dict['async_session']() as session:
        from fluence.models import Account, Blueprint, BlueprintSchema

        try:
            minter = (await session.execute(
                select(Account).
                where(Account.stark_key == data['minter']))).scalar_one()
        except NoResultFound:
            minter = Account(stark_key=data['minter'])
            session.add(minter)

        blueprint = Blueprint(
            permanent_id=data['permanent_id'],
            minter=minter,
            expire_at=None)
        session.add(blueprint)
        await session.commit()

        return web.json_response(BlueprintSchema().dump(blueprint))


@routes.get('/_metadata/{permanent_id}/{token_id}')
async def get_metadata_by_permanent_id(request: Request):
    async with request.config_dict['async_session']() as session:
        from fluence.models import Token, TokenContract, Blueprint

        token = (await session.execute(
            select(Token).
            join(Token.contract).
            join(TokenContract.blueprint).
            where(Token.token_id == parse_int(request.match_info['token_id'])).
            where(Blueprint.permanent_id == request.match_info['permanent_id']))).sclar_one()

        return web.json_response(token.asset_metadata)


@routes.get('/collections')
async def get_collections(request: Request):
    page = parse_int(request.query.get('page', '1'))
    size = parse_int(request.query.get('size', '100'))
    owner = request.query.get('owner')

    async with request.config_dict['async_session']() as session:
        from fluence.models import TokenContract, Account, Blueprint

        def augment(stmt):
            stmt = stmt.where(TokenContract.fungible == true())
            if owner:
                stmt = stmt.join(TokenContract.minter). \
                    where(Account.address == owner)

            return stmt

        query = augment(select(TokenContract)).limit(size).offset(size * (page - 1))
        count = augment(select(functions.count()).select_from(LimitOrder))

        return web.json_response({
            'data': list(map(
                TokenContract().dump,
                (await session.execute(
                    query.options(
                        selectinload(TokenContract.blueprint).selectinload(Blueprint.account)))).scalars())),
            'total': (await session.execute(count)).scalar_one(),
        })


@routes.post('/collections')
async def register_collection(request: Request):
    data = await request.json()
    async with request.config_dict['async_session']() as session:
        from fluence.models import TokenContract, Account, Blueprint

        if 'blueprint' in data:
            blueprint = (await session.execute(
                select(Blueprint).
                where(Blueprint.permanent_id == data['blueprint']).
                options(
                    selectinload(Blueprint.minter),
                    selectinload(Blueprint.contract)))).scalar_one()
            if blueprint.contract:
                return web.HTTPBadRequest()
        else:
            minter = parse_int(data['minter'])
            try:
                account = (await session.execute(
                    select(Account).
                    where(Account.address == minter))).scalar_one()
            except NoResultFound:
                account = Account(stark_key=data['minter'])
                session.add(account)

            blueprint = Blueprint(account)
            session.add(blueprint)

        if not authenticate(
                [data['address'], data['name'], data['symbol'], data['base_uri']],
                request.query['signature'],
                int(blueprint.minter.stark_key)):
            return web.HTTPUnauthorized()

        req, signature = request.config_dict['forwarder'].forward(
            *request.config_dict['ether_fluence'].register_contract(
                data['address'], ContractKind.ERC721, int(blueprint.minter.stark_key)))

        token_contract = TokenContract(
            address=data['address'],
            fungible=True,
            blueprint=blueprint,
            name=data['name'],
            symbol=data['symbol'],
            decimals=0,
            base_uri=data['base_uri'])
        session.add(token_contract)
        await session.commit()

        return web.json_response({
            'req': ReqSchema().dump(req),
            'signature': signature,
        })


@routes.get('/clients')
async def get_client(request: Request):
    stark_key = await request.config_dict['fluence']. \
        get_client(request.query['address'])

    return web.json_response({'stark_key': str(stark_key)})


@routes.post('/clients')
async def register_client(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].register_client(
        data['stark_key'],
        data['address'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/balance')
async def get_balance(request: Request):
    balance = await request.config_dict['fluence'].get_balance(
        request.query['user'],
        request.query['contract'])

    return web.json_response({'balance': str(balance)})


@routes.get('/owner')
async def get_owner(request: Request):
    owner = await request.config_dict['fluence'].get_owner(
        request.query['token_id'],
        request.query['contract'])

    return web.json_response({'owner': str(owner)})


@routes.post('/mint')
async def mint(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].mint(
        data['user'],
        data['amount_or_token_id'],
        data['contract'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/collections/{address}/tokens/{token_id}/_metadata')
async def get_metadata(request: Request):
    async with request.config_dict['async_session']() as session:
        from fluence.models import TokenContract, Token

        token = (await session.execute(
            select(Token).
            join(Token.contract).
            where(Token.token_id == parse_int(request.match_info['token_id'])).
            where(TokenContract.address == request.match_info['address']))).scalar_one()

        return web.json_response(token.asset_metadata)


@routes.put('/collections/{address}/tokens/{token_id}/_metadata')
async def update_metadata(request: Request):
    metadata = await request.json()
    try:
        ERC721Metadata.validate(metadata)
    except ValidationError:
        return web.HTTPBadRequest

    async with request.config_dict['async_session']() as session:
        from fluence.models import TokenContract, Token, TokenSchema

        token_contract, = (await session.execute(
            select(TokenContract).
            where(TokenContract.address == request.match_info['address']).
            options(selectinload(TokenContract.minter)))).one()
        token_id = parse_int(request.match_info['token_id'])
        try:
            token, = (await session.execute(
                select(Token).
                where(Token.token_id == token_id).
                where(Token.contract == token_contract).
                options(selectinload(Token.contract)))).one()
        except NoResultFound:
            token = Token(contract=token_contract, token_id=token_id, nonce=0)
            session.add(token)

        message_hash = \
            pedersen_hash(parse_int(token_contract.address),
                          pedersen_hash(token_id,
                                        pedersen_hash(token.nonce, 0)))
        r, s = map(parse_int, request.query['signature'].split(','))
        if not verify(message_hash, r, s, int(token_contract.minter.stark_key)):
            return web.HTTPUnauthorized()

        token.name = metadata['name']
        token.description = metadata['description']
        token.image = metadata['image']
        token.asset_metadata = metadata

        await session.commit()

        return web.json_response(TokenSchema().dump(token))


@routes.post('/withdraw')
async def withdraw(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].withdraw(
        data['user'],
        data['amount_or_token_id'],
        data['contract'],
        data['address'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/orders')
async def get_orders(request: Request):
    page = parse_int(request.query.get('page', '1'))
    size = parse_int(request.query.get('size', '100'))
    user = request.query.get('user')
    collection = request.query.get('collection')
    side = request.query.get('side')
    state = request.query.get('state')

    async with request.config_dict['async_session']() as session:
        from fluence.models import LimitOrder, LimitOrderSchema, State, Account, Token, TokenContract

        def augment(stmt):
            if user:
                stmt = stmt.join(LimitOrder.user). \
                    where(Account.address == user)
            if collection:
                stmt = stmt.join(LimitOrder.token). \
                    join(Token.contract). \
                    where(TokenContract.address == collection)
            if side in ['ask', 'bid']:
                stmt = stmt.where(LimitOrder.bid == (side == 'bid'))
            if state:
                stmt = stmt.where(LimitOrder.fulfilled == [null(), True, False][State(parse_int(state))])

            return stmt

        query = augment(select(LimitOrder)).limit(size).offset(size * (page - 1))
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


@routes.get('/orders/{id}')
async def get_order(request: Request):
    limit_order = await request.config_dict['fluence']. \
        get_order(request.match_info['id'])

    return web.json_response(limit_order._asdict())


@routes.put('/orders/{id}')
async def create_order(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].create_order(
        request.match_info['id'],
        LimitOrder(**data, state=0),
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.delete('/orders/{id}')
async def cancel_order(request: Request):
    tx = await request.config_dict['fluence'].cancel_order(
        request.match_info['id'],
        request.query['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.post('/orders/{id}')
async def fulfill_order(request: Request):
    data = await request.json()
    tx = await request.config_dict['fluence'].fulfill_order(
        request.match_info['id'],
        data['user'],
        data['nonce'],
        request.query['signature'].split(','))

    return web.json_response({'transaction_hash': tx})


@routes.get('/tx/{hash}/_status')
async def get_tx_status(request: Request):
    status = await request.config_dict['feeder_gateway']. \
        get_transaction_status(request.match_info['hash'])

    return web.json_response(status)


def authenticate(message: list[Union[int, str, bytes]], signature: str, stark_key: int) -> bool:
    import hashlib

    message_hash = functools.reduce(
        lambda a, b: pedersen_hash(b, a),
        map(lambda x:
            parse_int(x) if not isinstance(x, bytes) else
            int.from_bytes(hashlib.sha1(x).digest(), byteorder='big'),
            reversed(message)), 0)
    r, s = map(parse_int, signature.split(','))

    return verify(message_hash, r, s, stark_key)


def serve():
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

    v1 = web.Application()
    v1.add_routes(routes)
    app.add_subapp('/api/v1', v1)

    web.run_app(app, port=4000)
