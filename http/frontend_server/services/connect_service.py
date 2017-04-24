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
from http.frontend_server.services import management_service
from http.frontend_server.utilities import cache
from http.frontend_server.utilities import disk_util
from http.frontend_server.utilities import disk_manager


# This service adds thewanted disk back to the disk array,
# Rebuilding of the disk is done by the RebuildCallable, which is called
# upon finishing of this connection service. Cannot be done in one service
# because client is waiting for answer on management, has to be done
# "in the background"

class ConnectService(base_service.BaseService):

    (
        SETUP_STATE,
        GET_DATA_STATE,
        SET_DATA_STATE,
    )=range(3)

    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(
            self,
            [],
            ["disknum", "address"],
            args
        )
        self._disks = entry.application_context["disks"]
        self._disknum = None

        self._disk_built = False
        self._state = ConnectService.GET_DATA_STATE

        self._current_blocknum = ""
        self._current_data = ""
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
                "service" : "/getblock",
                "content" : ""
            }
        if self._disknum is not None:
            self._client_contexts[self._disknum]["service"] = "/setblock"

    #checks if and how the disk needs to be rebuilt, returns False if not
    def initial_setup(self, entry):
        self._disknum = int(self._args["disknum"][0])
        address = util.make_address(self._args["address"][0])

        #see if we are dealing with a familiar disk or not
        if self._disks[self._disknum]["address"] != address:
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


    def before_response_status(self, entry):
        #initial_setup, also check if we need to add thid disk out of no-where
        self.initial_setup(entry)

        #Re-send the management part
        self._response_content = html_util.create_html_page(
            "",
            refresh=0,
            redirect_url=management_service.ManagementService.get_name()
        )
        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True

    #REBULD PART, DONE BEFORE TERMINATE (AFTER CLOSE)
    def before_terminate(self, entry):
        self.rebuild_disk(entry)
        #wait for callables to finish the current task
        entry.state = constants.SLEEPING_STATE

    #checks if self._disknum is built
    def check_if_built(self):
        #check if already connected, no need to rebuild, or cache is empty
        if (
            self._disks[self._disknum]["state"] == constants.REBUILD
            and not self._disks[self._disknum]["cache"].is_empty()
        ):
            return False
        return True

    def on_finish(self, entry):
        if not self._disk_manager.check_if_finished():
            return
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code"
            )

        client_responses = self._disk_manager.get_responses()

        if self._state == ConnectService.SETUP_STATE:
            #only got here if we have new disk that need to be updated
            #we should use functions from InitService for handling disk_info
            pass
        elif self._state == ConnectService.GET_DATA_STATE:
            #data not saved in cache, need to xor all the blocks
            blocks = []
            for disknum, response in client_responses.items():
                blocks.append(response["content"])

            #check if finished scratch mode (will wlays be this topology)
            if (
                (
                    self._disks[self._disknum]["cache"].mode
                    == cache.Cache.SCRATCH_MODE
                ) and disk_util.DiskUtil.all_empty(blocks)
            ):
                #all the blocks we got are empty, change to cache mode
                self._disks[self._disknum]["cache"].mode = (
                    cache.Cache.CACHE_MODE
                )
                #change state to set_data_state so we can start handling
                #cache mode
                self._state = ConnectService.SET_DATA_STATE
            else:
                self._current_data = disk_util.DiskUtil.compute_missing_block(
                    blocks
                )

        elif self._state == ConnectService.SET_DATA_STATE:
            pass

        self._state = ConnectService.STATES[self._state]["next"]
        self.rebuild_disk(entry)
        entry.state = constants.SLEEPING_STATE

    def rebuild_disk(self, entry):
        if self.check_if_built():
            #turn the disk online, finally connected
            self._disks[self._disknum]["state"] = constants.ONLINE
            entry.state = constants.CLOSING_STATE
            return

        while ConnectService.STATES[self._state]["function"](
            self,
            entry
        ):
            self._state = ConnectService.STATES[self._state]["next"]


    def get_data_state(self, entry):
        self._current_blocknum, self._current_data = (
            self._disks[self._disknum]["cache"].next_block()
        )
        #need to retreive data from XOR of all the disks
        if self._current_data is None:
            #client contexts are already organized,
            #self._disknum - write block
            #otherwise - read block
            self.reset_client_contexts()
            for disknum, context in self._client_contexts.items():
                self._client_contexts[disknum]["args"] = {
                    "blocknum" : self._current_blocknum
                }

            self._disk_manager = disk_manager.DiskManager(
                self._socket_data,
                entry,
                {
                    k : v for k, v in self._client_contexts.items()
                    if k != self._disknum
                }
            )
            return False
        return True

    def set_data_state(self, entry):
        self.reset_client_contexts()
        self._client_contexts[self._disknum]["args"] = {
            "blocknum" : self._current_blocknum
        }
        self._client_contexts[self._disknum]["content"] = self._current_data

        self._disk_manager = disk_manager.DiskManager(
            self._socket_data,
            entry,
            {self._disknum : self._client_contexts[self._disknum]}
        )
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
