import errno
import logging
import os
import socket
import time
import traceback

from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util


# python-3 woodo
try:
   # try python-2 module name
   import urlparse
except ImportError:
   # try python-3 module name
   import urllib.parse
   urlparse = urllib.parse



class GetBlockService(base_service.BaseService):
    BLOCK_SIZE = 4096

    def __init__(self, args):
        base_service.BaseService.__init__(self, [], ["blocknum"], args)
        self._fd = None

    def before_response_status(self, entry):
        try:
            self._fd = entry.application_context["disk_fd"]

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
                "Content-Length" : GetBlockService.BLOCK_SIZE #min(
                    #GetBlockService.BLOCK_SIZE,
                    ##abs(
                    #    os.fstat(self._fd).st_size
                    #    - os.lseek(self._fd, 0, os.SEEK_CUR)
                    #)
                #)
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


class SetBlockService(base_service.BaseService):
    BLOCK_SIZE = 4096

    def __init__(self, args):
        base_service.BaseService.__init__(self, [], ["blocknum"], args)
        self._content = ""
        self._fd = None

    def before_content(self, entry):
        try:
            self._fd = entry.application_context["disk_fd"]

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


SERVICES = {
    "/getblock" : GetBlockService,
    "/setblock" : SetBlockService
}