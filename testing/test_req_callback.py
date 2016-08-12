from utils import *
from pytrade import *
import requests

def on_request(req, py):
    if req.url.endswith('?test-halt'):
        return Halt

    if req.url.endswith('?test-tamper'):
        req.url=SERVER
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

    if req.url.endswith('?test-py-stream'):
        py.set_status(200,'hello')
        py.add_header('x-foo','bar')
        py.flush()
        for char in 'tampered':
            py.write(char)
        return Halt

    if req.url.endswith('?test-pass'):
        return Pass

    if req.url.endswith('?test-bad-ret'):
        return

    return Go

def init():
    global example_text
    example_text=requests.get(SERVER).text

def test_normal_req(s):
    res=s.get(SERVER)
    assert res.status_code==200 and res.text==example_text and res.headers['x-original-header']=='original header'

def test_halt(s):
    res=s.get(SERVER+'?test-halt')
    assert not res.content

def test_tamper_request(s):
    res=s.get(SERVER+'?test-tamper')
    assert res.status_code==200 and res.text==example_text

def test_response(s):
    res=s.get(SERVER+'?test-response')
    assert res.text=='tampered' and res.headers.get('x-foo')=='bar' and res.reason.lower()=='hello'

def test_py(s):
    res=s.get(SERVER+'?test-py')
    assert res.text=='tampered' and res.headers.get('x-foo')=='bar' and res.reason.lower()=='hello'

def test_py_stream(s):
    res=s.get(SERVER+'?test-py-stream')
    assert res.text=='tampered' and res.headers.get('x-foo')=='bar' and res.reason.lower()=='hello'

def test_pass(s):
    res1=s.get(SERVER+'?test-pass')
    res2=requests.get(SERVER+'?test-pass')
    assert res1.status_code==res2.status_code==200 and res1.text==res2.text

def test_post(s):
    res1=requests.post(SERVER,data=b'hello world')
    res2=s.post(SERVER,data=b'hello world')
    assert res1.status_code==res2.status_code==200 and res1.text==res2.text

def test_bad_ret(s):
    res=s.get(SERVER+'?test-bad-ret')
    assert res.status_code==500