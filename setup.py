from setuptools import *

setup(
    name='pytrade',
    author='xmcp',
    version='2.0.02',
    
    description='HTTP Proxy for Humans',
    keywords='http proxy',
    url='https://github.com/xmcp/pytrade',
    
    license='WTFPL',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Internet :: Proxy Servers',
        
        'Natural Language :: Chinese (Simplified)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
    ],
    
    packages=find_packages(exclude=['testing','example']),
    package_data={
        'pytrade': ['ssl_stuff/*'],
    },
    install_requires=[
        'tornado',
        'requests',
        'publicsuffix',
    ],
    extras_require={
        'test': ['pytest'],
    },
)
