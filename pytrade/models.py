#coding=utf-8
import traceback
import urllib.parse
from pytrade.const import *
import requests.status_codes


def counter():
    num=0
    while True:
        num+=1
        yield num


def run_once(f):
    runned=False
    def wrapper(*args,**kwargs):
        nonlocal runned
        if not runned:
            runned=True
            return f(*args,**kwargs)

    return wrapper


def _parse_status(status):
    if isinstance(status,int):
        status=[status]
    elif isinstance(status,str):
        code,_,reason=status.partition(' ')
        if _:
            status=[int(code),reason]
        else:
            status=[int(code)]
    if len(status)==1:
        status=[int(status[0]),requests.status_codes._codes.get(status[0],['unknown'])[0].replace('_',' ')]
    assert len(status)==2, 'bad status code'
    return status


class Req:
    def __init__(self,method,url,headers,body,counter):
        self.method=method
        self.url=url
        self.headers=headers
        self.body=body
        self._real_count=None
        self._counter=counter

    @property
    def _count(self):
        if self._real_count is None:
            self._real_count=next(self._counter)
        return self._real_count

    @property
    def host(self):
        return urllib.parse.urlsplit(self.url).netloc.partition(':')[0]

    @property
    def port(self):
        splited=urllib.parse.urlsplit(self.url)
        return int(splited.netloc.partition(':')[2] or (443 if splited.scheme=='https' else 80))


class Res:
    def __init__(self, r):
        self.code=r.status_code
        self.reason=r.reason
        self.headers=r.headers

        self._r=r
        self._modified_content=None
        self._iter_consumed_flag=False
        self._content_consumed_flag=False
        self._decoded_flag=False
        self._content_bkp=[]

    @property
    def status(self):
        return self.code,self.reason

    @status.setter
    def status(self,st):
        self.code,self.reason=_parse_status(st)

    @property
    def text(self):
        return self.binary.decode(self._r.encoding or self._r.apparent_encoding,'ignore')

    @text.setter
    def text(self,text):
        self.binary=text.encode(self._r.encoding or self._r.apparent_encoding,'ignore')

    @property
    def binary(self):
        if self._modified_content is not None:
            return self._modified_content
        else:
            assert not self._iter_consumed_flag, 'the response data is consumed in the iterator way'
            self._content_consumed_flag=True
            self._decoded_flag=True
            self._content_bkp=[self._r.content]
            return self._r.content

    @binary.setter
    def binary(self,content):
        self._content_consumed_flag=True
        self._decoded_flag=True
        self._modified_content=content
        self._content_bkp=[content]
        if 'content-length' in self.headers:
            self.headers['content-length']=len(content)

    def iter_binary(self,chunksize=64*1024):
        assert not self._content_consumed_flag, 'the response data is consumed in the non-iterator way'
        assert not self._iter_consumed_flag, 'you can only build the iterator once'
        self._iter_consumed_flag=True
        self._decoded_flag=True
        for chunk in self._r.iter_content(chunksize):
            self._content_bkp.append(chunk)
            yield chunk

    def iter_raw(self,chunksize=64*1024):
        assert not self._content_consumed_flag, 'the response data is consumed in the non-iterator way'
        assert not self._iter_consumed_flag, 'you can only build the iterator once'
        self._iter_consumed_flag=True
        self._decoded_flag=False
        for chunk in self._r.raw.stream(chunksize,False):
            self._content_bkp.append(chunk)
            yield chunk


class PyBase:
    def __init__(self,req,pyi,set_status,add_header,write,finish,flush):
        self._original_finish=finish

        self.set_status=self._tamper_fn(set_status)
        self.add_header=self._tamper_fn(add_header)
        self.write=self._tamper_fn(write)
        self.finish=self._tamper_fn(self._finish)
        self.flush=self._tamper_fn(flush)

        if pyi.verbose<=Silent:
            self.log=lambda:None
        else:
            self.log=run_once(self._log)

        self._req=req
        self._counter=pyi.counter
        self._tamper_flag=False
        self._finished_flag=False

    def _tamper_fn(self,fn):
        def wrapped(*args,**kwargs):
            self._tamper_flag=True
            return fn(*args,**kwargs)

        return wrapped

    def _finish(self,data=None):
        self._finished_flag=True
        self._original_finish(data)

    def _log(self):
        raise NotImplementedError()

    @property
    def count(self):
        return self._req._count


class PyRequest(PyBase):
    def _log(self):
        print(' -> #%4d %s (%dB) %s'%(self._req._count,self._req.method,len(self._req.body),self._req.url))


class PyResponse(PyBase):
    def __init__(self,req,res:Res,counter,set_status,add_header,write,finish,flush):
        super().__init__(req,counter,set_status,add_header,write,finish,flush)
        self._res=res

    def _log(self):
        print('<-  #%4d %s %s (%sB) %s'%(self._req._count,self._res.code,self._res.reason,self._res.headers.get('content-length','?'),self._req.url))


class ReqSSL:
    def __init__(self,host,port):
        self.host=host
        self.port=int(port)

    @property
    def url(self):
        return 'https://%s:%d'%(self.host,self.port)


class PySSL:
    def __init__(self,reqssl,pyi):
        self._counter=pyi.counter
        self._count=None
        self._reqssl=reqssl
        self.log=run_once(self._log)

    @property
    def count(self):
        return self._count or next(self._counter)

    def _log(self):
        print('<-> #%4d CONNECT %s : %s' % (self.count, self._reqssl.host, self._reqssl.port))


class PyError(PyBase):
    def __init__(self, req, pyi, exc, setstatus, addheader, putdata, finish, flush):
        super().__init__(
            req,pyi,
            lambda *_: pyi.ioloop.add_callback(setstatus, *_),
            lambda *_: pyi.ioloop.add_callback(addheader, *_),
            lambda *_: pyi.ioloop.add_callback(putdata, *_),
            lambda *_: pyi.ioloop.add_callback(finish, *_),
            lambda *_: pyi.ioloop.add_callback(flush, *_)
        )
        self._exc=exc
        self._verbose=pyi.verbose==Verbose

    def _log(self):
        print('!!! Exception: #%4d %s (%dB) %s'%(self._req._count,self._req.method,len(self._req.body),self._req.url))
        if self._verbose:
            traceback.print_exc()
        else:
            print('%s %s'%(type(self._exc),self._exc))


class Response:
    class _DefultRes:
        import requests.models

        code=200
        reason='OK'
        headers=requests.models.CaseInsensitiveDict()
        _content_bkp=[b'']
        binary=b''

    def __init__(self,base:Res=None,status=None,headers=None,body=None):
        if base is None:
            base=self._DefultRes()

        self.status=status if status is not None else (base.code, base.reason)
        self.headers=headers if headers is not None else base.headers
        self.status=_parse_status(self.status)
        self.body=body if body is not None else base.binary

        if 'content-length' in self.headers: #todo: make sure it's case insensitive
            self.headers['content-length']=len(self.body)
        if 'content-encoding' in self.headers:
            del self.headers['content-encoding']
