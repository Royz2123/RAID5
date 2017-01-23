#!/usr/bin/python

import contextlib
import socket

with contextlib.closing(
    socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    )
) as s:
    s.connect(('127.0.0.1', 8888))
    for i in range(10):
        s.send('ping'.encode('utf-8'))
        print(s.recv(1000))
