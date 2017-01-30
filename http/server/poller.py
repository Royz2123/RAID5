# -*- coding: utf-8 -*-
import argparse
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import select
import sys
import time
import traceback

import http_socket

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


class AsyncServer():
    def __init__(
        self,
        bind_address,
        bind_port,
        base,
        poll_type,
        poll_timeout,
        max_connections,
        max_buffer=constants.BLOCK_SIZE,
    ):
        self._base = base
        self._poll_timeout = poll_timeout
        self._poll_type = poll_type
        self._max_connections = max_connections
        self._max_buffer = max_buffer

        sl = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        fcntl.fcntl(
            sl.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(sl.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK,
        )

        sl.bind((bind_address, bind_port))
        sl.listen(10)

        self._socket_data = {
            sl.fileno() : http_socket.HttpSocket(
                sl,
                http_socket.LISTEN_STATE,
            )
        }

    def run(self):
        while len(self._socket_data.items()):
            try:
                self.close_needed()
                poll_obj = self._create_poller()

                #handle events from poller
                for curr_fd, event in poll_obj.poll(self._poll_timeout):
                    entry = self._socket_data[curr_fd]
                    try:
                        #socket has close
                        if event & (select.POLLHUP | select.POLLERR):
                            raise RuntimeError()

                        #socket recvd data
                        if event & select.POLLIN:
                            entry.recv_handler(self._socket_data, self._base)

                        #socket has send
                        if event & select.POLLOUT:
                            entry.send_handler(self._max_buffer, self._socket_data)

                    except util.Disconnect as e:
                        entry.closing_state(self._socket_data)

            except Exception as e:
                logging.critical(traceback.print_exc())
                self.close_all()


    def _create_poller(self):
        poller = self._poll_type()

        for fd, entry in self._socket_data.items():
            event = select.POLLERR

            if (
                entry._state == http_socket.LISTEN_STATE and
                len(self._socket_data) < self._max_connections
            ) or (
                entry._state >= http_socket.REQUEST_STATE and
                entry._state <= http_socket.CONTENT_STATE and
                len(entry._recvd_data) < self._max_buffer
            ):
                event |= select.POLLIN

            if (
                entry._state >= http_socket.RESPONSE_STATUS_STATE and
                entry._state <= http_socket.RESPONSE_CONTENT_STATE
            ):
                event |= select.POLLOUT

            poller.register(entry._socket.fileno(), event)
        return poller

    @property
    def socket_data(self):
        return self._socket_data

    @socket_data.setter
    def socket_data(self, s):
        self._socket_data = s

    def close_needed(self):
        for fd, entry in self._socket_data.items()[:]:
            if (
                entry._state == http_socket.CLOSING_STATE and
                entry._data_to_send == ""
            ):
                entry.close_handler()
                del self._socket_data[fd]

    def close_all(self):
        for fd, entry in self._socket_data.items()[:]:
            entry.close_handler()
            del self._socket_data[fd]


class Poller():
    def __init__(self):
        self._poller = select.poll()

    def register(self, fd, event):
        self._poller.register(fd, event)

    def poll(self, timeout):
        return self._poller.poll(timeout)


class Select():
    def __init__(self, socket_data, max_connections, max_buffer):
        self._poller = select.select()

    def poll(self, timeout):
        pass
