#!/usr/bin/python

import contextlib
import socket

with contextlib.closing(
    socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    )
) as sl:
    sl.bind(('0.0.0.0', 8888))
    sl.listen(1)
    while True:
        s, addr = sl.accept()
        with contextlib.closing(s):
            s.settimeout(30)
            while True:
                data = s.recv(1000)
                if len(data) == 0:
                    break
                s.send(data)
