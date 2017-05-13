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

from common.services import base_service
from common.utilities import constants
from common.utilities import html_util
from common.utilities import util

class DisplayDisksService(base_service.BaseService):
    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(self, [])

    @staticmethod
    def get_name():
        return "/display_disks"

    def before_response_headers(self, entry):
        self._response_content = html_util.create_html_page(
            html_util.create_disks_list(
                entry.application_context["available_disks"],
                entry.application_context["volumes"]
            ),
            constants.HTML_DISPLAY_HEADER,
            constants.DEFAULT_REFRESH_TIME,
        )
        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True
