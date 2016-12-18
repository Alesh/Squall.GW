import jinja2
import os.path
import logging
import urllib.parse
from squall.gateway import SCGIGateway, HTTPError, BaseResponse


def unquote(data):
    return urllib.parse.unquote_plus(data)


def parse_qs(qs):
    result = dict()
    for name, value in urllib.parse.parse_qs(qs).items():
        if len(value) < 2:
            result[name] = value[0]
        else:
            result[name] = value
    return result


async def index(self):
    await hello(self)

async def hello(self, name="World"):
    await self.render('hello.html', name=name)

async def environ(self, **kwargs):
    await self.render('environ.html', environ=self.env)


class Response(BaseResponse):
    """ HTTP response with support jinja2 templates
    """
    def __init__(self, environ, start_response, template_engine):
        self._write = None
        self._environ = environ
        self._start = start_response
        self._te = template_engine
        super().__init__(200)

    @property
    def env(self):
        """ Request environ """
        return self._environ

    async def write(self, data):
        """ Writes response data.
        """
        if self._write is None:
            self._write = self._start(self.status, self.headers)
        await self._write(data)

    async def render(self, filename, **kwargs):
        if self._write is not None:
            raise HTTPError(500, "Cannot more write")
        self.set_header('Content-Type', 'text/html; charset=UTF-8')
        template = self._te.get_template(filename)
        for chunk in template.stream(**kwargs):
            await self.write(chunk)


class Application(object):
    """ Web applications
    """

    def __init__(self, debug):
        self.map = {
            '': index,
            'index.html': index,
            'hello.html': hello,
            'environ.html': environ,
        }
        self.debug = debug
        loader = jinja2.FileSystemLoader(
            os.path.join(os.path.dirname(__file__), 'templates'))
        self.template_engine = jinja2.Environment(loader=loader)

    async def __call__(self, environ, start_response):
        """ Request handler
        """
        kwargs = {}
        key, *args = environ['PATH_INFO'].split('/')[1:]
        action = self.map.get(key, None)
        if action is None:
            raise HTTPError(404)
        qs = environ.get('QUERY_STRING')
        if qs:
            getargs = parse_qs(qs)
            if getargs:
                kwargs.update(getargs)
        content_type = environ.get('CONTENT_TYPE')
        content_length = int(environ.get('CONTENT_LENGTH') or 0)
        if content_type and content_length > 0:
            if content_type == 'application/x-www-form-urlencoded':
                tg = environ['squall.request_tg']
                read_bytes = environ['squall.read_bytes']
                qs = await read_bytes(content_length, timeout=next(tg))
                if qs:
                    postargs = parse_qs(unquote(qs.decode('ISO-8859-1')))
                    if postargs:
                        kwargs.update(postargs)
        try:
            resp = Response(environ, start_response, self.template_engine)
            await action(resp, *args, **kwargs)
        except TypeError:
            if self.debug:
                logging.exception("Error while parse request")
            if action.__code__.co_argcount < len(args) + 1:
                raise HTTPError(404)
            else:
                raise HTTPError(400)


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=9000,
                        help="sets number of listen port")
    parser.add_argument('--debug', action='store_true',
                        help="activates debug mode")
    parser.add_argument('-w', '--workers', type=int, default=0,
                        help="number of workers; default equal cpu cores")
    parser.add_argument('-b', '--backlog', type=int, default=128,
                        help="size of incomming request backlog queue")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)

    SCGIGateway(Application(args.debug),
                debug=args.debug).start(args.port,
                                        backlog=args.backlog,
                                        workers=args.workers)
