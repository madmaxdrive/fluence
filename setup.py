from setuptools import setup

setup(
    name='fluence',
    version='0.0.1',
    packages=['fluence'],
    package_data={
        'fluence': ['abi/*'],
    },
    install_requires=[
        'aiohttp',
        'aiohttp-sqlalchemy',
        'asyncpg',
        'cairo-lang',
        'click',
        'py-eth-sig-utils',
        'python-decouple',
        'sqlalchemy',
    ],
    entry_points={
        'console_scripts': [
            'crawl = fluence.crawl:crawl',
            'interpret = fluence.interpret:cli',
            'serve = fluence.serve:serve',
            'stark = fluence.stark_key:cli',
        ],
    },
)
