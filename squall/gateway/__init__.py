""" Gateways from Squall to the web applications
"""
from squall.gateway.base import Error as HTTPError  # noqa
from squall.gateway.base import Response as BaseResponse  # noqa
from squall.gateway.scgi import SCGIGateway  # noqa
