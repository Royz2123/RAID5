#!/usr/bin/python
## @package RAID5.common.services.get_file_service
# Module that implements the GetFileService service
#

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

## GetFileService is a HTTP Service class that sends back to the requester a
## file that has been requested
class GetFileService(base_service.BaseService):

    ## Constructor for GetFileService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param filename (string) file requested by user
    def __init__(self, entry, filename):
        super(GetFileService, self).__init__([])

        ## Filename requested
        self._filename = filename

        ## File descriptor of that filename
        self._fd = None

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/get_file"

    ## Before pollable sends response status service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_status(self, entry):
        try:
            self._fd = os.open(
                self._filename,
                os.O_RDONLY | os.O_BINARY,
                0o666
            )
            self._response_headers = {
                "Content-Length": os.fstat(self._fd).st_size,
                "Content-Type": constants.MIME_MAPPING.get(
                    os.path.splitext(
                        self._filename
                    )[1].lstrip('.'),
                    'txt/html',
                )
            }
            print os.fstat(self._fd).st_size
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            logging.error("%s :\t File not found " % entry)
            self._response_status = 404
        except Exception as e:
            logging.error("%s :\t %s " % (entry, e))
            self._response_status = 500

        return True

    ## Before pollable sends response content service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_content(
        self,
        entry,
        max_buffer=constants.BLOCK_SIZE
    ):
        # exit if not reading from file
        if self._response_status != 200:
            return True

        # read buf from file
        buf = util.read(self._fd, max_buffer)

        # if finished reading file, exit
        if len(buf) == 0:
            os.close(self._fd)
            return True

        # update read content and notify that there might be more content
        self._response_content += buf
        return False
