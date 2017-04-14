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
from http.common.services import form_service
from http.common.utilities import constants
from http.common.utilities import util
from http.frontend_server.pollables import bds_client_socket
from http.frontend_server.utilities import disk_util
from http.frontend_server.utilities import disk_manager


class WriteToDiskService(form_service.FileFormService, base_service.BaseService):
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    (
        READ_STATE,
        WRITE_STATE
    ) = range(2)

    def __init__(self, entry, socket_data, args):
        form_service.FileFormService.__init__(self, entry)
        self._disks = entry.application_context["disks"]
        self._entry = entry
        self._socket_data = socket_data

        self._rest_of_data = ""
        self._finished_data = True

        self._block_mode = WriteToDiskService.REGULAR
        self._block_state = WriteToDiskService.READ_STATE

        self._block_data = ""
        self._current_block = None
        self._current_phy_disk = None
        self._current_phy_parity_disk = None

        self._disk_manager = None
        self._client_contexts = {}
        self.reset_client_contexts()

    @staticmethod
    def get_name():
        return "/disk_write"

    def reset_client_contexts(self):
        self._client_contexts = {}
        for disknum in range(len(self._disks)):
            self._client_contexts[disknum] = {
                "headers" : {},
                "method" : "GET",
                "args" : {"blocknum" : self._current_block},
                "disknum" : disknum,
                "disk_address" : self._disks[disknum]["address"],
                "service" : "/setblock",
                "content" : "",
            }


    @property
    def client_contexts(self):
        return self._client_contexts

    @client_contexts.setter
    def client_contexts(self, c_c):
        self._client_contexts = c_c

    #override arg and file handle from FileFormService
    def arg_handle(self, buf, next_state):
        #for this function, next_state indicates if we finished getting the arg

        self._args[self._arg_name][0] += buf
        if next_state and self._arg_name == "firstblock":
            self._current_block = int(self._args[self._arg_name][0])
        elif (
            next_state
            and self._arg_name == "disk"
            and (
                int(self._args[self._arg_name][0]) >= len(self._disks) - 1
                or int(self._args[self._arg_name][0]) < 0
            )
        ):
            raise RuntimeError("Invalid disk index")
            self._response_status = 500

    def file_handle(self, buf, next_state):
        if self._response_status != 200:
            return

        self._rest_of_data += buf
        self._finished_data = next_state

        if (
            len(self._rest_of_data) >= constants.BLOCK_SIZE
            or (self._finished_data and self._rest_of_data != "")
        ):
            self._block_data, self._rest_of_data = (
                self._rest_of_data[:constants.BLOCK_SIZE],
                self._rest_of_data[constants.BLOCK_SIZE:]
            )
            self._block_data = self._block_data.ljust(constants.BLOCK_SIZE, chr(0))
            self.handle_block()

    def on_finish(self, entry):
        if not self._disk_manager.check_if_finished():
            return
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Got bad status code from BDS"
            )

        if self._block_mode == WriteToDiskService.REGULAR:
            if self._block_state == WriteToDiskService.READ_STATE:
                self._block_state = WriteToDiskService.WRITE_STATE
                self.handle_block()
                return
            elif self._block_state == WriteToDiskService.WRITE_STATE:
                self._block_state = WriteToDiskService.READ_STATE
                self._current_block += 1
                if (
                    len(self._rest_of_data) >= constants.BLOCK_SIZE
                    or (self._finished_data and self._rest_of_data != "")
                ):
                    self._block_data, self._rest_of_data = (
                        self._rest_of_data[:constants.BLOCK_SIZE],
                        self._rest_of_data[constants.BLOCK_SIZE:]
                    )
                    self._block_data = self._block_data.ljust(constants.BLOCK_SIZE, chr(0))
                    self.handle_block()
                    return

        '''
        elif self._block_mode == WriteToDiskService.RECONSTRUCT:
            for client_update, disknum in (
                self._client_updates,
                range(len(self._disks))
            ):
                if (
                    disknum != self._current_phy_disk
                    and not client_update["finished"]
                ):
                    return
        '''
        #if we reached here, we are ready to continue
        if not self._finished_data:
            entry.state = constants.GET_CONTENT_STATE
        else:
            entry.state = constants.SEND_STATUS_STATE

    def before_response_status(self, entry):
        self._response_headers = {
            "Content-Length" : "0"
        }
        return True

    def handle_block(self):
        self._current_phy_disk = disk_util.DiskUtil.get_physical_disk_num(
            self._disks,
            int(self._args["disk"][0]),
            self._current_block
        )
        self._current_phy_parity_disk = disk_util.DiskUtil.get_parity_disk_num(
            self._disks,
            self._current_block
        )
        self.reset_client_contexts()

        #first try writing the block regularly
        try:
            #step 1 - get current_block and parity block contents
            #step 2 - calculate new blocks to write

            #TODO: Sort out if's
            self._block_mode = WriteToDiskService.REGULAR

            if self._block_state == WriteToDiskService.READ_STATE:
                service = "/getblock"
            else:
                service = "/setblock"

                #ALGORITHM:
                #Lets say:
                #x0 - contents of desired block before update
                #x1 - contents of desired block after update
                #p0 - contents of parity block before update
                #p1 - contents of parity block after update

                #then:
                #p1 = p0 XOR (x1 XOR x0)
                client_responses = self._disk_manager.get_responses()

                x0 = client_responses[self._current_phy_disk]["content"]
                x1 = self._block_data
                p0 = client_responses[self._current_phy_parity_disk]["content"]
                p1 = disk_util.DiskUtil.compute_missing_block([x0, x1, p0])

                self._client_contexts[self._current_phy_disk]["content"] = x1
                self._client_contexts[self._current_phy_parity_disk]["content"] = p1

            non_cached_contexts = {}
            for disk in (
                self._current_phy_disk,
                self._current_phy_parity_disk
            ):
                self._client_contexts[disk]["service"] = service
                blocknum, block_data = (
                    self._client_contexts[disk]["args"]["blocknum"],
                    self._client_contexts[disk]["content"],
                )

                if (
                    service == "/setblock"
                    and self._disks[disk]["cache"].check_if_add(
                        blocknum,
                        block_data
                    )
                ):
                    self._disks[disk]["cache"].add_block(
                        blocknum,
                        block_data
                    )
                    #adding to cache means no need for communication
                    #with server
                else:
                    non_cached_contexts[disk] = self._client_contexts[disk]

            self._disk_manager = disk_manager.DiskManager(
                self._socket_data,
                self._entry,
                non_cached_contexts
            )

        except socket.error as e:
            #connection refused of some sorts, must still try to write
            #step 1 - get all other non-parity blocks
            #step 2 - XOR and write in parity
            try:
                self._block_mode = WriteToDiskService.RECONSTRUCT
                print "shit?"

            except socket.error as e:
                #nothing to do
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
