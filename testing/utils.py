#coding=utf-8
__all__=['s','server','SERVER']

import pytest
import sys
sys.path.append('..')

from pytrade.proxy import Proxy
from pytrade import *

import threading
import requests
import socketserver
from http.server import HTTPServer, BaseHTTPRequestHandler
import zlib

class MultithreadServer(socketserver.ThreadingMixIn, HTTPServer):
    pass

class TestSeverHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith('?test-drop-connection'):
            return self.wfile.close()

        self.send_response(200,'OK')
        self.send_header('content-type','text/plain')
        self.send_header('content-encoding','deflate')
        self.send_header('x-original-header','original header')
        self.end_headers()
        self.wfile.write(zlib.compress((
            'hello world. url = [%s]; headers = [%s]; body = [%s]'%(
                self.path,
                '&'.join(sorted(self.headers)),
                self.rfile.read(int(self.headers.get('Content-Length',0)))
        )).encode()))
        self.wfile.close()

    do_POST=do_GET

    def log_message(self, *_):
        pass

@pytest.fixture(scope='session')
def server(request):
    httpd=MultithreadServer(('0.0.0.0',28567),TestSeverHandler)
    httpd.handle_error=lambda *_: None #suppress "ValueError: I/O operation on closed file"
    server_thread=threading.Thread(target=httpd.serve_forever)
    server_thread.start()

    def fin():
        httpd.shutdown()
        server_thread.join()

    request.addfinalizer(fin)

@pytest.fixture(scope='module')
def s(request,server):
    module_items=dir(request.module)
    args={}
    if 'on_request' in module_items:
        args['request']=request.module.on_request
    if 'on_response' in module_items:
        args['response']=request.module.on_response
    if 'on_connect' in module_items:
        args['connect']=request.module.on_connect
    if 'on_error' in module_items:
        args['error']=request.module.on_error

    pro=Proxy.from_friendly_args(8765,logging=request.module.logging if 'logging' in module_items else Verbose,**args)
    proxy_thread=threading.Thread(target=pro.run)
    proxy_thread.start()

    s=requests.session()
    s.proxies={'http':'http://127.0.0.1:8765','https':'http://127.0.0.1:8765'}

    if 'init' in module_items:
        request.module.init()

    def fin():
        pro.ioloop.add_callback(pro.ioloop.stop)
        proxy_thread.join()
        pro.server.stop()

    request.addfinalizer(fin)
    return s

SERVER='http://127.0.0.1:28567/'