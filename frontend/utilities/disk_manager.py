#!/usr/bin/python
## @package RAID5.frontend.utilities.disk_manager
# Module that implements the DiskManager class for handling BDSClientSockets
#

import errno
import logging
import os
import socket
import time
import traceback

from common.utilities import constants
from common.utilities import util
from frontend.pollables import bds_client_socket


## DiskManager manages multiple disk requests, and notifies when
## all disks have requests have gotten a response. Many services use this
## class in order to organize requests to the Block Devices.
class DiskManager(object):

    ## Constructor for DiskManager
    ## @param disks (dict) dictionary of disks in the relevant volume
    ## @param pollables (dict) pointer to the pollables in the system so that
    ## we can add new BDSClientSockets
    ## @param parent (pollable) (usually a ServiceSocket) that called the
    ## DiskManager.
    ## @param client_contexts (dict) dictionary specifying the request
    ## contexts for each of the BDSClientSockets
    ## client_contexts -> { disk_UUID : context}
    def __init__(self, disks, pollables, parent, client_contexts):
        ## All of the pollables in the Frontend Server
        self._pollables = pollables

        ## Parent Pollable that called the DiskManager
        self._parent = parent

        ## Dict of all the disk requests
        self._disk_requests = {}

        ## Disks we are handling
        self._disks = disks

        for disk_UUID, context in client_contexts.items():
            # add to database
            self._disk_requests[disk_UUID] = {
                "context": context,
                "update": {
                    "finished": False,
                    "status": "",
                    "content": "",
                }
            }
            # if disk is in offline state, don't even try to connect,
            if self._disks[disk_UUID]["state"] == constants.OFFLINE:
                raise util.DiskRefused(disk_UUID)

            # try to add the client to pollables
            self.add_bds_client(
                parent,
                self._disk_requests[disk_UUID]["context"],
                self._disk_requests[disk_UUID]["update"],
            )
        # set parent to sleeping state until finished
        self._parent.state = constants.SLEEPING_STATE

    ## Adds a BDSClientSocket to the list of pollables
    ## @param client_context (dict) dictionary specifying the request
    ## context for the current BDSClientSocket
    ## @param client_update (dict) dictionary specifying the client_update
    ## for the current BDSClientSocket
    def add_bds_client(self, parent, client_context, client_update):
        new_socket = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        try:
            new_socket.connect((client_context["disk_address"]))
        except socket.error as e:
            # connection refused from disk! build disk refused and raise..
            raise util.DiskRefused(client_context["disk_UUID"])

        # set to non blocking
        new_socket.setblocking(0)

        # add to database, need to specify block_num
        new_bds_client = bds_client_socket.BDSClientSocket(
            new_socket,
            client_context,
            client_update,
            parent
        )
        self._pollables[new_socket.fileno()] = new_bds_client
        logging.debug(
            "%s :\t Added a new BDS client, %s"
            % (
                parent,
                new_bds_client
            )
        )

    ## Returns the client_updates from the BDSClientSockets. The responses
    ## from ech of the Block Devices
    ## @returns updates (dict) of all the updates from the client answers
    def get_responses(self):
        ret = {}
        for disk_UUID, request in self._disk_requests.items():
            ret[disk_UUID] = request["update"]
        return ret

    ## Checks if all the responses returned the same status code
    ## @param common_status_code (int) the common_status_code we're checking
    ## @returns all_common (bool) if all the responses have the same code
    def check_common_status_code(self, common_status_code):
        for disk_UUID, response in self._disk_requests.items():
            if response["update"]["status"] != common_status_code:
                return False
        return True

    ## Checks if all the disks have gotten a response. Also checks that they
    ## got the same status code.
    ## @returns all_finished (bool) if all the BDSClientSockets have finished
    def check_if_finished(self):
        # check easy case first
        if len(self._disk_requests) == 0:
            return True

        for disk_UUID, data in self._disk_requests.items():
            if not data["update"]["finished"]:
                return False

        common_status_code = self._disk_requests[
            self._disk_requests.keys()[0]
        ]["update"]["status"]
        for disk_UUID, data in self._disk_requests.items():
            if data["update"]["status"] != common_status_code:
                raise RuntimeError(
                    "Got a different status code from disk %s, %s"
                    % (
                        data["update"]["status"],
                        common_status_code
                    )
                )
        return True
