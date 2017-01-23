# -*- coding: utf-8 -*-
import errno
import os
import socket

from . import constants


# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse


def spliturl(url):
    return urlparse.urlsplit(url)


def write(fd, buf):
    while buf:
        buf = buf[os.write(fd, buf):]


def parse_header(line):
    SEP = ':'
    n = line.find(SEP)
    if n == -1:
        raise RuntimeError('Invalid header received')
    return line[:n].rstrip(), line[n + len(SEP):].lstrip()



class Disconnect(RuntimeError):
    def __init__(self, desc = "Disconnect"):
        super(Disconnect, self).__init__(desc)

class InvalidArguments(RuntimeError):
    def __init__(self, desc = "Bad Arguments"):
        super(InvalidArguments, self).__init__(desc)


# vim: expandtab tabstop=4 shiftwidth=4
