# -*- coding: utf-8 -*-
import contextlib
import datetime
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

# This service adds the wanted disk back to the disk array,
# Rebuilding of the disk is done after terminate, since it has to be done in the
# background


class ConnectService(base_service.BaseService):
    def __init__(self, entry, socket_data, args):
        super(ConnectService, self).__init__(
            [],
            ["disk_UUID", "volume_UUID"],
            args
        )
        self._volume = None
        self._disks = None
        self._disk_UUID = None
        self._new_disk_mode = False

        self._disk_built = False
        self._state_machine = None

        self._current_block_num = ""
        self._current_data = ""
        self._socket_data = socket_data

        self._disk_manager = None

    @staticmethod
    def get_name():
        return "/connect"

    # checks if and how the disk needs to be rebuilt, returns False if not
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

        # sanity check that this level is one less than all the others:
        for disk_UUID, disk in self._disks.items():
            if (
                disk_UUID != self._disk_UUID and
                (
                    disk["level"] <=
                    self._disks[self._disk_UUID]["level"]
                )
            ):
                raise RuntimeError("Error in levels")

        self._disks[self._disk_UUID]["state"] = constants.REBUILD

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
    (
        GET_DATA_STATE,
        SET_DATA_STATE,
        UPDATE_LEVEL_STATE,
        FINAL_STATE
    ) = range(4)

    # STATE FUNCTIONS:

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
                self._socket_data,
                entry,
                service_util.create_get_block_contexts(
                    self._disks,
                    request_info
                )
            )
            entry.state = constants.SLEEPING_STATE
            return False  # need input, not an epsilon path

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

    def before_set_data(self, entry):
        self._disk_manager = disk_manager.DiskManager(
            self._disks,
            self._socket_data,
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
            self._disks,
            self._socket_data,
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

    def on_finish(self, entry):
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    # checks if self._disk_UUID is built
    def check_if_built(self):
        # check if already connected, no need to rebuild, or cache is empty
        if (
            self._disks[self._disk_UUID]["state"] == constants.REBUILD and
            not self._disks[self._disk_UUID]["cache"].is_empty()
        ):
            return False
        return True
