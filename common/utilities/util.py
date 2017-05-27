# -*- coding: utf-8 -*-
import base64
import errno
import os
import random
import socket
import string
import time
import uuid

from common.utilities import constants

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse

# generates a multipurpose UUID as a string
def generate_uuid():
    return str(uuid.uuid4())

# generates a long password for communication with block device server
def generate_password():
    return ''.join(
        [
            random.choice(string.ascii_letters + string.digits)
            for n in xrange(constants.LONG_PASSWORD_LENGTH)
        ]
    )

# checks the Basic Authentication of an entry, returns if there has been a
# successful_login to the frontend by the user
def check_user_login(entry):
    successful_login = False
    auth_content = extract_basic_auth_content(entry)
    if auth_content is not None:
        username, password = decode_authorization(auth_content)
        application_auth = entry.application_context["authentication"]
        successful_login = (
            username == application_auth["common_user"] and
            password == application_auth["common_password"]
        )
    return successful_login

# checks the Basic Authentication of an entry, returns if there has been a
# successful_login to the block device bythe frontend using the long password
# that has been provided
def check_frontend_login(entry):
    auth_content = extract_basic_auth_content(entry)
    if auth_content is not None:
        return (
            base64.b64decode(auth_content)
            == entry.application_context["authentication"]["long_password"]
        )
    return False

#extracts the basic Authentication Authorization content
def extract_basic_auth_content(entry):
    if "Authorization" in entry.request_context["headers"].keys():
        print "HEYYY"
        auth_type, auth_content = entry.request_context["headers"][
            "Authorization"
        ].split(" ", 2)
        if auth_type == "Basic":
            return auth_content.strip(" ")
    return None

# decodes the convention of Basic Authentication using base64
def decode_authorization(auth_content):
    return tuple(base64.b64decode(auth_content).split(':', 1))

# encodes the convention of Basic Authentication using base64
def encode_authorization(username, password):
    return base64.b64encode("%s:%s" % (username, password))

# returns a dict of only the initialized volumes
def initialized_volumes(volumes):
    init_volumes = {}
    for volume_UUID, volume in volumes.items():
        if volume["volume_state"] == constants.INITIALIZED:
            init_volumes[volume_UUID] = volume
    return init_volumes

def get_disk_UUID_by_num(disks, disk_num):
    for disk_UUID, disk in disks.items():
        if disk["disk_num"] == disk_num:
            return disk_UUID
    raise RuntimeError("Disk not found by disk num")

# recieves a dict of disks and seperates into two: onlines and offlines
def sort_disks(disks):
    online_disks, offline_disks = {}, {}
    for disk_UUID, disk in disks.items():
        if disk["state"] == constants.ONLINE:
            online_disks[disk_UUID] = disk
        else:
            offline_disks[disk_UUID] = disk
    return online_disks, offline_disks


def make_address(add):
    try:
        address, port = add.split(constants.ADDRESS_SEPERATOR)
        return (str(address), int(port))
    except BaseException:
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
    def __init__(self, desc="Disconnect"):
        super(Disconnect, self).__init__(desc)


class InvalidArguments(RuntimeError):
    def __init__(self, desc="Bad Arguments"):
        super(InvalidArguments, self).__init__(desc)


class DiskRefused(RuntimeError):
    def __init__(self, disk_UUID, desc="Disk Refused to connect"):
        super(DiskRefused, self).__init__(desc)
        self._disk_UUID = disk_UUID

    @property
    def disk_UUID(self):
        return self._disk_UUID


# vim: expandtab tabstop=4 shiftwidth=4
