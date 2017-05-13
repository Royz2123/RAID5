import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util

class SetBlockService(base_service.BaseService):
    BLOCK_SIZE = 4096

    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(self, [], ["blocknum"], args)
        self._content = ""
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
        return "/setblock"

    def before_content(self, entry):
        if self._fd is None:
            return True

        try:
            if not self.check_args():
                raise RuntimeError("Invalid args")

            os.lseek(
                self._fd,
                (
                    constants.BLOCK_SIZE
                    * int(self._args["blocknum"][0])
                ),
                os.SEEK_SET,
            )

            self._response_headers = {
                "Content-Length" : "0",
            }

        except Exception as e:
            logging.error("%s :\t %s " % (entry, e))
            self._response_status = 500
        return True


    def handle_content(self, entry, content):
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

    def before_terminate(self, entry):
        os.close(self._fd)
