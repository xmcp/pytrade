#coding=utf-8
import pytest
from utils import *
from pytrade import *
import requests

def on_request(req,py):
    req.test_flag=req.url.endswith('?test-flag')

    if req.url.endswith('?test-pass'):
        return Pass

    return Go

def on_response(req,res,py):
    if req.url.endswith('?test-pass'):
        return Response(body='!!failed!!')

    if req.test_flag:
        return Response(body='good')

    if req.url.endswith('?test-halt'):
        return Halt

    if req.url.endswith('?test-tamper'):
        res.reason='hello'
        res.headers['x-foo']='bar'
        return Go

    if req.url.endswith('?test-response'):
        return Response(
            status=(200,'hello'),
            headers={'x-foo':'bar'},
            body='tampered',
        )

    if req.url.endswith('?test-py'):
        py.set_status(200,'hello')
        py.add_header('x-foo','bar')
        py.finish('tampered')
        return Halt

    if req.url.endswith('?test-decode'):
        res.binary=res.binary
        res.text=res.text
        return Response(base=res,body=res.binary,keep_encoding=False)

    if req.url.endswith('?test-stream'):
        res.binary=b''.join(res.iter_binary())
        return Go

    if req.url.endswith('?test-raw'):
        return Response(
            base=res,
            body=b''.join(res.iter_raw()),
            keep_encoding=True
        )

    if req.url.endswith('?test-raw-cache'):
        for _ in res.iter_raw():
            pass
        return Go

    if req.url.endswith('?test-bad-ret'):
        return

    return Go

def init():
    global example_text
    example_text=requests.get(SERVER).text

def test_normal_res(s):
    res=s.get(SERVER)
    assert res.status_code==200 and res.text==example_text and res.headers['x-original-header']=='original header'

def test_req_flag(s):
    res=s.get(SERVER+'?test-flag')
    assert res.text=='good'

def test_halt(s):
    res=s.get(SERVER+'?test-halt')
    assert not res.content

def test_tamper_response(s):
    res=s.get(SERVER+'?test-tamper')
    assert res.status_code==200 and res.reason=='hello' and \
        res.text.partition('headers =')[2]==example_text.partition('headers =')[2]!='' and \
        res.headers['x-original-header']=='original header' and res.headers['x-foo']=='bar'

def test_resopnse(s):
    res=s.get(SERVER+'?test-response')
    assert res.text=='tampered' and res.headers.get('x-foo')=='bar' and res.reason.lower()=='hello'

def test_py(s):
    res=s.get(SERVER+'?test-py')
    assert res.text=='tampered' and res.headers.get('x-foo')=='bar' and res.reason.lower()=='hello'

def test_pass(s):
    res=s.get(SERVER+'?test-pass')
    assert res.status_code==200 and '!!failed!!' not in res.text

def test_res_decode(s):
    res1=requests.get(SERVER+'?test-decode')
    res2=s.get(SERVER+'?test-decode')
    assert res1.status_code==res2.status_code==200 and res1.text==res2.text

def test_res_stream(s):
    res1=requests.get(SERVER+'?test-stream')
    res2=s.get(SERVER+'?test-stream')
    assert res1.status_code==res2.status_code==200 and res1.text==res2.text

def test_res_raw(s):
    res1=requests.get(SERVER+'?test-raw')
    res2=s.get(SERVER+'?test-raw')
    assert res1.status_code==res2.status_code==200 and res1.text==res2.text

def test_raw_cache(s):
    res1=requests.get(SERVER+'?test-raw-cache')
    res2=s.get(SERVER+'?test-raw-cache')
    assert res1.status_code==res2.status_code==200 and res1.text==res2.text

def test_bad_ret(s):
    res=s.get(SERVER+'?test-bad-ret')
    assert res.status_code==500