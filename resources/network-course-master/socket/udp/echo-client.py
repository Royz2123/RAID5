#!/usr/bin/python

import contextlib
import socket

with contextlib.closing(
    socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_DGRAM,
    )
) as s:
    for i in range(10):
        s.sendto('ping'.encode('utf-8'), ('127.0.0.1', 8888))
        print(s.recvfrom(1000))
