import sys
from setuptools import setup

if sys.version_info[:2] < (3, 5):
    raise NotImplementedError("Required python version 3.5 or greater")

setup(**{
    'name': 'Squall.Gateway',
    'version': '0.1.dev0',
    'namespace_packages': ['squall'],
    'packages': ['squall.gateway'],
    'author': "Alexey Poryadin",
    'author_email': "alexey.poryadin@gmail.com",
    'description': "The addon to the Squall which implements "
                   "gateways to help building async web applications.",
    'install_requires': ['squall'],
})
