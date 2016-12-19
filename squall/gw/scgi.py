""" SCGI gateway
"""
from squall.utils import timeout_gen
from squall.network import SocketStream, TCPServer
from squall.gw.base import Gateway, StartResponse, logger


class SCGIGateway(Gateway, TCPServer):
    """ SCGI gateway/server
    """
    def __init__(self, application, *, block_size=2048, buffer_size=65536,
                 accept_timeout=0.5, request_timeout=15, response_timeout=60,
                 on_listen=None, on_finish=None, debug=False, disp=None):
        self.accept_timeout = accept_timeout
        self.request_timeout = request_timeout
        self.response_timeout = response_timeout
        self.stream_kwargs = dict(block_size=block_size,
                                  buffer_size=buffer_size)
        Gateway.__init__(self, application, debug=debug)
        TCPServer.__init__(self, disp=disp,
                           on_listen=on_listen, on_finish=on_finish)

    def _connection_factory(self, disp, sock, addr):
        stream = SocketStream(disp, sock, **self.stream_kwargs)
        environ = {
            'squall.version': (1, 0),
            'squall.read_bytes': stream.read_bytes,
            'squall.read_until': stream.read_until,
            'REMOTE_ADDR': addr[0],
            'REMOTE_PORT': addr[1]
        }
        return environ, stream

    async def _connection_handler(self, environ, stream):
        try:
            data = await stream.read_until(b':', max_number=16,
                                           timeout=self.accept_timeout)
            if data[-1] != ord(b':'):
                raise ValueError("Wrong header size")
            request_tg = timeout_gen(self.request_timeout)
            start_response = StartResponse(stream,
                                           timeout=self.response_timeout)
            data = await stream.read_bytes(int(data[:-1]) + 1,
                                           timeout=next(request_tg))
            if data[-1] != ord(b','):
                raise ValueError("Wrong header format")
            items = data.decode('ISO-8859-1').split('\000')
            environ.update(dict(zip(items[::2], items[1::2])))
            environ['squall.request_tg'] = request_tg
            await self(environ, start_response)
        except Exception as exc:
            if self.debug:
                logger.exception("Connection fail",
                                 extra={'ip': environ['REMOTE_ADDR']})
            else:
                logger.warning("Connection fail: %s", exc,
                               extra={'ip': environ['REMOTE_ADDR']})
        finally:
            stream.abort()
