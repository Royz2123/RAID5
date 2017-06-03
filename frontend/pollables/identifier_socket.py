#!/usr/bin/python
## @package RAID5.frontend.pollables.identfier_socket
# Module that defines the Frontend IdentifierSocket
#

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

## A Frontend Socket that listens to a UDP Multicast group address and
## tries to recognize Block Device Servers. The IdentifierSocket also handles
## the available_disks database.
## See also @ref block_device.pollables.declarer_socket.DeclarerSocket
#
class IdentifierSocket(pollable.Pollable):

    ## Constructor for IdentifierSocket
    # @param socket (socket) async socket we work with
    # @param application_context (dict) the application_context for
    # the Frontend server
    def __init__(self, socket, application_context):
        ## Application_context
        self._application_context = application_context

        ## Socket to work with
        self._socket = socket

        ## File descriptor of socket
        self._fd = socket.fileno()

        ## Data the IdentfierSocket has recieved.
        self._recvd_data = {}


    ## Function that specifies what socket is to do when system is on_idle
    ## declares itself using multicast
    def on_idle(self):
        self.update_disconnected()

    ## What IdentifierSocket does on read.
    ## First read from socket, to see what Block Devices we discovered.
    ## Func required by @ref common.pollables.pollable.Pollable
    def on_read(self):
        try:
            buf, address = self._socket.recvfrom(constants.BLOCK_SIZE)
            self.update_disk(buf, address)
        except BaseException:
            pass

    ## Updates the disconnected Block Devices from the available_disks
    ## database. Checks if last update was after DISCONNECT_TIME or
    ## TERMINATE_TIME, and handles accordingly.
    def update_disconnected(self):
        for disk_UUID, disk in self._application_context[
            "available_disks"
        ].items():
            if (time.time() - disk["timestamp"]) > constants.DISCONNECT_TIME:
                # Set disk to unavailable
                disk["state"] = constants.OFFLINE

                # Set the volume disk to offline too
                for volume_UUID, volume in self._application_context[
                    "volumes"
                ].items():
                    if disk_UUID in volume["disks"].keys():
                        print 'heyyy'
                        volume["disks"][disk_UUID]["state"] = constants.OFFLINE
            if (time.time() - disk["timestamp"]) > constants.TERMINATE_TIME:
                del self._application_context["available_disks"][disk_UUID]

    ## Updates a disk that has been recognized by the IdentifierSocket
    ## @param buf (string) buffer needed for parsing from the socket
    ## @param address (tuple) address from which the packet was recvd
    def update_disk(self, buf, address):
        # update the recd data from this address
        if address not in self._recvd_data.keys():
            self._recvd_data[address] = ""
        self._recvd_data[address] += buf

        # split recvd content
        content = self._recvd_data[address].split(constants.MY_SEPERATOR)

        # check if got entire decleration
        if "" not in content:
            return

        # clear recvd data from this address so we can wait for new
        # declerations
        self._recvd_data[address] = ""

        # Check if volume_UUID is in volumes
        if (
            content[2] == ""
            or content[2] in self._application_context["volumes"].keys()
        ):
            # update the disk in available_disks
            self._application_context["available_disks"][content[0]] = {
                "disk_UUID": content[0],
                "state": constants.ONLINE,
                "UDP_address": address,
                "TCP_address": (address[0], int(content[1])),
                "timestamp": time.time(),
                "volume_UUID": content[2]
            }

    ## Specifies what events the IdentifierSocket listens to.
    ## required by @ref common.pollables.pollable.Pollable
    # @returns event (event_mask)
    def get_events(self):
        return constants.POLLERR | constants.POLLIN

    ## When IdentifierSocket is terminating.
    ## required by @ref common.pollables.pollable.Pollable
    ## will not terminate as long as server is running
    ## @returns is_terminating (bool)
    def is_terminating(self):
        return False

    ## File descriptor property
    ## @returns file descriptor (int) of the socket
    @property
    def fd(self):
        return self._fd

    ## What IdentifierSocket does on close.
    ## required by @ref common.pollables.pollable.Pollable
    ## will not close as long as server is running
    def on_close(self):
        self._socket.close()

    ## representation of IdentifierSocket Object
    # @returns (str) representation
    def __repr__(self):
        return ("IdentifierSocket Object: %s\t\t\t" % self._fd)
