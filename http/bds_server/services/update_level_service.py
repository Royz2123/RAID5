import errno
import logging
import os
import socket
import time
import traceback

from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util

class UpdateLevelService(base_service.BaseService):
    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(self, [], ["add"], args)
        try:
            self._fd = os.open(
                entry.application_context["disk_info_name"],
                os.O_RDWR,
                0o666
            )
        except IOError as e:
            self._fd = None
            raise e

    @staticmethod
    def get_name():
        return "/increment"

    def before_response_status(self, entry):
        #read entire disk info
        disk_info = util.read(self._fd, constants.MAX_INFO_SIZE).split(
            constants.CRLF_BIN
        )
        disk_info[0] = str(
            int(disk_info[0])
            + int(self._args["add"][0])
        )
        self._response_content = disk_info[0]
        self._response_headers = {
            "Content-Length" : len(self._response_content)
        }

        #set back to beginning
        os.lseek(
            self._fd,
            0,
            os.SEEK_SET
        )

        #write new disk info with incremented level
        util.write(
            self._fd,
            constants.CRLF_BIN.join(disk_info)
        )

    def before_terminate(self, entry):
        os.close(self._fd)
