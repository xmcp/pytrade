#coding=utf-8

import tornado.httpserver
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.httpclient
import tornado.httputil

import socket
import requests
import threading
from contextlib import closing

from pytrade.const import *
from pytrade.models import *


def is_cmd(x):
    return x==Pass or x==Go or x==Halt or isinstance(x,Response)


def default_err_handler(req,e,py:PyError):
    py.log()
    py.set_status(500)
    py.add_header('content-type','text/plain')
    py.finish('Internal server error:\n'+str(e))


sess=requests.Session()
sess.trust_env=False #disable original proxy
thread_adapter=requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
sess.mount('http://', thread_adapter)


def _async(f):
    def _real(*__,**_):
        threading.Thread(target=f,args=__,kwargs=_).start()
    return _real

@_async
def tornado_fetcher(pyi, req, callback, setstatus, addheader, putdata, finish, flush):
    ioloop=pyi.ioloop
    try:
        with closing(sess.request(
                req.method, req.url, headers=req.headers, data=req.body,
                stream=True, allow_redirects=False, timeout=30,
            )) as r:

            res=Res(r)
            py=PyResponse(req,res,pyi,setstatus,addheader,putdata,finish,flush)
            cmd=callback(req,res,py) if callback is not None else Go

            if cmd==Go:
                if pyi.verbose>=Verbose:
                    py.log()
                assert not py._tamper_flag, 'cannot forward original response when PY is tampered'
                if res._decoded_flag and 'content-encoding' in res.headers:
                    del res.headers['content-encoding']
                    res.headers['content-length']=sum(map(len,res._content_bkp))

                ioloop.add_callback(setstatus,res.code,res.reason)
                for k,v in res.headers.items():
                    if k.lower() not in ['connection','transfer-encoding']:
                        ioloop.add_callback(addheader,k,v)

                for content in res._content_bkp if res._content_bkp else r.raw.stream(64*1024, False):
                    if content:
                        ioloop.add_callback(putdata,content)
                ioloop.add_callback(finish)

            elif cmd==Halt:
                if pyi.verbose>=Verbose:
                    print('<-H #%4d (Halted) %s %s (%sB) %s'%\
                        (req._count,res.code,res.reason,res.headers.get('content-length','?'),req.url))
                if not py._finished_flag:
                    ioloop.add_callback(finish)

            elif isinstance(cmd,Response):
                if pyi.verbose>=Verbose:
                    print('<-F #%4d (Faked: %s %sB) %s %s (%sB) %s'%\
                        (req._count,' '.join(map(str,cmd.status)),len(cmd.body),res.code,res.reason,res.headers.get('content-length','?'),req.url))

                ioloop.add_callback(setstatus,*cmd.status)
                for k,v in cmd.headers.items():
                    ioloop.add_callback(addheader,k,v)
                ioloop.add_callback(finish,cmd.body)

            else:
                raise RuntimeError('bad response callback value %r'%cmd)

    except Exception as e:
        pyerr=PyError(req, pyi, e, setstatus, addheader, putdata, finish, flush)
        pyi.err_callback(req,e,pyerr)
        if not pyerr._finished_flag:
            pyerr.finish()


class ProxyHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'POST', 'HEAD', 'DELETE', 'PATCH', 'PUT', 'CONNECT']

    def compute_etag(self):
        return None # disable tornado Etag

    @tornado.web.asynchronous
    def get(self):
        def callback_set_status(*status):
            self.set_status(*status)

        def callback_add_header(k,v):
            self.add_header(k, v)

        def callback_write(data):
            self.write(data)

        def callback_finish(data=None):
            self.finish(data)

        def callback_flush():
            self.flush()

        if 'Proxy-Connection' in self.request.headers:
            del self.request.headers['Proxy-Connection']

        self._headers = tornado.httputil.HTTPHeaders()

        req=Req(self.request.method,self.request.uri,self.request.headers,self.request.body or b'',self.application.pyinstance.counter)
        py=PyRequest(req,self.application.pyinstance,
                     callback_set_status,callback_add_header,callback_write,callback_finish,callback_flush)
        if self.application.pyinstance.verbose>=Verbose:
            py.log()
        try:
            cmd=self.application.pyinstance.req_callback(req,py)
        except Exception as e:
            pyerr=PyError(req, self.application.pyinstance, e, callback_set_status, callback_add_header, callback_write, callback_finish, callback_flush)
            self.application.pyinstance.err_callback(req,e,pyerr)
            if not pyerr._finished_flag:
                pyerr.finish()
            return

        if cmd==Go or cmd==Pass:
            assert not py._tamper_flag, 'cannot forward request when PY is tampered'
            tornado_fetcher(
                self.application.pyinstance, req,
                self.application.pyinstance.res_callback if cmd==Go else None,
                callback_set_status, callback_add_header, callback_write, callback_finish, callback_flush,
            )

        elif cmd==Halt:
            if self.application.pyinstance.verbose>=Verbose:
                print('<-H #%4d (Halted) %s'%(req._count,req.url))
            if not py._finished_flag:
                self.finish()

        elif isinstance(cmd,Response):
            if self.application.pyinstance.verbose>=Verbose: #todo: encode to bytes before calc length
                print('<-F #%4d (Faked: %s %sB) %s'%(req._count,' '.join(map(str,cmd.status)),len(cmd.body),req.url))

            self.set_status(*cmd.status)
            for k,v in cmd.headers:
                self.add_header(k,v)
            self.finish(cmd.body)

        else:
            raise RuntimeError('bad request callback value %r'%cmd)

    post=get
    head=get
    delete=get
    patch=get
    put=get

    @tornado.web.asynchronous
    def connect(self):
        host, port = self.request.uri.split(':')
        client = self.request.connection.stream

        def client_close(data=None):
            if upstream.closed():
                return
            if data:
                upstream.write(data)
            upstream.close()

        def upstream_close(data=None):
            if client.closed():
                return
            if data:
                client.write(data)
            client.close()

        def start_tunnel():
            client.read_until_close(client_close, upstream.write)
            upstream.read_until_close(upstream_close, client.write)
            client.write(b'HTTP/1.0 200 Connection established\r\n\r\n')

        reqssl=ReqSSL(host,port)
        py=PySSL(reqssl,self.application.pyinstance)
        try:
            cmd=self.application.pyinstance.con_callback(reqssl,py)
        except:
            traceback.print_exc()
            return self.finish()

        if cmd==Pass:
            if self.application.pyinstance.verbose>=Verbose:
                py.log()
            upstream = tornado.iostream.IOStream(socket.socket())
            upstream.connect((reqssl.host, reqssl.port), start_tunnel)

        elif cmd==Go:
            raise NotImplementedError #todo: implement mitm later

        elif cmd==Halt:
            if self.application.pyinstance.verbose>=Verbose:
                print('<H> #%4d (Halted) CONNECT %s : %s'%(py.count,reqssl.host,reqssl.port))
            self.finish()

        else:
            raise RuntimeError('bad connection callback value %r'%cmd)


class Proxy:
    def __init__(self,port,req_callback,res_callback,err_callback,con_callback,verbose):
        self.req_callback=req_callback
        self.res_callback=res_callback
        self.err_callback=err_callback
        self.con_callback=con_callback

        self.counter=counter()
        self.verbose=verbose

        port=int(port)

        if self.verbose>Silent:
            print('=== Running proxy on port %d.'%port)

        app=tornado.web.Application([
            (r'.*', ProxyHandler),
        ])
        app.pyinstance=self
        app.listen(port)
        self.ioloop=tornado.ioloop.IOLoop.instance()
        self.ioloop.start()


def proxy(port,request=Go,response=Go,error=Halt,connect=Pass,logging=Normal):
    def normalize(callback):
        if is_cmd(callback): #todo: do not prepare Req/Res and PY for optimization
            return lambda *_: callback
        else:
            return callback

    Proxy(port,normalize(request),normalize(response),default_err_handler if error==Halt else error,normalize(connect),logging)
