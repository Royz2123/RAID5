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
from http.frontend_server.utilities import disk_manager
from http.frontend_server.utilities import disk_util
from http.frontend_server.utilities import service_util
from http.frontend_server.utilities.state_util import state
from http.frontend_server.utilities.state_util import state_machine

# This service adds the wanted disk back to the disk array,
# Rebuilding of the disk is done after terminate, since it has to be done in the
# background

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
        self._new_disk_mode = False

        self._disk_built = False
        self._state_machine = None

        self._current_blocknum = ""
        self._current_data = ""
        self._socket_data = socket_data

        self._disk_manager = None

    @staticmethod
    def get_name():
        return "/connect"

    #checks if and how the disk needs to be rebuilt, returns False if not
    def initial_setup(self, entry):
        self._disknum = int(self._args["disknum"][0])
        address = util.make_address(self._args["address"][0])

        #see if we are dealing with a familiar disk or not
        if self._disks[self._disknum]["address"] != address:
            self._new_disk_mode = True
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
            self._disks[self._disknum]["disk_UUID"] = "UKNOWN"

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
    (
        NEW_DISK_SETUP_STATE,
        GET_DATA_STATE,
        SET_DATA_STATE,
        UPDATE_LEVEL_STATE,
        FINAL_STATE
    )=range(5)

    #STATE FUNCTIONS:

    def before_new_disk_setup(self, entry):
        #get info file from the new disk
        self._disk_manager = disk_manager.DiskManager(
            self._socket_data,
            entry,
            service_util.create_get_disk_info_contexts(
                self._disks,
                [self._disknum]
            )
        )
        return False     #need input, not an epsilon path

    def after_new_disk_setup(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        elif self._disk_manager.check_common_status_code("404"):
            raise RuntimeError(
                "New Block Device doesn't have a disk info file"
            )
        elif not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code"
            )

        #update the new uuid from the disk file, and check that the new disk
        # is part of the system
        disk_data = (
            self._disk_manager.get_responses()[self._disknum]["content"].split(
                constants.CRLF_BIN
            )
        )
        comparable_disknum = not self._disknum

        #lets check that the common_uuid is identical:
        if disk_data[1] != self._disks[comparable_disknum]["common_UUID"]:
            raise RuntimeError(
                "Got two different topoligies: \n%s\n%s" % (
                    disk_data[1],
                    self._disks[comparable_disknum]["common_UUID"]
                )
            )

        self._disks[self._disknum]["disk_UUID"] = disk_data[2]

        #move on to rebuilding disk
        if self.check_if_built():
            return ConnectService.UPDATE_LEVEL_STATE
        return ConnectService.GET_DATA_STATE

    def before_get_data(self, entry):
        self._current_blocknum, self._current_data = (
            self._disks[self._disknum]["cache"].next_block()
        )
        if self._current_data is not None:
            #got data stored in cache, no need for hard rebuild
            # ==> This is an epsilon_path
            return True
        else:
            #need to retreive data from XOR of all the disks besides the current
            #in order to rebuild it
            request_info = {}
            for disknum in range(len(self._disks)):
                if disknum != self._disknum:
                    request_info[disknum] = self._current_blocknum

            self._disk_manager = disk_manager.DiskManager(
                self._socket_data,
                entry,
                service_util.create_get_block_contexts(
                    self._disks,
                    request_info
                )
            )
            entry.state = constants.SLEEPING_STATE
            return False     #need input, not an epsilon path

    def after_get_data(self, entry):
        # first check if the data has come from the cache
        if self._current_data is not None:
            return ConnectService.SET_DATA_STATE

        # now we know that the data has come from the other disks. check if
        # they all finished and their responses
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code"
            )

        #data not saved in cache, need to xor all the blocks
        blocks = []
        for disknum, response in self._disk_manager.get_responses().items():
            blocks.append(response["content"])

        #check if finished scratch mode for cache
        if (
            (
                self._disks[self._disknum]["cache"].mode
                == cache.Cache.SCRATCH_MODE
            ) and disk_util.all_empty(blocks)
        ):
            #all the blocks we got are empty, change to cache mode
            self._disks[self._disknum]["cache"].mode = (
                cache.Cache.CACHE_MODE
            )
            #nothing to set now, we stay in GET_DATA_STATE and start working
            #from cache
            return ConnectService.GET_DATA_STATE
        else:
            self._current_data = disk_util.compute_missing_block(
                blocks
            )
            return ConnectService.SET_DATA_STATE

    def before_set_data(self, entry):
        self._disk_manager = disk_manager.DiskManager(
            self._socket_data,
            entry,
            service_util.create_set_block_contexts(
                self._disks,
                {
                    self._disknum : {
                        "blocknum" : self._current_blocknum,
                        "content" : self._current_data
                    }
                }
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False     #need input, not an epsilon path

    def after_set_data(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code"
            )

        if self.check_if_built():
            return ConnectService.UPDATE_LEVEL_STATE
        return ConnectService.GET_DATA_STATE


    def before_update_level(self, entry):
        self._disk_manager = disk_manager.DiskManager(
            self._socket_data,
            entry,
            service_util.create_update_level_contexts(
                self._disks,
                { self._disknum : "1"}
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False     #need input, not an epsilon path

    def after_update_level(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code"
            )

        self._disks[self._disknum]["level"] += 1
        self._disks[self._disknum]["state"] = constants.ONLINE
        entry.state = constants.CLOSING_STATE
        return ConnectService.FINAL_STATE

    STATES = [
        state.State(
            NEW_DISK_SETUP_STATE,
            [GET_DATA_STATE],
            before_new_disk_setup,
            after_new_disk_setup,
        ),
        state.State(
            GET_DATA_STATE,
            [SET_DATA_STATE],
            before_get_data,
            after_get_data,
        ),
        state.State(
            SET_DATA_STATE,
            [GET_DATA_STATE, UPDATE_LEVEL_STATE],
            before_set_data,
            after_set_data,
        ),
        state.State(
            UPDATE_LEVEL_STATE,
            [FINAL_STATE],
            before_update_level,
            after_update_level,
        ),
        state.State(
            FINAL_STATE,
            [FINAL_STATE],
        ),
    ]

    def before_terminate(self, entry):
        #create the state machine for rebuilding disk
        first_state_index = ConnectService.GET_DATA_STATE
        if self._new_disk_mode:
            first_state_index = ConnectService.NEW_DISK_SETUP_STATE
        elif self.check_if_built():
            first_state_index = ConnectService.UPDATE_LEVEL_STATE

        #create rebuild state machine
        self._state_machine = state_machine.StateMachine(
            ConnectService.STATES,
            ConnectService.STATES[first_state_index],
            ConnectService.STATES[ConnectService.FINAL_STATE]
        )
        #pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    def on_finish(self, entry):
        #pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    #checks if self._disknum is built
    def check_if_built(self):
        #check if already connected, no need to rebuild, or cache is empty
        if (
            self._disks[self._disknum]["state"] == constants.REBUILD
            and not self._disks[self._disknum]["cache"].is_empty()
        ):
            return False
        return True
