#coding=utf-8
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.httputil
import tornado.gen

import sys
import socket
import requests
from tornado.concurrent import run_on_executor
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor

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
        pyerr=PyError(req, pyi, sys.exc_info(), setstatus, addheader, putdata, finish, flush)
        cmd=pyi.err_callback(req,e,pyerr)
        if isinstance(cmd,Response):
            if pyi.verbose>=Verbose:
                print('<-! #%4d Exception Response %s %dB %s'%\
                    (req._count,' '.join(map(str,cmd.status)),len(cmd.body),req.url))

            ioloop.add_callback(setstatus,*cmd.status)
            for k,v in cmd.headers.items():
                ioloop.add_callback(addheader,k,v)
            ioloop.add_callback(putdata,cmd.body)
        if not pyerr._finished_flag:
            pyerr.finish()


class ProxyHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ['GET', 'POST', 'HEAD', 'DELETE', 'PATCH', 'PUT', 'CONNECT']
    executer=ThreadPoolExecutor(100)

    def compute_etag(self):
        return None # disable tornado Etag

    def _async(self,fn,*args,**kwargs):
        def self_remover(_,*args,**kwargs):
            return fn(*args,**kwargs)
        return run_on_executor(executor='executer')(self_remover)(self,*args,**kwargs)

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        if 'Proxy-Connection' in self.request.headers:
            del self.request.headers['Proxy-Connection']
        self._headers = tornado.httputil.HTTPHeaders()
        req=Req(self.request.method,self.request.uri,self.request.headers,self.request.body or b'',self.application.pyinstance.counter)
        py=PyRequest(req,self.application.pyinstance,self.set_status,self.add_header,self.write,self.finish,self.flush)
        if self.application.pyinstance.verbose>=Verbose:
            py.log()
        try:
            cmd=yield self._async(self.application.pyinstance.req_callback,req,py)
        except Exception as e:
            pyerr=PyError(req, self.application.pyinstance, sys.exc_info(), self.set_status, self.add_header, self.write, self.finish, self.flush)
            cmd=yield self._async(self.application.pyinstance.err_callback,req,e,pyerr)

            if isinstance(cmd,Response):
                if self.application.pyinstance.verbose>=Verbose:
                    print('<-! #%4d Exception Response %s %dB %s'%\
                        (req._count,' '.join(map(str,cmd.status)),len(cmd.body),req.url))

                self.set_status(*cmd.status)
                for k,v in cmd.headers.items():
                    self.add_header(k,v)
                self.write(cmd.body)
            if not pyerr._finished_flag:
                pyerr.finish()
            return

        if cmd==Go or cmd==Pass:
            assert not py._tamper_flag, 'cannot forward request when PY is tampered'
            yield self._async(tornado_fetcher,
                self.application.pyinstance, req,
                self.application.pyinstance.res_callback if cmd==Go else None,
                self.set_status, self.add_header, self.write, self.finish, self.flush,
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
            for k,v in cmd.headers.items():
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
        except Exception as e:
            pyerr=PyError(reqssl, self.application.pyinstance, sys.exc_info(), self.set_status, self.add_header, self.write, self.finish, self.flush)
            cmd=self.application.pyinstance.err_callback(reqssl,e,pyerr)

            if isinstance(cmd,Response):
                if self.application.pyinstance.verbose>=Verbose:
                    print('<-! #%4d Exception Response %s %dB %s'%\
                        (py.count,' '.join(map(str,cmd.status)),len(cmd.body),reqssl.url))

                self.set_status(*cmd.status)
                for k,v in cmd.headers.items():
                    self.add_header(k,v)
                self.write(cmd.body)
            if not pyerr._finished_flag:
                pyerr.finish()
            return

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
        self.port=int(port)

        self.app=tornado.web.Application([
            (r'.*', ProxyHandler),
        ])
        self.server=self.app.listen(self.port)
        self.app.pyinstance=self
        self.ioloop=tornado.ioloop.IOLoop.instance()

    @classmethod
    def from_friendly_args(cls,port,request=Go,response=Go,error=Halt,connect=Pass,logging=Normal):
        def normalize(callback):
            if is_cmd(callback): #todo: do not prepare Req/Res and PY for optimization
                return lambda *_: callback
            else:
                return callback

        return cls(
            port,
            normalize(request), normalize(response), default_err_handler if error==Halt else error, normalize(connect),
            logging
        )

    def run(self):
        if self.verbose>Silent:
            print('=== Running proxy on port %d.'%self.port)
        self.ioloop.start()


def proxy(port,request=Go,response=Go,error=Halt,connect=Pass,logging=Normal):
    Proxy.from_friendly_args(port,request,response,error,connect,logging).run()
