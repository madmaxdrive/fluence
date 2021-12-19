import asyncio
import logging
from datetime import datetime, timezone

import click
from services.external_api.base_client import BadRequest
from sqlalchemy.exc import NoResultFound
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient

from fluence.models import Block, Transaction, Contract


class BlockCache:
    def __init__(self, async_session: sessionmaker):
        self._lo = -1
        self._blocks = []
        self._async_session = async_session

    async def hit(self, block_number):
        lo = int(block_number / 1000)
        if self._lo != lo:
            self._lo = lo
            lo *= 1000

            async with self._async_session() as session:
                blocks = await session.execute(
                    select(Block.id).
                    where(lo <= Block.id).
                    where(Block.id < lo + 1000))
                self._blocks = [b for b, in blocks]

        return block_number in self._blocks


class Crawler:
    def __init__(self, feeder: FeederGatewayClient, async_session: sessionmaker, cooldown: float):
        self._feeder = feeder
        self._async_session = async_session
        self._block_cache = BlockCache(async_session)
        self._cooldown = cooldown

    async def run(self, thru):
        block = await self._feeder.get_block(block_hash=thru)
        i = j = block['block_number'] + 1

        loop = asyncio.get_running_loop()
        cd = loop.time()
        while True:
            if thru is None and cd < loop.time():
                try:
                    await self._crawl(j)
                    j += 1

                    continue
                except BadRequest:
                    cd = loop.time() + self._cooldown

            if i > 1:
                await self._crawl(i - 1)
                i -= 1

                continue

            await asyncio.sleep(self._cooldown)

    async def _crawl(self, block_number: int):
        if await self._block_cache.hit(block_number):
            return

        logging.warning(f'crawl_block(block_number={block_number})')
        await self._persist(await self._feeder.get_block(block_number=block_number))

    async def _persist(self, document):
        async with self._async_session() as session:
            block = Block(
                id=document['block_number'],
                hash=document['block_hash'],
                timestamp=datetime.fromtimestamp(document['timestamp'], timezone.utc),
                _document=document)
            session.add(block)

            for receipt, transaction in zip(document['transaction_receipts'], document['transactions']):
                assert receipt['transaction_hash'] == transaction['transaction_hash']
                try:
                    contract, = (await session.execute(
                        select(Contract).
                        where(Contract.address == transaction['contract_address']))).one()
                except NoResultFound:
                    contract = Contract(address=transaction['contract_address'])
                    session.add(contract)

                tx = Transaction(
                    hash=transaction['transaction_hash'],
                    block=block,
                    transaction_index=receipt['transaction_index'],
                    type=transaction['type'],
                    contract=contract,
                    entry_point_selector=transaction.get('entry_point_selector'),
                    entry_point_type=transaction.get('entry_point_type'),
                    calldata=transaction['calldata' if transaction['type'] != 'DEPLOY' else 'constructor_calldata'])
                session.add(tx)

            await session.commit()


@click.command()
@click.argument('thru', required=False)
def crawl(thru):
    from fluence.services import async_session, feeder_client

    crawler = Crawler(feeder_client, async_session, 15)
    asyncio.run(crawler.run(thru))
