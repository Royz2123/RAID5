import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util

## A Block Device Service that updates the level of the disk_info file
# Also known as generation id
# Created in order to simplify the handling of the disk info file, and to
# save unnecessary calls the block device services:
# @ref block_device.services.get_disk_info_service.GetDiskInfoService
# and @ref block_device.services.set_disk_info_service.SetDiskInfoService
class UpdateLevelService(base_service.BaseService):

    ## Constructor for UpdateLevelService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(UpdateLevelService, self).__init__(self, [], ["add"], args)
        try:
            # File desciptore of the disk_info file
            self._fd = os.open(
                entry.application_context["disk_info_name"],
                os.O_RDWR,
                0o666
            )
        except IOError as e:
            self._fd = None
            raise e

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/increment"

    ## What the service does before sending a response status
    # see @ref common.services.base_service.BaseService
    # function increments the level by the add arg specified
    # @param entry (pollable) the entry that the service is assigned to
    # @returns (bool) if finished and ready to move on
    def before_response_status(self, entry):
        #if not util.check_login(entry):
        #    # login was unsucsessful, notify the user agent
        #    self._response_status = 401
        #    return

        # Authorization was successful
        # read entire disk info
        disk_info = util.read(self._fd, constants.MAX_INFO_SIZE).split(
            constants.CRLF_BIN
        )
        disk_info[0] = str(
            int(disk_info[0]) +
            int(self._args["add"][0])
        )
        self._response_content = disk_info[0]
        self._response_headers = {
            "Content-Length": len(self._response_content)
        }

        # set back to beginning
        os.lseek(
            self._fd,
            0,
            os.SEEK_SET
        )

        # write new disk info with incremented level
        util.write(
            self._fd,
            constants.CRLF_BIN.join(disk_info)
        )

    ## What the service needs to do before terminating
    # see @ref common.services.base_service.BaseService
    # closes the disk file descriptor
    def before_terminate(self, entry):
        os.close(self._fd)
