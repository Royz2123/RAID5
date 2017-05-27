#!/usr/bin/python
## @package RAID5.block_device.services.login_service
# Module that implements the Block Device LoginService
#

import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import config_util
from common.utilities import constants
from common.utilities import util

## A Block Device Service that allows the Frontend to supply it with a
## long_password for later communication
class LoginService(base_service.BaseService):

    ## Constructor for LoginService
    # @param entry (entry) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(LoginService, self).__init__([], ["add"], args)

        ## the password recieved from the frontend
        self._password_content = ""

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/login"


    ## Handle the content that entry socket has recieved
    # extract the password and volume_UUID from frontend request
    # @param entry (pollable) the entry that the service is assigned to
    # @param content (str) content recieved from the frontend
    def handle_content(self, entry, content):
        self._password_content += content

        # parser all the content
        parsed_content = self._password_content.split(constants.CRLF_BIN)

        # check if finished getting data
        if "" not in parsed_content:
            return

        # Got entire password and volume UUID. update in dynamic config_file:
        password = parsed_content[1]
        volume_UUID = parsed_content[0]

        # update the config file
        config_file = entry.application_context["config_file"]

        config_util.write_field_config(
            entry.application_context["config_file"],
            "Authentication",
            "long_password",
            password,
        )
        config_util.write_field_config(
            entry.application_context["config_file"],
            "Server",
            "volume_UUID",
            volume_UUID,
        )
        # update the Authentication field
        entry.application_context["authentication"]["long_password"] = (
            password
        )
        entry.application_context["server_info"]["volume_UUID"] = (
            volume_UUID
        )

    ## What the service does before sending a response status
    # function reads the block requested from the disk file
    # @param entry (pollable) the entry that the service is assigned to
    # @returns (bool) if finished and ready to move on
    def before_response_status(self, entry):
        self._response_headers = {
            "Content-Length": 0
        }
        return True
