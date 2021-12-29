from setuptools import setup

setup(
    name='fluence',
    version='0.0.1',
    packages=['fluence'],
    package_data={
        'fluence': ['openapi.yaml'],
        'fluence.contracts': ['abi/*'],
    },
    install_requires=[
        'aiohttp',
        'aiohttp-sqlalchemy',
        'asyncpg',
        'cairo-lang',
        'click',
        'jsonschema',
        'marshmallow',
        'pendulum',
        'py-eth-sig-utils',
        'python-decouple',
        'PyYAML',
        'rororo',
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
