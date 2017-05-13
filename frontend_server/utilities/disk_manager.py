# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import time
import traceback

from common.utilities import constants
from common.utilities import util
from frontend_server.pollables import bds_client_socket
from frontend_server.utilities import disk_util


# Manages multiple disk requests, and notifies when
# all disks have requests have gotten a response.
class DiskManager(object):
    def __init__(self, disks, pollables, parent, client_contexts):
        #client_contexts : { disk_UUID : context}
        self._pollables = pollables
        self._parent = parent
        self._disk_requests = {}
        self._disks = disks

        for disk_UUID, context in client_contexts.items():
            #add to database
            self._disk_requests[disk_UUID] = {
                "context" : context,
                "update" : {
                    "finished" : False,
                    "status" : "",
                    "content" : "",
                }
            }
            #if disk is in offline state, don't even try to connect,
            if self._disks[disk_UUID]["state"] == constants.OFFLINE:
                raise util.DiskRefused(disk_UUID)

            #try to add the client to pollables
            disk_util.add_bds_client(
                parent,
                self._disk_requests[disk_UUID]["context"],
                self._disk_requests[disk_UUID]["update"],
                pollables
            )
        #set parent to sleeping state until finished
        self._parent.state = constants.SLEEPING_STATE

    #returns a copy dict of { disk_UUID : response }
    def get_responses(self):
        ret = {}
        for disk_UUID, request in self._disk_requests.items():
            ret[disk_UUID] = request["update"]
        return ret


    #checks if al responses have the recvd status code, useful
    def check_common_status_code(self, common_status_code):
        for disk_UUID, response in self._disk_requests.items():
            if response["update"]["status"] != common_status_code:
                return False
        return True

    # simple function that checks if all the disks have gotten a response
    # if so, returns the common_status_code otherwise raises error
    def check_if_finished(self):
        #check easy case first
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
