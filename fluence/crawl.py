import asyncio
import logging
from datetime import datetime, timezone

from decouple import config
from services.external_api.base_client import RetryConfig, BadRequest
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient

from fluence.models import Block, Transaction, Contract

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
feeder_client = FeederGatewayClient(
    url=config('FEEDER_GATEWAY_URL'),
    retry_config=RetryConfig(n_retries=1))
engine = create_async_engine(
        config('ASYNC_DATABASE_URL'),
        echo=False,
    )
async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )


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


async def do_crawl():
    block = await feeder_client.get_block()
    i = j = block['block_number']
    bc = BlockCache()

    loop = asyncio.get_running_loop()
    cd = loop.time()
    while True:
        if cd < loop.time():
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


def crawl():
    asyncio.run(do_crawl())
