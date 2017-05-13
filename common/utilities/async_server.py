# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import select
import struct
import sys
import time
import traceback

from bds_server.pollables import declarer_socket
from common.pollables import listener_socket
from common.pollables import service_socket
from common.utilities import constants
from common.utilities import poller
from common.utilities import util
from frontend_server.pollables import identifier_socket

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
        self._pollables = {}
        self._callables = []

    def add_listener(self):
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
        self._pollables[sl.fileno()] = listener_socket.ListenerSocket(
            sl,
            constants.LISTEN_STATE,
            self._application_context,
            self._pollables
        )


    def add_declarer(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP
        )
        sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_TTL,
            2
        )
        fcntl.fcntl(
            sock.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(sock.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK,
        )
        self._pollables[sock.fileno()] = declarer_socket.DeclarerSocket(
            sock,
            self._application_context,
        )

    def add_identifier(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP
        )
        sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )
        sock.bind(
            (
                '',
                int(self._application_context["multicast_group"]["port"])
            )
        )
        sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            struct.pack(
                "=4sl",
                socket.inet_aton(
                    self._application_context["multicast_group"]["address"]
                ),
                socket.INADDR_ANY
            )
        )
        fcntl.fcntl(
            sock.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(sock.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK,
        )
        self._pollables[sock.fileno()] = identifier_socket.IdentifierSocket(
            sock,
            self._application_context,
        )

    def on_start(self):
        #Add a listener, for service requests that the server offers
        self.add_listener()

        if (
            self._application_context["server_type"]
            == constants.BLOCK_DEVICE_SERVER
        ):
            #need to declare constantly so frontend_servers
            #recognize and add us:
            self.add_declarer()
        elif (
            self._application_context["server_type"]
            == constants.FRONTEND_SERVER
        ):
            #need to constantly identify new connections
            self.add_identifier()

    def handle_events(self, events):
        for curr_fd, event in events:
            entry = self._pollables[curr_fd]

            try:
                #pollable has error
                if event & (select.POLLHUP | select.POLLERR):
                    logging.debug("%s:\tEntry has error" % entry)
                    entry.on_error()

                #pollable has read
                if event & select.POLLIN:
                    logging.debug("%s:\tEntry has read" % entry)
                    entry.on_read()

                #pollable has write
                if event & select.POLLOUT:
                    logging.debug("%s:\tEntry has write" % entry)
                    entry.on_write()

            except util.Disconnect as e:
                logging.error("%s:\tSocket disconnected, closing...", entry)
                entry.on_close()


    def timeout_event(self):
        #if poll went off on timeout, call for an "update" on system status
        for fd, entry in self._pollables.items():
            try:
                entry.on_idle()
            except Exception as e:
                traceback.print_exc()
                logging.error(
                    (
                        "%s:\tSocket raised an error when on_idle: %s"
                    ) % (
                        entry,
                        e
                    )
                )

    def run(self):
        logging.debug("STARTED RUNNING..\n")
        self.on_start()
        logging.debug("READY FOR REQUESTS")
        #start running
        while len(self._pollables):
            try:
                self.close_needed()
                poll_obj = self.create_poller()

                #handle events from poller
                events = poll_obj.poll(self._application_context["poll_timeout"])

                if len(events):
                    #got some event, check it and let pollable respond
                    self.handle_events(events)
                else:
                    #went out on timeout. Call on_idle for all pollables
                    self.timeout_event()

            except Exception as e:
                logging.critical(traceback.print_exc())
                self.close_all()
        logging.debug("SERVER TERMINATING")

    def create_poller(self):
        poll_obj = self._application_context["poll_type"]()

        for fd, entry in self._pollables.items():
            poll_obj.register(
                fd,
                entry.get_events()
            )
        return poll_obj

    @property
    def pollables(self):
        return self._pollables

    @pollables.setter
    def pollables(self, s):
        self._pollables = s

    def close_needed(self):
        for fd, entry in self._pollables.items()[:]:
            if (
                entry.is_closing() and
                entry.data_to_send == ""
            ):
                entry.on_close()
                #if socket still doesn't want to close before terminate
                #then add it callables list to be closed when wanted
                self._callables.append(entry)
                del self._pollables[fd]

        for closed_socket in self._callables:
            #check if finally ready to terminate
            if entry.is_closing():
                del closed_socket


    def close_all(self):
        for fd, entry in self._pollables.items()[:]:
            entry.on_close()
            del self._pollables[fd]
