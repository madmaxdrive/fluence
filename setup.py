from setuptools import setup

setup(
    name='fluence',
    version='0.0.1',
    packages=['fluence'],
    install_requires=[
        'aiohttp',
        'cairo-lang',
        'click',
        'python-decouple',
    ],
    entry_points={
        'console_scripts': [
            'serve = fluence.serve:serve',
            'stark = fluence.stark_key:cli',
        ],
    },
)
