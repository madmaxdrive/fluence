import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import click
from services.external_api.base_client import BadRequest
from sqlalchemy.exc import NoResultFound
from sqlalchemy.future import select

from fluence.models import Block, Transaction, Contract
from fluence.services import async_session, feeder_client


class BlockCache:
    def __init__(self):
        self.lo = -1
        self.blocks = []

    async def hit(self, block_number):
        lo = int(block_number / 1000)
        if self.lo != lo:
            self.lo = lo
            lo *= 1000

            async with async_session() as session:
                blocks = await session.execute(
                    select(Block.id).
                    where(lo <= Block.id).
                    where(Block.id < lo + 1000))
                self.blocks = [b for b, in blocks]

        return block_number in self.blocks


async def persist_block(document):
    async with async_session() as session:
        block = Block(
            id=document['block_number'],
            hash=document['block_hash'],
            timestamp=datetime.fromtimestamp(document['timestamp'], timezone.utc),
            _document=document)
        session.add(block)

        for receipt, transaction in zip(document['transaction_receipts'], document['transactions']):
            assert receipt['transaction_hash'] == transaction['transaction_hash']
            try:
                (contract,) = (await session.execute(
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


async def crawl_block(block_number: int, cache: BlockCache):
    if await cache.hit(block_number):
        return

    logging.warning(f'crawl_block(block_number={block_number})')
    block = await feeder_client.get_block(block_number=block_number)
    await persist_block(block)


async def do_crawl(to_block):
    block = await feeder_client.get_block(block_hash=to_block)
    i = j = block['block_number'] + 1
    bc = BlockCache()

    loop = asyncio.get_running_loop()
    cd = loop.time()
    while True:
        if to_block is None and cd < loop.time():
            try:
                await crawl_block(j, bc)
                j += 1

                continue
            except BadRequest:
                cd = loop.time() + 15

        if i > 1:
            await crawl_block(i - 1, bc)
            i -= 1

            continue

        await asyncio.sleep(15)


@click.command()
@click.argument('to_block', required=False)
def crawl(to_block):
    asyncio.run(do_crawl(to_block))
