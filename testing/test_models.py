#coding=utf-8
import pytest
from utils import *
from pytrade import *
import requests

def on_request(req,py):
    py.log()
    assert py.count
    req.test_count=py.count

    if req.url.endswith('?test-req-py'):
        assert isinstance(req.host,str)
        assert isinstance(req.port,int)
        return Response(body='ok')

    return Go

def on_response(req,res,py):
    py.log()
    assert py.count==req.test_count

    if req.url.endswith('?test-res-py'):
        assert isinstance(res.code,int)
        assert isinstance(res.reason,str)
        code,reason=res.status
        assert res.code==code
        assert res.reason==reason
        return Response(body='ok')

    if req.url.endswith('?test-res-status-1'):
        res.status='403 forbidden'
        assert res.reason=='forbidden'
        return Go

    if req.url.endswith('?test-res-status-2'):
        res.status=(403,'forbidden')
        assert res.reason=='forbidden'
        return Go

    if req.url.endswith('?test-res-status-3'):
        res.status=403
        assert res.reason=='forbidden'
        return Go

    if req.url.endswith('?test-res-status-4'):
        res.status='403'
        assert res.reason=='forbidden'
        return Go

    if req.url.endswith('?test-bin-regulations-1'):
        try:
            assert res.binary
            assert res.text
            assert res.binary
            res.text='123'
            assert res.binary==b'123'
            res.binary=b'234'
            assert res.text=='234'
            assert res.binary==b'234'
        except Exception as e:
            return Response(body=repr(e))
        else:
            return Response(body='ok')

    if req.url.endswith('?test-bin-regulations-2'):
        assert res.binary
        try:
            next(res.iter_binary())
        except AssertionError:
            return Response(body='ok')
        else:
            return Response(body='failed: no error')

    if req.url.endswith('?test-bin-regulations-3'):
        next(res.iter_binary())
        try:
            res.binary
        except AssertionError:
            return Response(body='ok')
        else:
            return Response(body='failed: no error')

    if req.url.endswith('?test-bin-regulations-4'):
        next(res.iter_raw())
        try:
            next(res.iter_binary())
        except AssertionError:
            return Response(body='ok')
        else:
            return Response(body='failed: no error')

    return Go

def on_connect(req,py):
    py.log()
    assert py.count
    assert isinstance(req.url,str)
    assert isinstance(req.host,str)
    assert isinstance(req.port,int)
    assert req.host in req.url
    assert str(req.port) in req.url

    return Pass

def test_req_py(s):
    res=s.get(SERVER+'?test-req-py')
    assert res.status_code==200 and res.text=='ok'

def test_res_py(s):
    res=s.get(SERVER+'?test-res-py')
    assert res.status_code==200 and res.text=='ok'

def test_con_py(s):
    s.get('https://example.com')


@pytest.mark.parametrize('ind',[1,2,3,4])
def test_res_status(s,ind):
    res=s.get(SERVER+'?test-res-status-%d'%ind)
    assert res.status_code==403 and res.reason=='forbidden'

@pytest.mark.parametrize('ind',[1,2,3,4])
def test_bin_regulations(s,ind):
    res=s.get(SERVER+'?test-bin-regulations-%d'%ind)
    assert res.status_code==200 and res.text=='ok'
