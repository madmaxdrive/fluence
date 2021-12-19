import asyncio
import logging
from decimal import Decimal
from typing import Optional

import click
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fluence.models import Account, TokenContract, Token, LimitOrder, Block, Contract
from fluence.models.LimitOrder import Side
from fluence.models.TokenContract import KIND_ERC721
from fluence.models.Transaction import Transaction, TYPE_DEPLOY
from fluence.services import async_session
from fluence.utils import to_address, parse_int


class FluenceInterpreter:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def exec(self, tx: Transaction):
        instructions = {
            '0xe3f5e9e1456ffa52a3fbc7e8c296631d4cc2120c0be1e2829301c0d8fa026b': self.register_contract,
            '0x2a1bcb8fb1380e0c7309c92f894e7b42dc9e72d3d29ce1f8f094d07115ee417': self.register_client,
            '0x2f0b3c5710379609eb5495f1ecd348cb28167711b73609fe565a72734550354': self.mint,
            '0x15511cc3694f64379908437d6d64458dc76d02482052bfb8a5b33a72c054c77': self.withdraw,
            '0xc73f681176fc7b3f9693986fd7b14581e8d540519e27400e88b8713932be01': self.deposit,
            '0x2efcd071f276b825d51002f410e1b0af5b23ef0e9049c5521ca8bc40e178679': self.create_order,
            '0x2d99282b26beeb0e75a3144ef2019a076c60e140c325804ab7f5fa28d6ec5e5': self.fulfill_order,
            '0x1ce71ba7239e3e78e2c0009c4461923344dc98ce84fc1ceb7282704459a14c1': self.cancel_order,
        }
        try:
            await instructions[tx.entry_point_selector](tx)
        except KeyError:
            pass

    async def register_contract(self, tx: Transaction):
        logging.warning(f'register_contract')
        _from_address, contract, kind, _mint = tx.calldata
        token_contract = TokenContract(address=to_address(contract), fungible=int(kind) != KIND_ERC721)
        self.session.add(token_contract)

    async def register_client(self, tx: Transaction):
        logging.warning(f'register_client')
        user, address = tx.calldata[:2]
        await self.lift_account(user, address)

    async def mint(self, tx: Transaction):
        logging.warning(f'mint')
        user, token_id, contract = tx.calldata[:3]
        token = await self.lift_token(token_id, contract)
        token.latest_tx = tx

        token.owner = await self.lift_account(user)

    async def withdraw(self, tx: Transaction):
        logging.warning(f'withdraw')
        _user, amount_or_id, contract, _address = tx.calldata[:4]
        token = await self.lift_token(amount_or_id, contract)
        if token:
            token.owner = None
            token.latest_tx = tx

    async def deposit(self, tx: Transaction):
        logging.warning(f'deposit')
        _from_address, user, amount_or_id, contract = tx.calldata
        account = await self.lift_account(user)
        token = await self.lift_token(amount_or_id, contract)
        if token:
            token.owner = account
            token.latest_tx = tx

    async def create_order(self, tx: Transaction):
        logging.warning(f'create_order')
        order_id, user, bid, base_contract, base_token_id, quote_contract, quote_amount = tx.calldata
        account = await self.lift_account(user)
        token = await self.lift_token(base_token_id, base_contract)
        quote_contract, = (await self.session.execute(
            select(TokenContract).where(TokenContract.address == to_address(quote_contract)))).one()

        limit_order = LimitOrder(
            order_id=Decimal(order_id),
            user=account,
            bid=parse_int(bid) == Side.BID,
            token=token,
            quote_contract=quote_contract,
            quote_amount=Decimal(quote_amount),
            tx=tx)
        self.session.add(limit_order)

        token.ask = limit_order

    async def fulfill_order(self, tx: Transaction):
        logging.warning(f'fulfill_order')
        order_id, user = tx.calldata[:2]
        limit_order, = (await self.session.execute(
            select(LimitOrder).where(LimitOrder.order_id == Decimal(order_id)))).one()
        limit_order.closed_tx = tx
        limit_order.fulfilled = True

        token = limit_order.token
        token.latest_tx = tx
        token.ask = None
        if limit_order.bid:
            token.owner = limit_order.user
        else:
            user = await self.lift_account(user)
            token.owner = user

    async def cancel_order(self, tx: Transaction):
        logging.warning(f'cancel_order')
        order_id, = tx.calldata[:1]
        limit_order, = (await self.session.execute(
            select(LimitOrder).
            where(LimitOrder.order_id == Decimal(order_id)).
            options(selectinload(LimitOrder.token)))).one()
        limit_order.closed_tx = tx
        limit_order.fulfilled = False
        limit_order.token.ask = None

    async def lift_account(self, user: str, address: Optional[str] = None) -> Account:
        user = Decimal(user)

        try:
            account, = (await self.session.execute(
                select(Account).
                where(Account.stark_key == user))).one()
        except NoResultFound:
            account = Account(stark_key=user)
            self.session.add(account)

        if address:
            account.ethereum_address = to_address(address)

        return account

    async def lift_token(self, token_id: str, contract: str) -> Optional[Token]:
        token_id = Decimal(token_id)
        contract = to_address(contract)

        token_contract, = (await self.session.execute(
            select(TokenContract).where(TokenContract.address == contract))).one()
        if token_contract.fungible:
            return None

        try:
            token, = (await self.session.execute(
                select(Token).
                where(Token.token_id == token_id).
                where(Token.contract == token_contract))).one()
        except NoResultFound:
            token = Token(contract=token_contract, token_id=token_id)
            self.session.add(token)

        return token


async def interpret(address: str):
    while True:
        async with async_session() as session:
            try:
                contract, = (await session.execute(
                    select(Contract).where(Contract.address == address))).one()
            except NoResultFound:
                logging.warning('Failed to find contract')
                await asyncio.sleep(15)
                continue

            if contract.block_counter is None:
                try:
                    tx, = (await session.execute(
                        select(Transaction).
                        where(Transaction.contract == contract).
                        where(Transaction.type == TYPE_DEPLOY).
                        options(selectinload(Transaction.block)))).one()

                    contract.block_counter = tx.block.id
                except NoResultFound:
                    logging.warning('Failed to find "DEPLOY"')
                    await asyncio.sleep(15)
                    continue

            try:
                block, = (await session.execute(
                    select(Block).where(Block.id == contract.block_counter))).one()
                interpreter = FluenceInterpreter(session)
                for tx, in await session.execute(
                    select(Transaction).
                    where(Transaction.block == block).
                    where(Transaction.contract == contract).
                    order_by(Transaction.transaction_index)):
                    logging.warning(f'interpret(tx={tx.hash})')
                    await interpreter.exec(tx)

                contract.block_counter += 1
                await session.commit()
            except NoResultFound:
                logging.warning('Failed to find block')
                await asyncio.sleep(15)


@click.command()
@click.argument('contract')
def cli(contract: str):
    asyncio.run(interpret(contract))
