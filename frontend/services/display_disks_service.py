#!/usr/bin/python
## @package RAID5.frontend.services.display_disks_service
## Module that defines the DisplayDisksService service class.
## It displays the disks in the Frontend Server. can be
## recached by the "Manage System" button in the menu
#

import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import html_util
from common.utilities import util

## Simple Frontend HTTP service that displays the disks currently in the
## system nicely with HTML.
class DisplayDisksService(base_service.BaseService):

    ## Constructor for DisplayDisksService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(DisplayDisksService, self).__init__(["Authorization"])

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/display_disks"

    ## Before pollable sends response status service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_status(self, entry):
        if not util.check_user_login(entry):
            # login was unsucsessful, notify the user agent
            self._response_status = 401

    ## Before pollable sends response headers service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_headers(self, entry):
        if self._response_status == 200:
            self._response_content = html_util.create_html_page(
                html_util.create_disks_list(
                    entry.application_context["available_disks"],
                    entry.application_context["volumes"]
                ),
                constants.HTML_DISPLAY_HEADER,
                constants.DEFAULT_REFRESH_TIME,
            )
            self._response_headers = {
                "Content-Length": "%s" % len(self._response_content),
            }
        else:
            self._response_headers = {
                "Content-Length": 0,
                "WWW-Authenticate": "Basic realm='myRealm'",
            }
        return True
