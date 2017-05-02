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

class DisconnectService(base_service.BaseService):
    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(
            self,
            [],
            ["disknum"],
            args
        )
        self._disks = entry.application_context["disks"]
        self._disknum = None

        self._pollables = pollables

        self._client_contexts = {}
        self._disk_manager = None

    @staticmethod
    def get_name():
        return "/disconnect"

    def reset_client_contexts(self):
        self._client_contexts = {}
        for disknum in range(len(self._disks)):
            self._client_contexts[disknum] = {
                "headers" : {},
                "args" : {"add" : "1"},
                "disknum" : disknum,
                "disk_address" : self._disks[disknum]["address"],
                "method" : "GET",
                "service" : (
                    update_level_service.UpdateLevelService.get_name()
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

    def handle_disconnect(self, entry):
        self._disknum = int(self._args["disknum"][0])
        if self._disks[self._disknum]["state"] != constants.ONLINE:  #check if already disconnected
            return

        #check that all other disks are online (RAID5 requirements)
        for disknum in range(len(self._disks)):
            if not self._disks[disknum]["state"] == constants.ONLINE:
                raise RuntimeError(
                    "Can't turn disk %s offline, already have disk %s offline" % (
                        self._disknum,
                        disknum
                    )
                )

        #already set to offline so that another attempt to disconnect shall be denied
        self._disks[self._disknum]["state"] = constants.OFFLINE
        self._disks[self._disknum]["cache"] = cache.Cache(
            mode=cache.Cache.CACHE_MODE
        )

        #now need to increment other disks level
        #check this isn't the disk we are disconnecting
        self.reset_client_contexts()
        self._disk_manager = disk_manager.DiskManager(
            self._pollables,
            entry,
            {
                k : v for k, v in (
                    self._client_contexts.items()
                ) if k != self._disknum
            },
        )

    def before_response_status(self, entry):
        self.handle_disconnect(entry)

    def before_response_headers(self, entry):
        #Re-send the management part. No refresh so user can enter new disk
        self._response_content = html_util.create_html_page(
            html_util.create_disks_table(entry.application_context["disks"]),
            constants.HTML_MANAGEMENT_HEADER,
        )

        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True
