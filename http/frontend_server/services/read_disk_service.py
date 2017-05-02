# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import time
import traceback

from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util
from http.frontend_server.pollables import bds_client_socket
from http.frontend_server.utilities import disk_manager
from http.frontend_server.utilities import disk_util

class ReadFromDiskService(base_service.BaseService):
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(
            self,
            ["Content-Type"],
            ["disk", "firstblock", "blocks"],
            args
        )
        self._disks = entry.application_context["disks"]
        self._pollables = pollables

        self._block_mode = ReadFromDiskService.REGULAR
        self._current_block = None
        self._current_phy_disk = None

        self._client_contexts = {}
        self._disk_manager = None
        self.reset_client_contexts()

    @staticmethod
    def get_name():
        return "/disk_read"

    def reset_client_contexts(self):
        self._client_contexts = {}
        for disknum in range(len(self._disks)):
            self._client_contexts[disknum] = {
                "headers" : {},
                "method" : "GET",
                "args" : {"blocknum" : self._current_block},
                "disknum" : disknum,
                "disk_address" : self._disks[disknum]["address"],
                "service" : "/getblock",
                "content" : ""
            }

    @property
    def client_contexts(self):
        return self._client_contexts

    @client_contexts.setter
    def client_contexts(self, c_c):
        self._client_contexts = c_c

    def on_finish(self, entry):
        if not self._disk_manager.check_if_finished():
            return
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Got bad status code from BDS"
            )

        #if we have a pending block, send it back to client
        #Get ready for next block (if there is)
        #TODO: Too much in response_content
        self.update_block()
        self._current_block += 1
        entry.state = constants.SEND_CONTENT_STATE

    def before_response_status(self, entry):
        if len(self._disks)==0:
            raise RuntimeError("%s:\t Need to initialize system" % (
                entry,
            ))
        elif int(self._args["blocks"][0]) < 0:
            raise RuntimeError("%s:\t Invalid amount of blocks: %s" % (
                entry,
                self._args["blocks"][0]
            ))
        elif (
            int(self._args["disk"][0]) < 0
            or int(self._args["disk"][0]) >= (len(self._disks) - 1)
        ):
            raise RuntimeError("%s:\t Invalid disk requested: %s" % (
                entry,
                self._args["disk"][0]
            ))
        elif int(self._args["firstblock"][0]) < 0:
            raise RuntimeError("%s:\t Invalid first block requested: %s" % (
                entry,
                self._args["firstblock"][0]
            ))


        #could check on how many are active...
        self._response_headers = {
            "Content-Length" : (
                int(self._args["blocks"][0])
                * constants.BLOCK_SIZE
            ),
            "Content-Type" : "text/html",
            "Content-Disposition" : (
                "attachment; filename=blocks[%s : %s].txt"
                % (
                    int(self._args["firstblock"][0]),
                    (
                        int(self._args["blocks"][0])
                        + int(self._args["firstblock"][0])
                    )
                )
            ),
        }

        self._current_block = int(self._args["firstblock"][0])
        return True

    def before_response_content(self, entry):
        #we shouldnt get here, but for now
        if entry.state == constants.SLEEPING_STATE:
            return False

        #check if there are no more blocks to send
        if (
            self._current_block
            == (
                int(self._args["firstblock"][0])
                + int(self._args["blocks"][0])
            )
        ):
            return True

        self._current_phy_disk = disk_util.DiskUtil.get_physical_disk_num(
            self._disks,
            int(self._args["disk"][0]),
            self._current_block
        )
        self.reset_client_contexts()

        try:
            self._block_mode = ReadFromDiskService.REGULAR
            self._disk_manager = disk_manager.DiskManager(
                self._pollables,
                entry,
                {
                    self._current_phy_disk : self._client_contexts[
                        self._current_phy_disk
                    ]
                },
            )
        except util.DiskRefused as e:
            #probably got an error when trying to reach a certain BDS
            #ServerSocket. We shall try to get the data from the rest of
            #the disks. Otherwise, two disks are down and theres nothing
            #we can do
            logging.debug(
                "%s:\t Couldn't connect to one of the BDSServers, %s: %s" % (
                    entry,
                    self._current_phy_disk,
                    e
                )
            )
            try:
                self._block_mode = ReadFromDiskService.RECONSTRUCT
                self._disk_manager = disk_manager.DiskManager(
                    self._pollables,
                    entry,
                    {
                        k : v for k, v in (
                            self._client_contexts.items()
                        ) if k != self._current_phy_disk
                    },
                )
            except socket.error as e:
                #Got another bad connection (Connection refused most likely)
                logging.error(
                    (
                        "%s:\t Couldn't connect to two of the"
                         + "BDSServers, giving up: %s"
                    ) % (
                        entry,
                        e
                    )
                )
                return True
        return False

    #woke up from sleeping mode, checking if got required blocks
    def update_block(self):
        client_responses = self._disk_manager.get_responses()
        #regular block update
        if self._block_mode == ReadFromDiskService.REGULAR:
            self._response_content += (
                client_responses[self._current_phy_disk]["content"].ljust(
                    constants.BLOCK_SIZE,
                    chr(0)
                )
            )

        #reconstruct block update
        elif self._block_mode == ReadFromDiskService.RECONSTRUCT:
            blocks = []
            for disknum, response in client_responses.items():
                blocks.append(response["content"])

            self._response_content += disk_util.DiskUtil.compute_missing_block(blocks).ljust(
                constants.BLOCK_SIZE,
                chr(0)
            )
