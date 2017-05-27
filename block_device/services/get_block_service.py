import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util

## A Block Device Service that allows the Frontend Server to request a block
#
class GetBlockService(base_service.BaseService):

    ## Constructor for GetBlockService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(GetBlockService, self).__init__(self, [], ["block_num"], args)
        try:
            ## File descriptor of disk file
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
        return "/getblock"

    ## What the service does before sending a response status
    # see @ref common.services.base_service.BaseService
    # function reads the block requested from the disk file
    # @param entry (pollable) the entry that the service is assigned to
    # @returns (bool) if finished and ready to move on
    def before_response_status(self, entry):
        try:
            if not self.check_args():
                raise RuntimeError("Invalid args")

            os.lseek(
                self._fd,
                (
                    GetBlockService.BLOCK_SIZE *
                    int(self._args["block_num"][0])
                ),
                os.SEEK_SET,
            )
            self._response_content = util.read(
                self._fd,
                constants.BLOCK_SIZE
            )
            self._response_headers = {
                "Content-Length": len(self._response_content)
            }

        except Exception as e:
            traceback.print_exc()
            logging.error("%s :\t %s " % (entry, e))
            self._response_status = 500

        return True

    ## What the service needs to do before terminating
    # see @ref common.services.base_service.BaseService
    # closes the disk file descriptor
    def before_terminate(self, entry):
        os.close(self._fd)
