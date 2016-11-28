#coding=utf-8

Pass='pass'
Go='go'
Halt='halt'

Silent=1
Normal=2
Verbose=3

import requests
import sys
import traceback
from .models import Response

sess=requests.Session()
sess.trust_env=False #disable original proxy
thread_adapter=requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
sess.mount('http://', thread_adapter)

def default_err_handler(req,e,py):
    py.log()
    py.set_status(500)
    py.add_header('content-type','text/plain')
    py.finish('Internal server error:\n\n[%s] %s\n\n%s'%(type(e),e,traceback.format_exc()))

def is_cmd(x):
    return x==Pass or x==Go or x==Halt or isinstance(x,Response)

def fallback(alternative):
    def decorator(fn):
        def call(req,*args,**kwargs):
            try:
                cmd=fn(req,*args,**kwargs)
            except Exception as e:
                print('*** Exception (suppressed by fallback): #%4d %s (%dB) %s'%(req._count, req.method, len(req.body), req.url))
                exc_info=sys.exc_info()
                traceback.print_exception(*exc_info)
                return alternative
            else:
                if cmd is None:
                    return alternative
                elif is_cmd(cmd):
                    return cmd
                else:
                    print('*** Value fallbacked: %r -> %r'%(cmd,alternative))
                    return alternative
        return call
    return decorator