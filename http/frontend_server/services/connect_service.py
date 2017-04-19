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

from http.bds_server.services import update_level_service
from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import html_util
from http.common.utilities import util
from http.frontend_server.pollables import bds_client_socket
from http.frontend_server.utilities import cache
from http.frontend_server.utilities import disk_util
from http.frontend_server.utilities import disk_manager


# This service adds thewanted disk back to the disk array,
# Rebuilding of the disk is done by the RebuildCallable, which is called
# upon finishing of this connection service. Cannot be done in one service
# because client is waiting for answer on management, has to be done
# "in the background"

class ConnectService(base_service.BaseService):
    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(
            self,
            [],
            ["disknum", "address"],
            args
        )
        self._disks = entry.application_context["disks"]
        self._disknum = None

        self._current_block = ""
        self._socket_data = socket_data

        self._disk_built = False
        self._state = ConnectService.GET_DATA_STATE

        self._current_block = ""
        self._socket_data = socket_data

        self._disk_manager = None
        self._client_contexts = {}

    @staticmethod
    def get_name():
        return "/connect"

    def reset_client_contexts(self):
        self._client_contexts = {}
        for disknum in range(len(self._disks)):
            self._client_contexts[disknum] = {
                "headers" : {},
                "args" : {},
                "disknum" : disknum,
                "disk_address" : self._disks[disknum]["address"],
                "method" : "GET",
                "service" : "/%s%s" % (
                    constants.DISK_INFO_NAME,
                    disknum,
                ),
                "content" : ""
            }

    #checks if and how the disk needs to be rebuilt, returns False if not
    def check_if_rebuild(self, entry):
        self._disknum = int(self._args["disknum"][0])
        address = util.make_address(self._args["address"][0])

        #check if already connected, no need to rebuild
        if self._disks[self._disknum]["state"] == constants.ONLINE:
            return False

        if self._disks[self._disknum]["address"] == address:
            #if theres no cache to be updated, no need to rebuild
            if self._disks[self._disknum]["cache"].is_empty():
                return False
        else:
            #check we don't already have this address in the system
            for disknum in range(len(self._disks)):
                if (
                    disknum != self._disknum
                    and address == self._disks[disknum]["address"]
                ):
                    raise RuntimeError("Can't connect to the same disk twice")

            #update the disk address and cache
            self._disks[self._disknum]["address"] = address
            self._disks[self._disknum]["cache"] = cache.Cache(
                mode=cache.Cache.SCRATCH_MODE
            )

            #TODO: need to get new UUID from disk
            # self.reset_client_contexts()
            # self._disk_manager = disk_manager.DiskManager(
            #    self._socket_data,
            #    entry,
            #    {self._disknum : self._client_contexts[self._disknum]}
            #)


        #sanity check that this level is one less than all the others:
        for disknum in range(len(self._disks)):
            if (
                disknum != self._disknum
                and (
                    self._disks[disknum]["level"]
                    <= self._disks[self._disknum]["level"]
                )
            ):
                raise RuntimeError("Error in levels")

        self._disks[self._disknum]["state"] = constants.REBUILD
        return True

    def before_response_status(self, entry):
        #note if there is need for rebuilding the disk
        if not self.check_if_rebuild(entry):
            self._disk_built = True

        print self._disks[self._disknum]["state"]
        #Re-send the management part
        self._response_content = html_util.create_html_page(
            html_util.create_disks_table(entry.application_context["disks"]),
            constants.HTML_MANAGEMENT_HEADER,
        )
        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True


    #REBULD PART, DONE AFTER TERMINATE
    (
        GET_DATA_STATE,
        SET_DATA_STATE
    )=range(2)

    def after_terminate(self, entry):
        if self._disk_built:
            return
        entry.state = constants.SLEEPING_STATE
        self.rebuild_disk(entry)

    def on_finish(self, entry):
        if not self._disk_manager.check_if_finished():
            return
        self._client_responses = self._disk_manager.get_responses()

        if self._state == ConnectService.GET_DATA_STATE:
            if not self._disk_manager.check_common_status_code("200"):
                raise RuntimeError(
                    "Block Device Server sent a bad status code"
                )

        elif self._state == InitService.HANDLE_INFO_STATE:
            #check if got a response from ALL of the
            #block devices:
            if not self._disk_manager.check_common_status_code("200"):
                raise RuntimeError(
                    "Block Device Server sent a bad status code: %s"
                    % (
                        client_responses[0]["status"]
                    )
                )

        self._state = InitService.STATES[self._state]["next"]


    def rebuild_disk(self, entry):
        while True:
            next_state = ConnectService.STATES[self._state]["function"](
                self,
                entry
            )
            if next_state == 0:
                return False
            elif (
                self._state == ConnectService.SET_DATA_STATE
                and next_state == 2
            ):
                break
            self._state = ConnectService.STATES[self._state]["next"]

        return True


    def get_data_state(self, entry):
        blocknum, data = self._disks[self._disknum]["cache"].next_block()

        #need to retreive data from XOR of all the disks
        if data is None:

            entry.state = constants.SLEEPING_STATE

        self._current_block


    def set_data_state(self, entry):
        entry.state = constants.SLEEPING_STATE
        return False


    STATES = {
        GET_DATA_STATE: {
            "function": get_data_state,
            "next": SET_DATA_STATE,
        },
        SET_DATA_STATE: {
            "function": set_data_state,
            "next": GET_DATA_STATE
        },
    }
