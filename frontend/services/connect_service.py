#!/usr/bin/python
## @package RAID5.frontend.services.connect_service
## Module that implements the ConnectService class. Service brings a disk
## back online to a volume.
#

import errno
import logging
import os
import socket
import time
import traceback

from block_device.services import update_level_service
from common.services import base_service
from common.utilities import constants
from common.utilities import html_util
from common.utilities import util
from frontend.pollables import bds_client_socket
from frontend.services import display_disks_service
from frontend.utilities import cache
from frontend.utilities import disk_manager
from frontend.utilities import disk_util
from frontend.utilities import service_util
from common.utilities.state_util import state
from common.utilities.state_util import state_machine

## Frontend ConnectService. This service adds the wanted disk back to the disk
## array. Rebuilding of the disk is done after terminate, since it has to be
## done in the background after socket has been closed, as a callable
class ConnectService(base_service.BaseService):

    ## Constructor for ConnectService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(ConnectService, self).__init__(
            [],
            ["disk_UUID", "volume_UUID"],
            args
        )

        ## Volume we're dealing with
        self._volume = None

        ## Disks we're dealing with
        self._disks = None

        ## Disk UUID of connected disk
        self._disk_UUID = None

        ## Mode of adding a new disk
        self._new_disk_mode = False

        ## Disk already built boolean
        self._disk_built = False

        ## StateMachine object
        self._state_machine = None

        ## Current block num (for rebuilding)
        self._current_block_num = ""

        ## Current data (for rebuilding)
        self._current_data = ""

        ## pollables of the Frontend server
        self._pollables = pollables

        ## Disk Manager that manages all the clients
        self._disk_manager = None

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/connect"

    ## Checks if and how the disk needs to be rebuilt.
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns need_rebuild (bool) if needs to be rebuilt
    def initial_setup(self, entry):
        self._disk_UUID = self._args["disk_UUID"][0]
        self._volume_UUID = self._args["volume_UUID"][0]

        # first check validity of volume
        if (
            self._volume_UUID not in entry.application_context["volumes"].keys(
            ) or
            (
                entry.application_context["volumes"][self._volume_UUID][
                    "volume_state"
                ] != constants.INITIALIZED
            )
        ):
            raise RuntimeError("%s:\t Need to initialize volume" % (
                entry,
            ))

        self._volume = entry.application_context["volumes"][self._volume_UUID]
        self._disks = self._volume["disks"]

        # now check validity of disk_UUID
        if self._disk_UUID not in self._disks.keys():
            raise RuntimeError("%s:\t Disk not part of volume" % (
                entry,
            ))

        # sanity check that this level is no more than all the others:
        for disk_UUID, disk in self._disks.items():
            if (
                disk_UUID != self._disk_UUID and
                (
                    disk["level"] <
                    self._disks[self._disk_UUID]["level"]
                )
            ):
                raise RuntimeError("Error in levels")

        self._disks[self._disk_UUID]["state"] = constants.REBUILD

    ## Before pollable sends response status service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_status(self, entry):
        # initial_setup, also check if we need to add thid disk out of no-where
        self.initial_setup(entry)

        # Re-send the management part
        self._response_content = html_util.create_html_page(
            "",
            constants.HTML_DISPLAY_HEADER,
            0,
            display_disks_service.DisplayDisksService.get_name(),
        )
        self._response_headers = {
            "Content-Length": "%s" % len(self._response_content),
        }
        return True

    # REBULD PART, DONE BEFORE TERMINATE (AFTER CLOSE)

    ## Rebuilding States
    (
        GET_DATA_STATE,
        SET_DATA_STATE,
        UPDATE_LEVEL_STATE,
        FINAL_STATE
    ) = range(4)

    # STATE FUNCTIONS:

    ## Before we get the rebulding data
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_get_data(self, entry):
        self._current_block_num, self._current_data = (
            self._disks[self._disk_UUID]["cache"].next_block()
        )
        if self._current_data is not None:
            # got data stored in cache, no need for hard rebuild
            # ==> This is an epsilon_path
            return True
        else:
            # need to retreive data from XOR of all the disks besides the current
            # in order to rebuild it
            request_info = {}
            for disk_UUID in self._disks.keys():
                if disk_UUID != self._disk_UUID:
                    request_info[disk_UUID] = {
                        "block_num" : self._current_block_num,
                        "password" : self._volume["long_password"]
                    }

            self._disk_manager = disk_manager.DiskManager(
                self._disks,
                self._pollables,
                entry,
                service_util.create_get_block_contexts(
                    self._disks,
                    request_info
                )
            )
            entry.state = constants.SLEEPING_STATE
            return False  # need input, not an epsilon path

    ## After we get the rebulding data
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
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

        # data not saved in cache, need to xor all the blocks
        blocks = []
        for disk_num, response in self._disk_manager.get_responses().items():
            blocks.append(response["content"])

        # check if finished scratch mode for cache
        if (
            (
                self._disks[self._disk_UUID]["cache"].mode ==
                cache.Cache.SCRATCH_MODE
            ) and disk_util.all_empty(blocks)
        ):
            # all the blocks we got are empty, change to cache mode
            self._disks[self._disk_UUID]["cache"].mode = (
                cache.Cache.CACHE_MODE
            )
            # nothing to set now, we stay in GET_DATA_STATE and start working
            # from cache
            return ConnectService.GET_DATA_STATE
        else:
            self._current_data = disk_util.compute_missing_block(
                blocks
            )
            return ConnectService.SET_DATA_STATE

    ## Before we set the rebulding data
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_set_data(self, entry):
        self._disk_manager = disk_manager.DiskManager(
            self._disks,
            self._pollables,
            entry,
            service_util.create_set_block_contexts(
                self._disks,
                {
                    self._disk_UUID: {
                        "block_num": self._current_block_num,
                        "content": self._current_data,
                        "password" : self._volume["long_password"]
                    }
                }
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False  # need input, not an epsilon path


    ## After we set the rebulding data
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
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

    ## Before we update the level of the updated disk
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_update_level(self, entry):
        self._disk_manager = disk_manager.DiskManager(
            self._disks,
            self._pollables,
            entry,
            service_util.create_update_level_contexts(
                self._disks,
                {
                    self._disk_UUID: {
                        "addition" : "1",
                        "password" : self._volume["long_password"]
                    }
                }
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False  # need input, not an epsilon path

    ## Before we have updated the level of the updated disk
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
    def after_update_level(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code"
            )

        self._disks[self._disk_UUID]["level"] += 1
        self._disks[self._disk_UUID]["state"] = constants.ONLINE
        entry.state = constants.CLOSING_STATE
        return ConnectService.FINAL_STATE

    ## Rebuilding states for StateMachine
    STATES = [
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

    ## Before pollable terminates service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_terminate(self, entry):
        # create the state machine for rebuilding disk
        first_state_index = ConnectService.GET_DATA_STATE
        if self._new_disk_mode:
            first_state_index = ConnectService.NEW_DISK_SETUP_STATE
        elif self.check_if_built():
            first_state_index = ConnectService.UPDATE_LEVEL_STATE

        # create rebuild state machine
        self._state_machine = state_machine.StateMachine(
            ConnectService.STATES,
            ConnectService.STATES[first_state_index],
            ConnectService.STATES[ConnectService.FINAL_STATE]
        )
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    ## Called when BDSClientSocket invoke the on_finsh method to wake up
    ## the ServiceSocket. Let StateMachine handle the wake up call.
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    def on_finish(self, entry):
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    ## Checks if self._disk_UUID is built
    ## @returns built (bool) if disk needs to be rebuilt
    def check_if_built(self):
        # check if already connected, no need to rebuild, or cache is empty
        if (
            self._disks[self._disk_UUID]["state"] == constants.REBUILD and
            not self._disks[self._disk_UUID]["cache"].is_empty()
        ):
            return False
        return True
