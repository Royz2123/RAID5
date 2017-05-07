# -*- coding: utf-8 -*-
import errno
import os
import socket
import time

from http.common.utilities import constants

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse


def make_address(add):
    try:
        address, port = add.split(constants.ADDRESS_SEPERATOR)
        return (str(address), int(port))
    except:
        return False

def spliturl(url):
    return urlparse.urlsplit(url)

def write(fd, buf):
    while buf:
        buf = buf[os.write(fd, buf):]

def read(fd, max_buffer):
    ret = ""
    while True:
        buf = os.read(fd, max_buffer - len(ret))
        if buf == "":
            break
        ret += buf
    return ret

def parse_header(line):
    SEP = ':'
    n = line.find(SEP)
    if n == -1:
        raise RuntimeError('Invalid header received')
    return line[:n].rstrip(), line[n + len(SEP):].lstrip()


def send_all(s, buf):
    write(s.fileno(), buf)

def recv_all(s):
    return read(s.fileno(), constants.BLOCK_SIZE)


def recv_line(
    s,
    buf,
    max_length=constants.MAX_HEADER_LENGTH,
    block_size=constants.BLOCK_SIZE,
):
    while True:
        if len(buf) > max_length:
            raise RuntimeError('Exceeded maximum line length %s' % max_length)

        n = buf.find(constants.CRLF_BIN)
        if n != -1:
            break

        t = s.recv(block_size)
        if not t:
            raise RuntimeError('Disconnect')
        buf += t

    return buf[:n].decode('utf-8'), buf[n + len(constants.CRLF_BIN):]




class Disconnect(RuntimeError):
    def __init__(self, desc = "Disconnect"):
        super(Disconnect, self).__init__(desc)

class InvalidArguments(RuntimeError):
    def __init__(self, desc = "Bad Arguments"):
        super(InvalidArguments, self).__init__(desc)

class DiskRefused(RuntimeError):
    def __init__(self, disk_num, desc = "Disk Refused to connect"):
        super(DiskRefused, self).__init__(desc)
        self._disk_num = disk_num

    @property
    def disk_num(self):
        return self._disk_num


# vim: expandtab tabstop=4 shiftwidth=4
