# -*- coding: utf-8 -*-
import errno
import importlib
import logging
import os
import select
import socket
import time
import traceback

from common.pollables import pollable
from common.utilities import constants
from common.utilities import http_util
from common.utilities import util
from common.services import base_service

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse


class IdentifierSocket(pollable.Pollable):
    def __init__(self, socket, application_context):
        self._application_context = application_context
        self._socket = socket
        self._fd = socket.fileno()
        self._recvd_data = ""
        self._data_to_send = ""

    def on_idle(self):
        self.update_disconnected()

    def on_read(self):
        try:
            buf, address = self._socket.recvfrom(constants.BLOCK_SIZE)
            self.update_disk(buf, address)
        except BaseException:
            pass

    def update_disconnected(self):
        for disk_UUID, disk in self._application_context["available_disks"].items(
        ):
            if (time.time() - disk["timestamp"]) > constants.DISCONNECT_TIME:
                disk["state"] = constants.OFFLINE
            if (time.time() - disk["timestamp"]) > constants.TERMINATE_TIME:
                del self._application_context["available_disks"][disk_UUID]

    def update_disk(self, buf, address):
        if buf.find(constants.CRLF_BIN) == -1:
            raise RuntimeError(
                "Invalid Decleration from Block Device: %s" % buf
            )
        # split the content so we can address it
        content = buf.split(constants.CRLF_BIN)

        # update the disk in available_disks
        self._application_context["available_disks"][content[0]] = {
            "disk_UUID": content[0],
            "state": constants.ONLINE,
            "UDP_address": address,
            "TCP_address": (address[0], int(content[1])),
            "timestamp": time.time(),
            "volume_UUID": content[2]
        }

    def get_events(self):
        return constants.POLLERR | constants.POLLIN

    def is_terminating(self):
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

    def __repr__(self):
        return ("IdentifierSocket Object: %s\t\t\t" % self._fd)
