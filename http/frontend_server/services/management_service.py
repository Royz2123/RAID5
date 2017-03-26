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


class ManagementService(base_service.BaseService):
    def __init__(self, entry):
        base_service.BaseService.__init__(self, [])

    @staticmethod
    def get_name():
        return "/management"

    def before_response_headers(self, entry):
        self._response_content = html_util.create_html_page(
            html_util.create_disks_table(entry.application_context["disks"]),
            "Disk Management"
        )

        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True
