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

class ConnectService(base_service.BaseService):
    (
        GET_DATA_STATE,
        SET_DATA_STATE
    )=range(2)

    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(
            self,
            [],
            ["disknum", "address"],
            args
        )
        self._disks = entry.application_context["disks"]
        self._disknum = None
        self._mode = None
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

    def on_finish(self, entry):
        if not self._disk_manager.check_if_finished():
            return
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Got bad status code from BDS"
            )

        #finished smoothly, update levels on frontend disks
        for disknum in range(len(self._disks)):
            if disknum != self._disknum:
                self._disks[disknum]["level"] += 1
        entry.state = constants.SEND_HEADERS_STATE

    def decide_connection(self, entry):
        self._disknum = int(self._args["disknum"][0])
        address = util.make_address(self._args["address"][0])

        if self._disks[self._disknum]["state"] == constants.ONLINE:  #check if already connected
            return

        self._mode = cache.Cache.CACHE_MODE
        if self._disks[self._disknum]["address"] != address:
            #check we don't already have this address in the system
            for disknum in range(len(self._disks)):
                if (
                    disknum != self._disknum
                    and address == self._disks[disknum]["address"]
                ):
                    raise RuntimeError("Can't connect to the same disk twice")

            #will need to rebuild the disk from scratch
            self._mode = cache.Cache.SCRATCH_MODE

            #update the disk address
            self._disks[self._disknum]["address"] = address
            self._disks[self._disknum]["cache"] = cache.Cache(
                mode=cache.Cache.SCRATCH_MODE
            )

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

    def before_response_status(self, entry):
        #first decide on adding mode (cache or scratch then cache)
        if self._mode is None:
            self.decide_connection(entry)

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

    def before_response_headers(self, entry):
        #Re-send the management part
        self._response_content = html_util.create_html_page(
            html_util.create_disks_table(entry.application_context["disks"]),
            constants.HTML_MANAGEMENT_HEADER,
            constants.DEFAULT_REFRESH_TIME
        )
        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True
