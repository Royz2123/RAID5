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
from common.utilities import util


## A Block Device Socket that declares the server using UDP Multicast to other
## Frontend Servers to recognize
#
class DeclarerSocket(pollable.Pollable):

    ## Constructor for DeclareSocket
    # @param socket (socket) async socket we work with
    # @param application_context (dict) the application_context for the block device
    #
    def __init__(self, socket, application_context):
        ## Application_context
        self._application_context = application_context

        ## Socket to work with
        self._socket = socket

        ## File descriptor of socket
        self._fd = socket.fileno()

        ## Mulricast group address
        self._group_address = (
            str(self._application_context["multicast_group"]["address"]),
            int(self._application_context["multicast_group"]["port"])
        )

    ## Function that specifies what socket is to do when system is on_idle
    # declares itself using multicast
    def on_idle(self):
        self._socket.sendto(
            self.create_content(),
            self._group_address,
        )

    ## Creates the decleration content
    def create_content(self):
        return (
            "%s%s%s%s%s%s" % (
                self._application_context["server_info"]["disk_uuid"],
                constants.CRLF_BIN,
                self._application_context["bind_port"],
                constants.CRLF_BIN,
                self._application_context["server_info"]["volume_uuid"],
                constants.CRLF_BIN
            )
        )

    ## Specifies what events the socket listens to
    # required by @ref common.pollables.pollable.Pollable
    def get_events(self):
        return constants.POLLERR

    ## When DeclarerSocket is terminating
    # required by @ref common.pollables.pollable.Pollable
    # will not terminate as long as server is running
    def is_terminating(self):
        return False

    ## What DeclarerSocket does on close
    # required from @ref common.pollables.pollable
    # will not close as long as server is running
    def on_close(self):
        self._socket.close()

    ## Socket property
    @property
    def socket(self):
        return self._socket

    ## File descriptor property
    @property
    def fd(self):
        return self._fd

    ## representatin of DeclarerSocket Object
    # @returns (str) representation
    def __repr__(self):
        return ("DeclarerSocket Object: %s\t\t\t" % self._fd)
