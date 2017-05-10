# -*- coding: utf-8 -*-
import errno
import importlib
import logging
import os
import select
import socket
import time
import traceback

from http.common.pollables import pollable
from http.common.utilities import constants
from http.common.utilities import util

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse


#A simple UDP socket that broadcasts it's "name" when on_idle
# The "name" is a list of information regarding the block device

class DeclarerSocket(pollable.Pollable):
    def __init__(self, socket, application_context):
        self._application_context = application_context
        self._socket = socket
        self._fd = socket.fileno()
        self._recvd_data = ""
        self._data_to_send = ""

        self._group_address = (
            str(self._application_context["multicast_group"]["address"]),
            int(self._application_context["multicast_group"]["port"])
        )

    def on_idle(self):
        self._socket.sendto(
            self.create_content(),
            self._group_address,
        )

    def create_content(self):
        return (
            "%s%s%s%s" % (
                self._application_context["server_info"]["disk_uuid"],
                constants.CRLF_BIN,
                self._application_context["bind_port"],
                constants.CRLF_BIN
            )
        )

    def get_events(self):
        return select.POLLERR

    def is_closing(self):
        return False

    @property
    def application_context(self):
        return self._application_context

    @application_context.setter
    def application_context(self, a):
        self._application_context = a

    @property
    def recvd_data(self):
        return self._recvd_data

    @recvd_data.setter
    def recvd_data(self, r):
        self._recvd_data = r

    @property
    def data_to_send(self):
        return self._data_to_send

    @data_to_send.setter
    def data_to_send(self, d):
        self._data_to_send = d

    @property
    def socket(self):
        return self._socket

    @property
    def fd(self):
        return self._fd

    def on_error(self, e):
        self._state = constants.CLOSING_STATE

    def on_close(self):
        self._socket.close()
