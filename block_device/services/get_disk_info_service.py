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
from common.services import get_file_service
from common.utilities import constants

## A Block Device Service that sends the Frontend it's disk info (block -1)
# Very simple class, just sets the disk_info location and then regular
# @ref common.services.get_file_service.GetFileService
class GetDiskInfoService(
        get_file_service.GetFileService,
        base_service.BaseService):

    ## Constructor for GetDiskInfoService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(GetDiskInfoService, self).__init__(self, [])

        ## specify the disk_info file name
        self._filename = entry.application_context["disk_info_name"]

        ## set the initial file descriptor to None
        self._fd = None

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/get_disk_info"
