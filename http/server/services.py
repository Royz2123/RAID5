# -*- coding: utf-8 -*-
import argparse
import contextlib
import datetime
import errno
import fcntl
import os
import socket
import select
import sys
import time
import traceback

import http_socket
import poller

from ..common import constants
from ..common import util

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse


MIME_MAPPING = {
    'html': 'text/html',
    'png': 'image/png',
    'txt': 'text/plain',
}

#TODO: set closing after finished file
class Service(object):
    def __init__(
        self,
        file_name,
        wanted_headers,
        wanted_args = [],
        args = []
    ):
        self._wanted_headers = wanted_headers
        self._wanted_args = wanted_args
        self._response_headers = {}
        self._response_status = 200
        self._response_content = ""
        self._args = args

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, a):
        self._args = a

    @property
    def wanted_headers(self):
        return self._wanted_headers

    @wanted_headers.setter
    def wanted_headers(self, w_h):
        self._wanted_headers = w_h

    @property
    def wanted_args(self):
        return self._wanted_args

    @wanted_args.setter
    def wanted_args(self, w_a):
        self._wanted_args = w_a

    @property
    def response_status(self):
        return self._response_status

    @response_status.setter
    def response_status(self, r_s):
        self._response_status = r_s

    @property
    def response_headers(self):
        return self._response_headers

    @response_headers.setter
    def response_headers(self, r_h):
        self._response_headers = r_h

    @property
    def response_content(self):
        return self._response_content

    @response_content.setter
    def response_content(self, r_c):
        self._response_content = r_c

    def before_response_status(self, entry):
        return True

    def before_response_headers(self, entry):
        return True

    def before_response_content(self, entry, max_buffer):
        return True

    def before_terminate(self, entry):
        return True

    def check_args(self):
        for arg in self._wanted_args:
            if arg not in self._args.keys():
                return False
        return len(self._wanted_args) == len(self._args)


class GetFileService(Service):
    def __init__(self, file_name):
        Service.__init__(self, file_name, ["Content-Length"])
        self._file_name = file_name
        self._fd = None

    def before_response_status(self, entry):
        try:
            self._fd = os.open(self._file_name, os.O_RDONLY, 0o666)
        except Exception as e:
            self._response_status = 404
            entry.closing_state()
        return True

    def before_response_headers(self, entry):
        self._response_headers = {
            "Content-Length" : os.fstat(self._fd).st_size,
            "Content-Type" : MIME_MAPPING.get(
                os.path.splitext(
                    self._file_name
                )[1].lstrip('.'),
                'application/octet-stream',
            )
        }
        return True

    def before_response_content(
        self,
        entry,
        max_buffer = constants.BLOCK_SIZE
    ):
        buf = True
        try:
            while len(entry.data_to_send) < max_buffer:
                buf = os.read(self._fd, max_buffer)
                if not buf:
                    break
                self._response_content += buf

            if buf:
                return False
            os.close(self._fd)
            return True

        except socket.error, e:
            if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                raise


class TimeService(Service):
    def __init__(self):
        Service.__init__(self, "", [])

    def before_response_headers(self, entry):
        self._response_headers = {
            "Content-Length" : len(str(datetime.datetime.now())),
        }
        self._response_content = str(datetime.datetime.now())
        return True


class MulService(Service):
    def __init__(self, args):
        Service.__init__(self, "", [], ["a", "b"], args)

    def before_response_status(self, entry):
        if not self.check_args():
            self._response_status = 500

    def before_response_headers(self, entry):
        if self._response_status == 200:
            resp = str(
                int(self._args['a'][0]) *
                int(self._args['b'][0])
            )
            self._response_headers = {
                "Content-Length" : len(resp)
            }
            self._response_content = resp
        return True


SERVICES = {
    "/clock": TimeService,
    "/mul" :  MulService,
}


'''
    references
    "/mul": {"name": mul, "headers": None},
    "/secret": {"name": secret, "headers": ["Authorization"]},
    "/cookie": {"name": cookie, "headers": ["Cookie"]},
    "/login": {"name": login, "headers": None},
    "/secret2": {"name": secret2, "headers": ["Cookie"]},
'''
