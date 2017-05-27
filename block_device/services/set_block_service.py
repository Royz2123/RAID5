#!/usr/bin/python
## @package RAID5.block_device.services.set_block_service
# Module that implements the Block Device SetBlockService
#

import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util

## A Block Device Service that allows the Frontend Server to set a block
#
class SetBlockService(base_service.BaseService):

    ## Constructor for GetBlockService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(SetBlockService, self).__init__(
            ["Authorization"],
            ["block_num"],
            args
        )

        ## Content of block recieved
        self._content = ""
        try:
            ## File descriptor os disk file
            self._fd = os.open(
                entry.application_context["disk_name"],
                os.O_RDWR,
                0o666
            )
        except OSError as e:
            self._fd = None
            raise e

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/setblock"


    ## What the service does before recieving the content
    # function prepares the file descriptor for writing in correct place
    # @param entry (pollable) the entry that the service is assigned to
    # @returns (bool) if finished and ready to move on
    def before_content(self, entry):
        if not util.check_frontend_login(entry):
            # login was unsucsessful, notify the user agent
            self._response_status = 401
            logging.debug("%s:\tIncorrect Long password (%s)" % (
                entry,
                self._response_status
            ))
            return True

        # login was successful
        if self._fd is None:
            return True

        try:
            if not self.check_args():
                raise RuntimeError("Invalid args")

            os.lseek(
                self._fd,
                (
                    constants.BLOCK_SIZE *
                    int(self._args["block_num"][0])
                ),
                os.SEEK_SET,
            )

            self._response_headers = {
                "Content-Length": "0",
            }

        except Exception as e:
            logging.error("%s :\t %s " % (entry, e))
            self._response_status = 500
        return True

    ## Handle the content that entry socket has recieved
    # write to disk file with file desciptor
    # @param entry (pollable) the entry that the service is assigned to
    # @param content (str) content recieved from the frontend
    def handle_content(self, entry, content):
        if self._response_status == 200:
            self._content += content
            try:
                while self._content:
                    self._content = self._content[
                        os.write(self._fd, self._content):
                    ]
            except Exception as e:
                logging.error("%s :\t %s " % (entry, e))
                self._response_status = 500
        return True

    ## What the service needs to do before terminating
    # closes the disk file descriptor
    def before_terminate(self, entry):
        os.close(self._fd)
