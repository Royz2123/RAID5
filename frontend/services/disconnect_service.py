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


class DisconnectService(base_service.BaseService):
    (
        DISCONNECT_STATE,
        FINAL_STATE,
    ) = range(2)

    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(
            self,
            [],
            ["disk_UUID"],
            args
        )
        self._disk_UUID = None
        self._volume_UUID = None
        self._disks = None

        self._pollables = pollables

        self._disk_manager = None
        self._state_machine = None

    @staticmethod
    def get_name():
        return "/disconnect"

    def before_disconnect(self, entry):
        self._disk_UUID = self._args["disk_UUID"][0]
        self._volume_UUID = self._args["volume_UUID"][0]

        # extract the disks from the wanted volume
        self._disks = entry.application_context[
            "volumes"
        ][self._volume_UUID]["disks"]

        # check if disk is already disconnected
        if self._disks[self._disk_UUID]["state"] != constants.ONLINE:
            return

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
                    disk_UUID: "1" for disk_UUID in self._disks.keys()
                    if disk_UUID != self._disk_UUID
                }
            ),
        )
        return False  # will always need input, not an epsilon_path

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

    def before_response_status(self, entry):
        self._state_machine = state_machine.StateMachine(
            DisconnectService.STATES,
            DisconnectService.STATES[DisconnectService.DISCONNECT_STATE],
            DisconnectService.STATES[DisconnectService.FINAL_STATE]
        )
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    def on_finish(self, entry):
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

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
