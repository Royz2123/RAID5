# -*- coding: utf-8 -*-
import errno
import logging
import os
import socket
import time
import traceback

from http.common.utilities import async_server
from http.common.utilities import constants
from http.common.utilities import util


class FrontServer(async_server.AsyncServer):
    def __init__(self, application_context):
        async_server.AsyncServer.__init__(self, application_context)

    def on_start(self):
        #need to check connections to BDS's, and raise error if one of them
        #is unresponsive. Also update the disks in the application_context
        if range(len(self._application_context["disks"])) < 2:
            raise RuntimeError("Not enough disks for RAID5")

        for disk_num in range(len(self._application_context["disks"])):
            disk = self._application_context[disk_num]
            with contextlib.closing(
                socket.socket(
                    family=socket.AF_INET,
                    type=socket.SOCK_STREAM,
                )
            ) as s:
                s.connect(disk["address"])

                cmd = "GET %s%s %s\r\nContent-Length: 0\r\n\r\n" % (
                    constants.DISK_INFO_NAME,
                    disk_num,
                    constants.HTTP_SIGNATURE,
                )
                util.send_all(s, cmd)
                disk_info = util.recv_all(s).split("%s%s" % (
                    constants.CRLF_BIN,
                    constants.CRLF_BIN,
                ))[1].split(constants.CRLF_BIN)

                disk["state"] = constants.ONLINE
                disk["level"] = disk_info[0]
                disk["UUID"] = disk_info[disk_num + 1]
                disk["peers"] = constants.CRLF_BIN.join(disk_info[1:])     #this includes the current disk too!

        for disk in self._application_context["disks"]:
            if disk["peers"] != self._application_context["disk"][0]["peers"]:
                raise RuntimeError("Invalid peer")
