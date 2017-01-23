#!/usr/bin/python

import contextlib
import socket

with contextlib.closing(
    socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_DGRAM,
    )
) as s:
    s.bind(('0.0.0.0', 8888))
    s.settimeout(30)
    while True:
        data, addr = s.recvfrom(1000)
        s.sendto(data, addr)
