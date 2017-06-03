#!/usr/bin/python
## @package RAID5.frontend.services.read_disk_service
## Module that implements the ReadFromDiskService class. Service reads a
## certain amount of blocks from a specific disk.
#

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


## Frontend HTTP service that knwos how to process a request to read from a
## logical disk and return the content from the actual physical disk. This
## service also know how handle when the wanted disk is disconnected, and
## can still access it's content based on the RAID5 protocol.
class ReadFromDiskService(base_service.BaseService):
    ## Reading States
    (
        READ_STATE,
        FINAL_STATE
    ) = range(2)

    ## Reading Modes
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    ## Constructor for ReadFromDiskService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(ReadFromDiskService, self).__init__(
            ["Content-Type", "Authorization"],
            ["volume_UUID", "disk_num", "firstblock", "blocks"],
            args
        )
        ## Reading mode
        self._block_mode = ReadFromDiskService.REGULAR

        ## Current block_num we're reading
        self._current_block = None

        ## physical UUID of the disk we're reading from
        self._current_phy_UUID = None

        ## Logical disk num of disk we're reading from
        self._disk_num = None

        ## UUID of volume we're dealing with
        self._volume_UUID = None

        ## Volume we're dealing with
        self._volume = None

        ## Disks we're dealing with
        self._disks = None

        ## StateMachine object
        self._state_machine = None

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
        return "/disk_read"

    ## Before reading a block from the Block Devices.
    ## First try reading the block regularly. If got DiskRefused, Then read
    ## that block from all the other disks and compute the missing block.
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_read(self, entry):
        self._current_phy_UUID = disk_util.get_physical_disk_UUID(
            self._disks,
            self._disk_num,
            self._current_block
        )
        try:
            # First check availablity
            available_disks = entry.application_context["available_disks"]
            online, offline = util.sort_disks(available_disks)
            if self._current_phy_UUID not in online.keys():
                raise util.DiskRefused(self._current_phy_UUID)

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

    ## After reading from relevant block devices.
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
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

    ## Function that updates the response content with the computed block.
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

    ## Reading states for StateMachine
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

    # Before pollable sends response status service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_status(self, entry):
        # first check login
        if not util.check_user_login(entry):
            # login was unsucsessful, notify the user agent
            self._response_status = 401
            self._response_headers["WWW-Authenticate"] = "Basic realm='myRealm'"
            return True

        # login went smoothly, moving on to disk read
        self._disk_num = int(self._args["disk_num"][0])
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

        # now check validity of disk_num
        if self._disk_num < 0 or self._disk_num >= len(self._disks) - 1:
            raise RuntimeError("%s:\t Logical disk not part of volume %s " % (
                entry,
                self._disk_num,
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

    ## Before pollable sends response content service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_content(self, entry):
        # first check if we have an error and we don't want to read
        if self._response_status != 200:
            return True

        # pass args to the machine, will use *args to pass them on
        # if the machine returns True, we know we can move on
        return self._state_machine.run_machine((self, entry))

    ## Called when BDSClientSocket invoke the on_finish method to wake up
    ## the ServiceSocket. Let StateMachine handle the wake up call.
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    def on_finish(self, entry):
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))
