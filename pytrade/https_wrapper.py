# coding=utf-8
import socketserver
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import os
from publicsuffix import PublicSuffixList
from contextlib import closing

from .certutil import CertManager
from . import ssl_config
from .ssl_config import *
from .const import *
from .models import *

verbose=None
pyi=None
def setup(pyinstance_,verbose_):
    global verbose
    global pyi
    verbose=verbose_
    pyi=pyinstance_


_psl=None
def normdomain(domain):
    global _psl

    if _psl is None:
        _psl=PublicSuffixList(open(ssl_config.psl_filename, encoding='utf-8'))

    suf=_psl.get_public_suffix(domain)
    return domain if domain==suf else '*.%s'%suf


class MultithreadServer(socketserver.ThreadingMixIn, HTTPServer):
    pass


def base_fetcher(req,responder,method,url,headers,body):
    try:
        the_response=sess.request(method=method,url=url,headers=headers,data=body)
    except Exception as e:
        pyerr=PyError(req,pyi,sys.exc_info(),
            responder.send_response,responder.send_header,responder.fake_write,responder.fake_finish,responder.wfile.flush)
        cmd=pyi.err_callback(req, e, pyerr)
        if isinstance(cmd,Response):
            if pyi.verbose>=Verbose:
                print('<-! #%4d Exception Response %s %dB %s'%(req._count,' '.join(map(str, cmd.status)),len(cmd.body),req.url))

            responder.send_response(*cmd.status)
            for k, v in cmd.headers.items():
                responder.send_header(k,v)
            responder.fake_write(cmd.body)
        return
    try:
        with closing(the_response) as res:
            responder.send_response(res.status_code, res.reason)
            for k,v in res.headers.items():
                if k not in ['Connection','Transfer-Encoding']:
                    responder.send_header(k, v)
            responder.end_headers()
            for content in res.raw.stream(chunksize, decode_content=False):
                responder.wfile.write(content)
    except Exception as e:
        pyerr=PyError(req,pyi,sys.exc_info(),
            responder.send_response,responder.send_header,responder.fake_write,responder.fake_finish,responder.wfile.flush)
        default_err_handler(req,e,pyerr)


class MyHandler(BaseHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.header_sent=False

    def fake_write(self,x):
        if not self.header_sent:
            self.end_headers()
            self.header_sent=True

        if isinstance(x, str):
            self.wfile.write(x.encode(errors='ignore'))
        else:
            self.wfile.write(x)

    def fake_finish(self,x=None):
        if x is not None:
            self.fake_write(x)
        # warning: we should NOT finish the request

    def do_GET(self):
        url='https://%s%s' % (self.headers['Host'],self.path)
        body=self.rfile.read(int(self.headers.get('Content-Length',0)))  # fixme: post request without content-length

        req=Req(self.command,url,self.headers,body or b'',pyi.counter)
        py=PyRequest(req,pyi,self.send_response,self.send_header,self.fake_write,self.fake_finish,self.wfile.flush)
        if pyi.verbose >= Verbose:
            py.log()
        try:
            cmd=pyi.req_callback(req,py)
        except Exception as e:
            pyerr=PyError(req,pyi,sys.exc_info(),self.send_response,self.send_header,self.fake_write,self.fake_finish,self.wfile.flush)
            default_err_handler(req,e,pyerr)
            if not pyerr._finished_flag:
                pyerr.finish()
            return

        if cmd==Go or cmd==Pass:
            assert not py._tamper_flag, 'cannot forward request when PY is tampered'
            base_fetcher(req,self,self.command,url,self.headers,body)

        elif cmd==Halt:
            if pyi.verbose>=Verbose:
                print('<-H #%4d (Halted) %s' % (req._count, req.url))

        elif isinstance(cmd, Response):
            if pyi.verbose>=Verbose:  # todo: encode to bytes before calc length
                print('<-F #%4d (Faked: %s %sB) %s'%(req._count,' '.join(map(str, cmd.status)),len(cmd.body),req.url))

            self.send_response(*cmd.status)
            for k, v in cmd.headers.items():
                self.send_header(k, v)
            self.wfile.write(cmd.body)

        else:
            raise RuntimeError('bad request callback value %r' % cmd)

    do_POST=do_GET
    do_HEAD=do_GET
    do_DELETE=do_GET
    do_PATCH=do_GET
    do_PUT=do_GET
    do_OPTIONS=do_GET

    def log_message(self, *_):
        pass  # default server log


cache = {}


def create_wrapper(host):
    if cert_wildcard:
        host = normdomain(host)
    if host in cache:
        return cache[host]

    ssl_check, fdomain = CertManager().generate(host)
    httpsd = MultithreadServer(('127.0.0.1', 0), MyHandler)

    if not ssl_check:
        print('https_wrapper: gen cert failed. using CA instead.')
        httpsd.socket = ssl.wrap_socket(httpsd.socket, certfile=ssl_config.ca_pem_file, server_side=True)
    else:
        sslcontext = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        sslcontext.load_cert_chain(
            os.path.join(ssl_config.key_dir, fdomain + '.crt'),
            keyfile=os.path.join(ssl_config.key_dir, fdomain + '.key')
        )
        httpsd.socket = sslcontext.wrap_socket(httpsd.socket, server_side=True)

    # httpsd.handle_error=lambda *_: None #suppress annoying "ValueError: I/O operation on closed file"
    port = httpsd.socket.getsockname()[1]
    threading.Thread(target=httpsd.serve_forever).start()

    print('https_wrapper: wrapping %s on port %d' % (host, port))
    cache[host] = port
    return port