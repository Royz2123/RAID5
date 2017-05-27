import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util


class GetBlockService(base_service.BaseService):
    BLOCK_SIZE = 4096

    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(self, [], ["block_num"], args)
        try:
            self._fd = os.open(
                entry.application_context["disk_name"],
                os.O_RDWR,
                0o666
            )
        except OSError as e:
            self._fd = None
            raise e

    @staticmethod
    def get_name():
        return "/getblock"

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

    def before_terminate(self, entry):
        os.close(self._fd)
