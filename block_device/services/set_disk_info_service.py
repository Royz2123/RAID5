# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import logging
import os
import socket
import time
import traceback

from common.services import form_service
from common.services import base_service
from common.utilities import constants


class SetDiskInfoService(
        form_service.FileFormService,
        base_service.BaseService):
    def __init__(self, entry, pollables, args):
        form_service.FileFormService.__init__(self, entry, pollables, args)
        self._save_filename = entry.application_context["disk_info_name"]
        self._tmp_filename = "%s_tmp" % self._save_filename
        self._fd = None

    @staticmethod
    def get_name():
        return "/set_disk_info"

    def file_handle(self, buf, next_state):
        while buf:
            buf = buf[os.write(self._fd, buf):]

        self._content = buf + self._content

        if next_state:
            os.rename(
                os.path.normpath(self._tmp_filename),
                os.path.normpath(self._save_filename)
            )
            os.close(self._fd)
