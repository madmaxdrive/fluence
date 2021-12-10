import logging

from decouple import config
from services.external_api.base_client import RetryConfig
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from starkware.starknet.services.api.feeder_gateway.feeder_gateway_client import FeederGatewayClient


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
