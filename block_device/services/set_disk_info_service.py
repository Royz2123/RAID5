#!/usr/bin/python
## @package RAID5.block_device.services.set_disk_info_service
# Module that implements the Block Device SetDiskInfoService
#

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

## A Block Device Service that modifies it's disk info (block -1)
# Very simple class, just sets the disk_info location and then regular
# @ref common.services.form_service.FileFormService.
class SetDiskInfoService(
        form_service.FileFormService,
        base_service.BaseService):

    ## Constructor for SetDiskInfoService
    # @param entry (entry) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(SetDiskInfoService, self).__init__(entry, pollables, args)

        ## the file name of the disk info (will be the final location)
        self._save_filename = entry.application_context["disk_info_name"]

        ## temporary filename until everything goes smoothly
        self._tmp_filename = "%s_tmp" % self._save_filename

        ## file descriptor of file we're writing to
        self._fd = None

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/set_disk_info"

    ## Handles the file content
    # see @ref common.services.form_service.FileFormService for more
    # @param buf (str) content of the file
    # @param next_state (bool) specifies if the file has been sent fully
    def file_handle(self, buf, next_state):
        while buf:
            buf = buf[os.write(self._fd, buf):]

        self._content = buf + self._content

        #if finished, rename to final name
        if next_state:
            os.rename(
                os.path.normpath(self._tmp_filename),
                os.path.normpath(self._save_filename)
            )
            os.close(self._fd)
