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


class TimeService(base_service.BaseService):
    def __init__(self, entry, pollables):
        super(TimeService, self).__init__([])

    @staticmethod
    def get_name():
        return "/clock"

    def before_response_headers(self, entry):
        self._response_headers = {
            "Content-Length": len(str(datetime.datetime.now())),
        }
        self._response_content = str(datetime.datetime.now())
        logging.debug(
            "%s :\t sending content: %s"
            % (
                entry,
                self._response_content
            )
        )
        return True
