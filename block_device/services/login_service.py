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


class LoginService(base_service.BaseService):
    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(self, [], ["add"], args)
        self._password_content = ""

    @staticmethod
    def get_name():
        return "/login"

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

    def before_response_status(self, entry):
        self._response_headers = {
            "Content-Length": 0
        }
