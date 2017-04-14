import errno
import logging
import os
import socket
import time
import traceback

from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util

class GetBlockService(base_service.BaseService):
    BLOCK_SIZE = 4096

    def __init__(self, entry, args):
        base_service.BaseService.__init__(self, [], ["blocknum"], args)
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
                    GetBlockService.BLOCK_SIZE
                    * int(self._args["blocknum"][0])
                ),
                os.SEEK_SET,
            )

            self._response_headers = {
                "Content-Length" : str(GetBlockService.BLOCK_SIZE)
            }

        except Exception as e:
            traceback.print_exc()
            logging.error("%s :\t %s " % (entry, e))
            self._response_status = 500
        return True

    def before_response_content(
        self,
        entry,
        max_buffer=constants.BLOCK_SIZE
    ):
        if self._response_status != 200:
            return True

        try:
            while len(self._response_content) < GetBlockService.BLOCK_SIZE:
                buf = os.read(
                    self._fd,
                    (
                        GetBlockService.BLOCK_SIZE
                        - len(self._response_content)
                    )
                )
                if not buf:
                    break
                self._response_content += buf

        except Exception as e:
            traceback.print_exc()
            logging.error("%s :\t %s " % (entry, e))

        self._response_content = self._response_content.ljust(
            constants.BLOCK_SIZE,
            chr(0)
        )
        return True

    def before_terminate(self, entry):
        os.close(self._fd)
