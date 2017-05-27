# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util
from frontend.pollables import bds_client_socket
from frontend.utilities import disk_manager
from frontend.utilities import disk_util
from frontend.utilities import service_util
from common.utilities.state_util import state
from common.utilities.state_util import state_machine


class ReadFromDiskService(base_service.BaseService):
    (
        READ_STATE,
        FINAL_STATE
    ) = range(2)

    # read mode
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    def __init__(self, entry, pollables, args):
        super(ReadFromDiskService, self).__init__(
            ["Content-Type", "Authorization"],
            ["volume_UUID", "disk_UUID", "firstblock", "blocks"],
            args
        )
        self._pollables = pollables

        self._block_mode = ReadFromDiskService.REGULAR
        self._current_block = None
        self._current_phy_UUID = None
        self._disk_UUID = None
        self._volume_UUID = None
        self._volume = None
        self._disks = None

        self._disk_manager = None
        self._state_machine = None

    @staticmethod
    def get_name():
        return "/disk_read"

    def before_read(self, entry):
        self._current_phy_UUID = disk_util.get_physical_disk_UUID(
            self._disks,
            self._disk_UUID,
            self._current_block
        )
        try:
            self._block_mode = ReadFromDiskService.REGULAR
            self._disk_manager = disk_manager.DiskManager(
                self._disks,
                self._pollables,
                entry,
                service_util.create_get_block_contexts(
                    self._disks,
                    {
                        self._current_phy_UUID: {
                            "block_num" : self._current_block,
                            "password" : self._volume["long_password"]
                        }
                    }
                ),
            )
        except util.DiskRefused as e:
            # probably got an error when trying to reach a certain BDS
            # ServiceSocket. We shall try to get the data from the rest of
            # the disks. Otherwise, two disks are down and theres nothing
            # we can do
            logging.debug(
                "%s:\t Couldn't connect to one of the BDSServers, %s: %s" % (
                    entry,
                    self._current_phy_UUID,
                    e
                )
            )
            try:
                self._block_mode = ReadFromDiskService.RECONSTRUCT

                # create request info for all the other disks
                request_info = {}
                for disk_UUID in self._disks.keys():
                    if disk_UUID != self._current_phy_UUID:
                        request_info[disk_UUID] = {
                            "block_num" : self._current_block,
                            "password" : self._volume["long_password"]
                        }

                self._disk_manager = disk_manager.DiskManager(
                    self._disks,
                    self._pollables,
                    entry,
                    service_util.create_get_block_contexts(
                        self._disks,
                        request_info
                    ),
                )
            except socket.error as e:
                # Got another bad connection (Connection refused most likely)
                raise RuntimeError(
                    (
                        "%s:\t Couldn't connect to two of the" +
                        "BDSServers, giving up: %s"
                    ) % (
                        entry,
                        e
                    )
                )
        entry.state = constants.SLEEPING_STATE
        return False  # always need input, not an epsilon path

    def after_read(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Got bad status code from BDS"
            )

        # if we have a pending block, send it back to client
        # Get ready for next block (if there is)

        # TODO: Too much in response_content
        self.update_block()
        self._current_block += 1
        entry.state = constants.SEND_CONTENT_STATE
        if (
            self._current_block ==
            (
                int(self._args["firstblock"][0]) +
                int(self._args["blocks"][0])
            )
        ):
            return ReadFromDiskService.FINAL_STATE
        return ReadFromDiskService.READ_STATE

    # woke up from sleeping mode, checking if got required blocks
    def update_block(self):
        client_responses = self._disk_manager.get_responses()
        # regular block update
        if self._block_mode == ReadFromDiskService.REGULAR:
            self._response_content += (
                client_responses[self._current_phy_UUID]["content"].ljust(
                    constants.BLOCK_SIZE,
                    chr(0)
                )
            )

        # reconstruct block update
        elif self._block_mode == ReadFromDiskService.RECONSTRUCT:
            blocks = []
            for disk_num, response in client_responses.items():
                blocks.append(response["content"])

            self._response_content += disk_util.compute_missing_block(
                blocks).ljust(constants.BLOCK_SIZE, chr(0))

    STATES = [
        state.State(
            READ_STATE,
            [READ_STATE, FINAL_STATE],
            before_read,
            after_read
        ),
        state.State(
            FINAL_STATE,
            [FINAL_STATE]
        )
    ]

    def before_response_status(self, entry):
        # first check login
        if not util.check_user_login(entry):
            # login was unsucsessful, notify the user agent
            self._response_status = 401
            self._response_headers["WWW-Authenticate"] = "Basic realm='myRealm'"
            return True

        # login went smoothly, moving on to disk read
        self._disk_UUID = self._args["disk_UUID"][0]
        self._volume_UUID = self._args["volume_UUID"][0]

        # first check validity of volume_UUID
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

        # also checek validity of blocks requested
        if int(self._args["blocks"][0]) < 0:
            raise RuntimeError("%s:\t Invalid amount of blocks: %s" % (
                entry,
                self._args["blocks"][0]
            ))
        elif int(self._args["firstblock"][0]) < 0:
            raise RuntimeError("%s:\t Invalid first block requested: %s" % (
                entry,
                self._args["firstblock"][0]
            ))

        # could check on how many are active...
        self._response_headers = {
            "Content-Length": (
                int(self._args["blocks"][0]) *
                constants.BLOCK_SIZE
            ),
            "Content-Type": "text/html",
            "Content-Disposition": (
                "attachment; filename=blocks[%s : %s].txt"
                % (
                    int(self._args["firstblock"][0]),
                    (
                        int(self._args["blocks"][0]) +
                        int(self._args["firstblock"][0])
                    )
                )
            ),
        }
        self._current_block = int(self._args["firstblock"][0])

        # initialize state machine for reading
        first_state = ReadFromDiskService.READ_STATE
        if int(self._args["blocks"][0]) == 0:
            first_state = ReadFromDiskService.FINAL_STATE

        self._state_machine = state_machine.StateMachine(
            ReadFromDiskService.STATES,
            ReadFromDiskService.STATES[first_state],
            ReadFromDiskService.STATES[ReadFromDiskService.FINAL_STATE]
        )
        return True

    def before_response_content(self, entry):
        # first check if we have an error and we don't want to read
        if self._response_status != 200:
            return True

        # pass args to the machine, will use *args to pass them on
        # if the machine returns True, we know we can move on
        return self._state_machine.run_machine((self, entry))

    def on_finish(self, entry):
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))
