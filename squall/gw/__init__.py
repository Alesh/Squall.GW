""" Gateways from Squall to the web applications
"""
from squall.gw.base import Error as HTTPError  # noqa
from squall.gw.base import Response as BaseResponse  # noqa
from squall.gw.scgi import SCGIGateway  # noqa
