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

from http.common.utilities import constants
from http.common.utilities import util
from http.frontend_server.pollables import bds_client_socket
from http.frontend_server.utilities import disk_util


# Manages multiple disk requests, and notifies when
# all disks have requests have gotten a response.
class DiskManager(object):
    def __init__(self, pollables, parent, client_contexts):
        #client_contexts : { disk_num : context}
        self._pollables = pollables
        self._parent = parent
        self._disk_requests = {}
        self._disks = parent.application_context["disks"]
        for disk_num, context in client_contexts.items():
            #add to database
            self._disk_requests[disk_num] = {
                "context" : context,
                "update" : {
                    "finished" : False,
                    "status" : "",
                    "content" : "",
                }
            }
            #if disk is in offline state, don't even try to connect,
            if self._disks[disk_num]["state"] == constants.OFFLINE:
                raise util.DiskRefused(disk_num)

            #try to add the client to pollables
            disk_util.add_bds_client(
                parent,
                self._disk_requests[disk_num]["context"],
                self._disk_requests[disk_num]["update"],
                pollables
            )
        #set parent to sleeping state until finished
        self._parent.state = constants.SLEEPING_STATE

    #returns a dict of { disk_num : response }
    def get_responses(self):
        ret = {}
        for disk_num, request in self._disk_requests.items():
            ret[disk_num] = request["update"]
        return ret


    #checks if al responses have the recvd status code, useful
    def check_common_status_code(self, common_status_code):
        for disk_num, response in self._disk_requests.items():
            if response["update"]["status"] != common_status_code:
                return False
        return True

    # simple function that checks if all the disks have gotten a response
    # if so, returns the common_status_code otherwise raises error
    def check_if_finished(self):
        #check easy case first
        if len(self._disk_requests) == 0:
            return True

        for disk_num, data in self._disk_requests.items():
            if not data["update"]["finished"]:
                return False

        common_status_code = self._disk_requests[
            self._disk_requests.keys()[0]
        ]["update"]["status"]
        for disk_num, data in self._disk_requests.items():
            if data["update"]["status"] != common_status_code:
                raise RuntimeError(
                    "Got a different status code from disk %s, %s"
                    % (
                        data["update"]["status"],
                        common_status_code
                    )
                )
        return True
