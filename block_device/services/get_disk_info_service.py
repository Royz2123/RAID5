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
from common.services import get_file_service
from common.utilities import constants


class GetDiskInfoService(
        get_file_service.GetFileService,
        base_service.BaseService):
    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(self, [])
        self._filename = entry.application_context["disk_info_name"]
        self._fd = None

    @staticmethod
    def get_name():
        return "/get_disk_info"
