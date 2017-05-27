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


class MulService(base_service.BaseService):
    def __init__(self, entry, pollables, args):
        super(MulService, self).__init__([], ["a", "b"], args)

    @staticmethod
    def get_name():
        return "/mul"

    def before_response_status(self, entry):
        if not self.check_args():
            self._response_status = 500

        self._response_content = str(
            int(self._args['a'][0]) *
            int(self._args['b'][0])
        )
        self._response_headers = {
            "Content-Length": len(self._response_content)
        }
        logging.debug(
            "%s :\t sending content: %s"
            % (
                entry,
                self._response_content
            )
        )
