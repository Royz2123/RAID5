#!/usr/bin/python
## @package RAID5.frontend.services.disconnect_service
## Module that defines the DisonnectService class. The service sets a disk in a
## volume to offline. Demonstrates an unresponsive Block Device Server.
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

## Frontend DisonnectService. This service removes the wanted disk from a
## specific volume.
class DisconnectService(base_service.BaseService):
    ## Disconnect States
    (
        DISCONNECT_STATE,
        FINAL_STATE,
    ) = range(2)

    ## Constructor for DisonnectService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(DisconnectService, self).__init__(
            [],
            ["disk_UUID"],
            args
        )
        ## Volume we're dealing with
        self._volume = None

        ## Disks we're dealing with
        self._disks = None

        ## Disk UUID of connected disk
        self._disk_UUID = None

        ## Volume UUID of relevant volume
        self._volume_UUID = None

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
        return "/disconnect"

    ## Before disconnecting the disk function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_disconnect(self, entry):
        self._disk_UUID = self._args["disk_UUID"][0]
        self._volume_UUID = self._args["volume_UUID"][0]

        # extract the disks from the wanted volume
        self._volume = entry.application_context["volumes"][self._volume_UUID]
        self._disks = self._volume["disks"]

        # check if disk is already disconnected
        if self._disks[self._disk_UUID]["state"] != constants.ONLINE:
            return True

        # check that all other disks are online (RAID5 requirements)
        for disk_UUID, disk in self._disks.items():
            if not disk["state"] == constants.ONLINE:
                raise RuntimeError(
                    "Can't turn disk %s offline, already have disk %s offline" %
                    (self._disk_UUID, disk_UUID))

        # already set to offline so that another attempt to disconnect shall be
        # denied
        self._disks[self._disk_UUID]["state"] = constants.OFFLINE
        self._disks[self._disk_UUID]["cache"] = cache.Cache(
            mode=cache.Cache.CACHE_MODE
        )

        # now need to increment other disks level
        # check this isn't the disk we are disconnecting
        self._disk_manager = disk_manager.DiskManager(
            self._disks,
            self._pollables,
            entry,
            service_util.create_update_level_contexts(
                self._disks,
                {
                    disk_UUID: {
                        "addition" : "1",
                        "password" : self._volume["long_password"]
                    }
                    for disk_UUID in self._disks.keys()
                    if disk_UUID != self._disk_UUID
                }
            ),
        )
        return False  # will always need input, not an epsilon_path


    ## After disconnecting the disk function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
    def after_disconnect(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Got bad status code from BDS"
            )

        # finished smoothly, update levels on frontend disks
        for disk_UUID, disk in self._disks.items():
            if disk_UUID != self._disk_UUID:
                disk["level"] += 1

        # also mark this disk as offline
        self._disks[self._disk_UUID]["state"] = constants.OFFLINE

        entry.state = constants.SEND_HEADERS_STATE
        return DisconnectService.FINAL_STATE

    ## State Machine states
    STATES = [
        state.State(
            DISCONNECT_STATE,
            [FINAL_STATE],
            before_disconnect,
            after_disconnect,
        ),
        state.State(
            FINAL_STATE,
            [FINAL_STATE]
        )
    ]

    ## Before pollable sends response status service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_status(self, entry):
        self._state_machine = state_machine.StateMachine(
            DisconnectService.STATES,
            DisconnectService.STATES[DisconnectService.DISCONNECT_STATE],
            DisconnectService.STATES[DisconnectService.FINAL_STATE]
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

    ## Before pollable sends response headers service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_headers(self, entry):
        # Re-send the management part. No refresh so user can enter new disk
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
