# -*- coding: utf-8 -*-
import argparse
import contextlib
import errno
import fcntl
import logging
import os
import select
import socket
import traceback

import http_socket
import pollable
import poller
import services

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


(
    LISTEN_STATE,
    CLOSING_STATE,
) = range(2)


class HttpSocketListen(pollable.Pollable):
    def __init__(self, socket, state):
        self._socket = socket
        self._fd = socket.fileno()
        self._state = LISTEN_STATE

    @property
    def fd(self):
        return self._fd

    @property
    def socket(self):
        return self._socket

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, s):
        self._state = s

    #state functions
    def listen_state(self, socket_data):
        new_socket, address = self._socket.accept()

        #set to non blocking
        fcntl.fcntl(
            new_socket.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(new_socket.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK
        )

        #add to database
        new_http_socket = http_socket.HttpSocket(
            new_socket,
            http_socket.REQUEST_STATE,
        )
        socket_data[new_socket.fileno()] = new_http_socket
        logging.debug(
            "%s :\t Added a new HttpSocket, %s"
            % (
                self,
                new_http_socket
            )
        )

    def closing_state(self, socket_data):
        for fd, entry in socket_data.items():
            entry._state = CLOSING_STATE

    #handlers:
    states = {
        LISTEN_STATE : {
            "function" : listen_state,
            "next" : CLOSING_STATE
        },
        CLOSING_STATE : {
            "function" : closing_state,
            "next" : CLOSING_STATE,
        }
    }

    def on_read(self, socket_data, base):
        try:
            if self._state == LISTEN_STATE:
                self.listen_state(socket_data)

        except Exception as e:
            logging.error("%s :\t %s" %
                (
                    self,
                    traceback.print_exc()
                )
            )
            self.closing_state(socket_data)

    def on_error(self):
        self._socket.close()

    def get_events(self, socket_data, max_connections, max_buffer):
        event = select.POLLERR
        if (
            self._state == LISTEN_STATE and
            len(socket_data) < max_connections
        ):
            event |= select.POLLIN
        return event

    #"util"
    def __repr__(self):
        return ("HttpListen Object: %s" % self._fd)
