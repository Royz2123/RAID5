# -*- coding: utf-8 -*-
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

from http.common.pollables import server_socket_listen
from http.common.pollables import server_socket
from http.common.utilities import constants
from http.common.utilities import poller
from http.common.utilities import util

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse


class AsyncServer(object):
    def __init__(self, application_context):
        self._application_context = application_context
        self._socket_data = {}

    def on_start(self):
        pass

    def run(self):
        logging.debug("STARTED RUNNING..\n")

        #Add a listener
        sl = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        fcntl.fcntl(
            sl.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(sl.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK,
        )
        sl.bind((
            self._application_context["bind_address"],
            self._application_context["bind_port"]
        ))
        sl.listen(10)
        self._socket_data[sl.fileno()] = server_socket_listen.ServerSocketListen(
            sl,
            constants.LISTEN_STATE,
            self._application_context,
        )

        logging.debug("READY FOR REQUESTS")
        #start running
        while len(self._socket_data):
            try:
                self.close_needed()
                poll_obj = self._create_poller()

                #handle events from poller
                for curr_fd, event in poll_obj.poll(
                    self._application_context["poll_timeout"]
                ):
                    entry = self._socket_data[curr_fd]

                    try:
                        #pollable has error
                        if event & (select.POLLHUP | select.POLLERR):
                            logging.debug("%s:\tEntry has error" % entry)
                            entry.on_error()

                        #pollable has read
                        if event & select.POLLIN:
                            logging.debug("%s:\tEntry has read" % entry)
                            entry.on_read(self._socket_data)

                        #pollable has write
                        if event & select.POLLOUT:
                            logging.debug("%s:\tEntry has write" % entry)
                            entry.on_write(self._socket_data)

                    except util.Disconnect as e:
                        logging.error("%s:\tSocket disconnected, closing...")
                        entry.on_close()

            except Exception as e:
                logging.critical(traceback.print_exc())
                self.close_all()


    def _create_poller(self):
        poll_obj = self._application_context["poll_type"]()

        for fd, entry in self._socket_data.items():
            poll_obj.register(
                fd,
                entry.get_events(self._socket_data)
            )
        return poll_obj

    @property
    def socket_data(self):
        return self._socket_data

    @socket_data.setter
    def socket_data(self, s):
        self._socket_data = s

    def close_needed(self):
        for fd, entry in self._socket_data.items()[:]:
            if (
                entry.state == constants.CLOSING_STATE and
                entry.data_to_send == ""
            ):
                entry.on_close()
                #if socket still wants to close after terminate, delete it
                if entry.state == constants.CLOSING_STATE:
                    del self._socket_data[fd]

    def close_all(self):
        for fd, entry in self._socket_data.items()[:]:
            entry.on_close()
            del self._socket_data[fd]
