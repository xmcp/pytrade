#coding=utf-8
from pytrade import *

def on_request(req,py):
    req.fff=True
    if req.url.startswith('http://pytrade-fake.'):
        return Response(
            status=200,
            body='hello world',
        )
    elif req.url.startswith('http://pytrade-halt.'):
        return Halt
    elif req.url.startswith('http://pytrade-tamper.'):
        py.set_status(200,'KO')
        py.add_header('content-type','text/plain')
        py.finish('hello world')
        return Halt
    return Go

def on_response(req,res,py):
    assert req.fff, 'FFF flag not found'
    py.log()
    for _ in res.iter_raw():
        pass

    if req.url.startswith('http://s.xmcp.ml/test-tamper/'):
        res.status=401
        res.headers['content-type']='text/xml'
        del res.headers['content-encoding']
        res.text='<foo></foo>'
        return Go
    elif req.url.startswith('http://s.xmcp.ml/test-fake/'):
        return Response(
            status=301,
            headers={
                'location': 'http://t.tt',
            },
        )
    elif req.url.startswith('http://s.xmcp.ml/test-fake-base/'):
        return Response(
            base=res,
        )
    elif req.url.startswith('http://s.xmcp.ml/test-halt/'):
        return Halt
    return Go

def on_connect(req,py):
    if req.host=='example.com':
        return Halt
    return Pass

proxy(8765,request=on_request,response=on_response,connect=on_connect,logging=Silent)