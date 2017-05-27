#!/usr/bin/python
## @package RAID5.common.utilities.async_server
# Module with the AsyncServer class for Asynchronous polling IO
#

import contextlib
import datetime
import errno
import logging
import os
import socket
import select
import struct
import sys
import time
import traceback

from block_device.pollables import declarer_socket
from common.pollables import listener_socket
from common.pollables import service_socket
from common.utilities import constants
from common.utilities import poller
from common.utilities import util
from frontend.pollables import identifier_socket

## AsyncServer class. Polls the objects it has and let's them handle
## their IO calls.
class AsyncServer(object):

    ## Constructor for AsyncServer
    ## @param application_context (dict) dict that specifies all of the
    ## parameters for this server.
    def __init__(self, application_context):
        ## Application_context
        self._application_context = application_context

        ## Pollables (start with none).
        ## Key: file descriptor
        ## Value: Pollable object
        self._pollables = {}

        ## Callables (start with none)
        self._callables = []

    ## Add a ListenerSocket to the pollables dict
    def add_listener(self):
        sock = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        # set to non-blocking
        sock.setblocking(0)

        # bind to the server address
        sock.bind((
            self._application_context["bind_address"],
            self._application_context["bind_port"]
        ))
        sock.listen(10)
        self._pollables[sock.fileno()] = listener_socket.ListenerSocket(
            sock,
            self._application_context,
            self._pollables
        )

    ## Adds a DeclarerSocket to the pollables dict
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
        # set socket to non-blocking
        sock.setblocking(0)
        self._pollables[sock.fileno()] = declarer_socket.DeclarerSocket(
            sock,
            self._application_context,
        )

    ## Adds an IdentifierSocket to the pollables dict
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
        # set socket to non-blocking
        sock.setblocking(0)
        self._pollables[sock.fileno()] = identifier_socket.IdentifierSocket(
            sock,
            self._application_context,
        )

    ## Specifies what server should do when starting up
    def on_start(self):
        # Add a listener, for service requests that the server offers
        self.add_listener()

        if (
            self._application_context["server_type"] ==
            constants.BLOCK_DEVICE_SERVER
        ):
            # need to declare constantly so frontends
            # recognize and add us:
            self.add_declarer()
        elif (
            self._application_context["server_type"] ==
            constants.FRONTEND_SERVER
        ):
            # need to constantly identify new connections
            self.add_identifier()

    ## Handle events from poller for all file descriptors specified.
    ## @param events (dict) dictionary specifying all of the polled events.
    def handle_events(self, events):
        for curr_fd, event in events:
            entry = self._pollables[curr_fd]

            try:
                # pollable has error
                if event & (constants.POLLHUP | constants.POLLERR):
                    logging.debug("%s:\tEntry has error" % entry)
                    entry.on_error()

                # pollable has read
                if event & constants.POLLIN:
                    logging.debug("%s:\tEntry has read" % entry)
                    entry.on_read()

                # pollable has write
                if event & constants.POLLOUT:
                    logging.debug("%s:\tEntry has write" % entry)
                    entry.on_write()

            except util.Disconnect as e:
                logging.error("%s:\tSocket disconnected, closing...", entry)
                entry.on_close()

    ## Handles the file descriptors when on timeout. Calls the on_idle
    ## function they have implemented
    def timeout_event(self):
        # if poll went off on timeout, call for an "update" on system status
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

    ## Function that runs the server
    def run(self):
        logging.debug("STARTED RUNNING..\n")
        self.on_start()
        logging.debug("READY FOR REQUESTS")
        # start running
        while len(self._pollables):
            try:
                self.close_needed()
                poll_obj = self.create_poller()

                # handle events from poller
                events = poll_obj.poll(
                    self._application_context["poll_timeout"])

                if len(events):
                    # got some event, check it and let pollable respond
                    self.handle_events(events)
                else:
                    # went out on timeout. Call on_idle for all pollables
                    self.timeout_event()

            except Exception as e:
                logging.critical(traceback.print_exc())
                self.close_all()
        logging.debug("SERVER TERMINATING")

    ## Creates a new poller based on the poll type specified in the
    ## application_context
    ## @returns poll_obj (poller object) returns a poller object
    def create_poller(self):
        poll_obj = self._application_context["poll_type"]()

        for fd, entry in self._pollables.items():
            poll_obj.register(
                fd,
                entry.get_events()
            )
        return poll_obj

    ## Pollables property
    ## @returns pollables (dict)
    @property
    def pollables(self):
        return self._pollables

    ## Pollables property setter
    ## @param pollables (dict)
    @pollables.setter
    def pollables(self, p):
        self._pollables = p

    ## Function that gracefully closes and terminates the sockets that need
    ## terminating.
    ## If a pollable doesn't want to close after on_close it must be a
    ## callable so add to the callables list.
    def close_needed(self):
        for fd, entry in self._pollables.items()[:]:
            if entry.is_terminating():
                entry.on_close()
                # if socket still doesn't want to close before terminate
                # then add it callables list to be closed when wanted
                self._callables.append(entry)
                del self._pollables[fd]

        for closed_socket in self._callables:
            # check if finally ready to terminate
            if entry.is_terminating():
                del closed_socket

    ## Forcefully close all sockets
    def close_all(self):
        for fd, entry in self._pollables.items()[:]:
            entry.on_close()
            del self._pollables[fd]
