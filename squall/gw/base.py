import sys
import logging
from traceback import format_exception
from urllib.parse import unquote_plus as unquote
from http.server import BaseHTTPRequestHandler as BRH
from squall.utils import timeout_gen
from squall.iostream import IOStream


logger = logging.getLogger('squall.gateway')


class Status(str):
    """ HTTP respanse status
    """
    def __new__(cls, code, reason=None):
        if reason is None:
            reason = BRH.responses.get(code, ('', ''))[0] or 'Undefined'
        self = super(Status, cls).__new__(cls, '{} {}'.format(code, reason))
        self._code = code
        return self

    @property
    def code(self):
        """ Response status code"""
        return self._code


class Response(object):
    """ Base class of HTTP responses and errors
    """
    def __init__(self, status_code, headers=[]):
        self.set_status(status_code)
        self._headers = headers

    @property
    def status(self):
        """ Response status """
        return self._status

    @property
    def headers(self):
        """ Response headers """
        return self._headers

    def set_status(self, code, reason=None):
        """ Sets response status.
        """
        if reason is None:
            reason = BRH.responses.get(code, ('', ''))[0] or 'Error'
        self._status = Status(code, reason)

    def add_header(self, name, value):
        """ Adds response header.
        """
        name = '-'.join(map(lambda a: a.capitalize(), name.split('-')))
        self._headers.append((name, value))

    def clear_header(self, name):
        """ Removes response header with given `name`.
        """
        name = '-'.join(map(lambda a: a.capitalize(), name.split('-')))
        self._headers = [(name_, value)
                         for name_, value in self._headers if name == name_]

    def set_header(self, name, value):
        """ Sets response header.
        """
        self.clear_header(name)
        self.add_header(name, value)


class Error(Exception, Response):
    """ HTTP error
    """
    def __init__(self, code, msg=None, headers=[], reason=None):
        Response.__init__(self, code, headers)
        if reason is not None:
            Response.set_status(self, code, reason)
        msg = '{}{}'.format(self.status, ('' if msg is None
                                          else ' ({})'.format(msg)))
        Exception.__init__(self, msg)


class StartResponse(object):
    """ start_response helper
    """
    def __init__(self, stream, protocol=None, timeout=None):
        isinstance(stream, IOStream)
        self._stream = stream
        self._tg = timeout_gen(timeout)
        self._headers_set = list()
        self._charset = 'ISO-8859-1'
        self.protocol = protocol
        self.headers_sent = list()

    def __call__(self, status, response_headers, exc_info=None):
        if exc_info:
            try:
                if self.headers_sent:
                    raise exc_info[1].with_traceback(exc_info[2])
            finally:
                exc_info = None
        elif self._headers_set:
            raise AssertionError("Headers already set!")
        self._headers_set[:] = [status, response_headers]
        return self.write

    @property
    def timeout(self):
        """ Response timeout
        """
        return next(self._tg)

    async def write(self, data=None, *, flush=False):
        """ Async writes response body
        """
        headers = None
        if not self._headers_set:
            raise AssertionError("write() before start_response()")
        if not self.headers_sent:
            status, response_headers = self.headers_sent[:] = self._headers_set
            if self.protocol is not None:
                headers = '{} {}\r\n'.format(self.protocol, status)
            else:
                headers = 'Status: {}\r\n'.format(status)
            for name, value in response_headers:
                if name.lower() == 'content-type':
                    part = value.split('charset=')
                    if len(part) == 2:
                        self._charset = part[1]
                headers += '{}: {}\r\n'.format(name, value)
            headers += '\r\n'
            headers = headers.encode('ISO-8859-1')

        if data is not None:
            if isinstance(data, str):
                data = data.encode(self._charset)
            elif not isinstance(data, bytes):
                raise ValueError("Cannot write data of type `{}`"
                                 "".format(type(data)))
            if headers is not None:
                data = headers + data
        elif headers is not None:
            data = headers

        if data is not None:
            while True:
                sent = self._stream.write(data)
                if sent < len(data):
                    await self._stream.flush(timeout=self.timeout)
                    data = data[sent:]
                    continue
                break
        if flush:
            await self._stream.flush(timeout=self.timeout)


class Gateway(object):
    """ Base async gateway
    """
    def __init__(self, application, *, debug=False):
        self.app = application
        self.debug = debug

    async def __call__(self, environ, start_response):
        """ Request handler
        """
        assert isinstance(start_response, StartResponse)
        environ['PATH_INFO'] = unquote(environ['PATH_INFO'])
        environ['SCRIPT_NAME'] = unquote(environ.get('SCRIPT_NAME', ''))
        try:
            await self.app(environ, start_response)
        except Exception as exc:
            if not isinstance(exc, Error):
                if isinstance(exc, TimeoutError):
                    exc = Error(408, str(exc))
                else:
                    exc = Error(500, str(exc))
            exc_info = sys.exc_info()
            start_response(exc.status, exc.headers, exc_info)
            if self.debug and exc.status.code == 500:
                exc.set_header('Content-Type', 'text/plain; charset=UTF-8')
                body = '{}\r\n{}'.format(exc,
                                         ''.join(format_exception(*exc_info)))
                await start_response.write(body)
                logger.exception(exc, extra={'ip': environ.get('REMOTE_ADDR')})
        finally:
            await start_response.write(flush=True)

    def _make_environ(self, stream, addr):
        isinstance(stream, IOStream)
        return {
            'squall.version': (1, 0),
            'squall.read_bytes': stream.read_bytes,
            'squall.read_until': stream.read_until,
            'REMOTE_ADDR': addr[0],
            'REMOTE_PORT': addr[1]
        }
