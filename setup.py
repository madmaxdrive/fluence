from setuptools import setup, find_packages

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
        ],
    },
)
