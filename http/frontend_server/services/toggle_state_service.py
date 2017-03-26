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

from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import html_util
from http.common.utilities import util

class ToggleStateService(base_service.BaseService):
    def __init__(self, entry, args):
        base_service.BaseService.__init__(
            self,
            [],
            ["disknum"],
            args
        )
        self._disks = entry.application_context["disks"]


    @staticmethod
    def get_name():
        return "/togglestate"

    def handle_toggle(self):
        toggle_disk = int(self._args["disknum"][0])
        self._disks[toggle_disk]["state"] = not self._disks[toggle_disk]["state"]

        if self._disks[toggle_disk]["state"]:
            #update all the other disks level
            pass
        else:
            #need to check the level in comparison to other disks
            pass


    def before_response_status(self, entry):
        self.handle_toggle()

        #Re-send the management part
        self._response_content = html_util.create_html_page(
            html_util.create_disks_table(entry.application_context["disks"]),
            "Disk Management"
        )

        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True
