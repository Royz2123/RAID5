# -*- coding: utf-8 -*-
import errno
import fcntl
import logging
import os
import select
import socket
import traceback

import server_socket

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


class ServerSocketListen(pollable.Pollable):
    def __init__(self, socket, state, application_context):
        self._application_context = application_context
        self._socket = socket
        self._fd = socket.fileno()
        self._state = constants.LISTEN_STATE
        self._data_to_send = ""

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
    def listen_state(self, pollables):
        new_socket, address = self._socket.accept()

        #set to non blocking
        fcntl.fcntl(
            new_socket.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(new_socket.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK
        )

        #add to database
        new_http_socket = server_socket.ServerSocket(
            new_socket,
            constants.GET_REQUEST_STATE,
            self._application_context
        )
        pollables[new_socket.fileno()] = new_http_socket
        logging.debug(
            "%s :\t Added a new HttpSocket, %s"
            % (
                self,
                new_http_socket
            )
        )

    def on_close(self):
        self._socket.close()

    #handlers:
    states = {
        constants.LISTEN_STATE : {
            "function" : listen_state,
            "next" : constants.CLOSING_STATE
        },
        constants.CLOSING_STATE : {
            "function" : on_close,
            "next" : constants.CLOSING_STATE,
        }
    }

    def on_read(self, pollables):
        try:
            if self._state == constants.LISTEN_STATE:
                self.listen_state(pollables)

        except Exception as e:
            logging.error("%s :\t %s" %
                (
                    self,
                    traceback.print_exc()
                )
            )
            self.on_error()

    def on_error(self):
        self._state = constants.CLOSING_STATE

    def get_events(self, pollables):
        event = select.POLLERR
        if (
            self._state == constants.LISTEN_STATE and
            len(pollables) < self._application_context["max_connections"]
        ):
            event |= select.POLLIN
        return event

    #"util"
    def __repr__(self):
        return ("HttpListen Object: %s\t\t\t" % self._fd)
