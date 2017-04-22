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
        form_service.FileFormService.__init__(self, entry, socket_data, args)
        self._disks = entry.application_context["disks"]
        self._entry = entry
        self._socket_data = socket_data

        self._rest_of_data = ""
        self._finished_data = True

        self._block_mode = WriteToDiskService.REGULAR
        self._block_state = WriteToDiskService.READ_STATE
        self._faulty_disknum = None

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

        if len(self._disks)==0:
            raise RuntimeError("%s:\t Need to initialize system" % (
                self._entry,
            ))
        elif next_state and self._arg_name == "firstblock":
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

        if self._block_state == WriteToDiskService.READ_STATE:
            self._block_state = WriteToDiskService.WRITE_STATE
            self.handle_block()
            return
        elif self._block_state == WriteToDiskService.WRITE_STATE:
            #prepare for next block, start regularly:
            self._block_mode = WriteToDiskService.REGULAR

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
            if self._block_mode == WriteToDiskService.REGULAR:
                if self._block_state == WriteToDiskService.READ_STATE:
                    contexts = self.contexts_for_regular_get_block()
                else:
                    contexts = self.contexts_for_regular_set_block()

                self._disk_manager = disk_manager.DiskManager(
                    self._socket_data,
                    self._entry,
                    contexts
                )

        except util.DiskRefused as disk_error:
            logging.error(
                (
                    "%s:\t Got: %s, trying to connect with RECONSTRUCT"
                ) % (
                    self._entry,
                    disk_error
                )
            )
            self._faulty_disknum = disk_error.disknum
            self._block_mode = WriteToDiskService.RECONSTRUCT
            #start reading from the beginning again:
            self._block_state = WriteToDiskService.READ_STATE

        #if didn't work, try with reconstruct
        try:
            #step 1 - get all other non-parity blocks
            #step 2 - XOR and write in parity
            if self._block_mode == WriteToDiskService.RECONSTRUCT:
                if self._block_state == WriteToDiskService.READ_STATE:
                    contexts = self.contexts_for_reconstruct_get_block()
                else:
                    contexts = self.contexts_for_reconstruct_set_block()

                self._disk_manager = disk_manager.DiskManager(
                    self._socket_data,
                    self._entry,
                    contexts
                )

        except util.DiskRefused as disk_error:
            #nothing to do
            logging.error(
                (
                    "%s:\t Couldn't connect to two of the"
                     + "BDSServers, giving up: %s"
                ) % (
                    self._entry,
                    disk_error
                )
            )

    #Getting the blocks we want from block devices:

    #GET BLOCKS, REGULAR AND RECONSTRUCT
    def contexts_for_reconstruct_get_block(self):
        return self.contexts_for_get_block(
            [
                disk for disk in range(len(self._disks))
                if disk != self._faulty_disknum
            ]
        )

    def contexts_for_regular_get_block(self):
        return self.contexts_for_get_block(
            [
                self._current_phy_disk,
                self._current_phy_parity_disk
            ]
        )


    #SET BLOCKS, REGULAR AND RECONSTRUCT
    def contexts_for_regular_set_block(self):
        #first update content

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

        #then return new client contexts
        return self.contexts_for_set_block(
            [
                self._current_phy_disk,
                self._current_phy_parity_disk
            ]
        )

    def contexts_for_reconstruct_set_block(self):
        #first update content

        #ALGORITHM:
        #Lets say:
        #x0 - contents of desired block before update
        #x1 - contents of desired block after update
        #p0 - contents of parity block before update
        #p1 - contents of parity block after update

        #then:
        #p1 = p0 XOR (x1 XOR x0)

        #but:
        #either x or p is down, or in other words, we cannot access x0 or p0
        #In any case, we can represent x0 or p0 as XOR of the rest and continue
        #regularly:

        #Lets say:
        #a0, b0, c0 ... z0 are the contents of all the disks before update

        #if p is down:
        #p1 = a0 XOR b0 ... XOR x0 XOR .. XOR z0 XOR (x1 XOR x0)
        #   = a0 XOR b0 ... XOR z0 XOR (x1)         --> (x0 XOR x0 = "0")
        # ---> Definition of p1!

        #if x is down:
        #p1 = p0 XOR (x1 XOR (a0 XOR b0 ... XOR z0))
        #   = x1 XOR (a0 XOR b0 XOR ... XOR z0)         --> (p0 XOR p0 = "0")
        # ---> Definition of p1!

        client_responses = self._disk_manager.get_responses()

        #first lets find the faulty disks content:
        blocks = []
        for disknum in range(len(self._disks)):
            if disknum != self._faulty_disknum:
                blocks.append(client_responses[disknum]["content"])
        faulty_content = disk_util.DiskUtil.compute_missing_block(blocks)

        #now lets set all the block content we have
        x1 = self._block_data
        if self._faulty_disknum == self._current_phy_disk:
            x0 = faulty_content
            p0 = client_responses[self._current_phy_parity_disk]["content"]
        else:
            #must be the other way around:
            x0 = client_responses[self._current_phy_disk]["content"]
            p0 = faulty_content
        p1 = disk_util.DiskUtil.compute_missing_block([x0, x1, p0])

        self._client_contexts[self._current_phy_disk]["content"] = x1
        self._client_contexts[self._current_phy_parity_disk]["content"] = p1

        #finally return new client contexts
        return self.contexts_for_set_block(
            [
                self._current_phy_disk,
                self._current_phy_parity_disk
            ]
        )

    #SHARED FUNCTIONS
    def contexts_for_get_block(self, disknums):
        contexts = {}
        for disk in disknums:
            self._client_contexts[disk]["service"] = "/getblock"
            contexts[disk] = self._client_contexts[disk]
        return contexts

    def contexts_for_set_block(self, disknums):
        contexts = {}
        for disk in disknums:
            self._client_contexts[disk]["service"] = "/setblock"
            blocknum, block_data = (
                self._client_contexts[disk]["args"]["blocknum"],
                self._client_contexts[disk]["content"],
            )
            #check if cache needs to update, if disk is offline
            if self._disks[disk]["cache"].check_if_add(blocknum):
                self._disks[disk]["cache"].add_block(
                    blocknum,
                    block_data
                )
                #adding to cache means no need for communication
                #with server
            else:
                contexts[disk] = self._client_contexts[disk]
        return contexts
