# PY♂Trade
紧张刺激的 Python HTTP(S) 代理库

## 说明
- 全部在 Python 3.x 上开发并测试
- `pip install -r requirements.txt`
- 支持 gzip 自动解码和流式响应
- 将来会支持 HTTPS 请求解码

## 简单上手
- Hello World：在 8765 端口建立一个 HTTP 代理
```python
from pytrade import *
proxy(port=8765, logging=Verbose)
```
- 记录每次请求、响应、HTTPS Connect 的详细信息
```python
from pytrade import *

def on_request(req, py):
    print('=== Request # %d ===' % py.count)

    print('Method: %s' % req.method)
    print('URL: %s' % req.url)
    print('Headers: %s' % req.headers.items())
    print('Body: %sB' % len(req.body))

    return Go

def on_response(req, res, py):
    print('=== Response # %d ===' % py.count)

    print('Status: %d %s' % (res.code, res.reason))
    print('Headers: %s' % res.headers.items())

    # getting response body will break the streaming mechanism. use with care.
    # print('Body: %sB' % len(res.binary))

    return Go

def on_connect(req, py):
    print('=== HTTPS Connect # %d ===' % py.count)

    print('Host: %s' % req.host)
    print('Port: %d' % req.port)

    return Pass # disable SSL MITM

proxy(port=8765, request=on_request, response=on_response, connect=on_connect)
```
- 修改请求正文和响应正文
```python
from pytrade import *

def on_request(req, py):
    py.log()
    req.body = req.body.replace(b'aaaaa', b'bbbbb')
    return Go

def on_response(req, res, py):
    py.log()
    res.binary = res.binary.replace(b'aaaaa', b'bbbbb')
    return Go

proxy(port=8765, request=on_request, response=on_response)
```
- 将所有 `s.xmcp.ml` 域名下的  HTTP 3xx 响应跳转到 `http://example.com`
```python
from pytrade import *

def on_response(req, res, py):
    if req.host == 's.xmcp.ml' and 300 <= res.code <= 399:
        return Response(
            status=301,
            headers={
                'location': 'http://example.com',
            },
        )
    else:
        return Go

proxy(port=8765, response=on_response)
```
- 禁止所有请求通过
```python
from pytrade import *
proxy(port=8765, request=Halt, connect=Halt, logging=Verbose)
```
……

更复杂的示例详见 `example/function_test.py` 文件`