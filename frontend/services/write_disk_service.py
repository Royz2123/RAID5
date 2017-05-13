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

from common.services import base_service
from common.services import form_service
from common.utilities import constants
from common.utilities import util
from frontend.pollables import bds_client_socket
from frontend.utilities import disk_util
from frontend.utilities import disk_manager
from frontend.utilities import service_util


class WriteToDiskService(form_service.FileFormService, base_service.BaseService):
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    (
        READ_STATE,
        WRITE_STATE
    ) = range(2)

    def __init__(self, entry, pollables, args):
        form_service.FileFormService.__init__(self, entry, pollables, args)
        self._entry = entry
        self._pollables = pollables

        self._rest_of_data = ""
        self._finished_data = True

        self._block_mode = WriteToDiskService.REGULAR
        self._block_state = WriteToDiskService.READ_STATE

        self._block_data = ""
        self._current_block = None

        self._volume_UUID = None    #volume requested from args
        self._disk_UUID = None      #disk requested from args
        self._current_phy_UUID = None
        self._current_phy_parity_UUID = None
        self._faulty_disk_UUID = None
        self._disks = None

        self._disk_manager = None

    @staticmethod
    def get_name():
        return "/disk_write"

    #override arg and file handle from FileFormService
    def arg_handle(self, buf, next_state):
        #for this function, next_state indicates if we finished getting the arg
        self._args[self._arg_name][0] += buf

        #first check validity of volume_UUID (if finished getting)
        if next_state and self._arg_name == "volume_UUID":
            #update the volume_UUID
            self._volume_UUID = self._args["volume_UUID"][0]
            #check validity
            if (
                self._volume_UUID not in self._entry.application_context["volumes"].keys()
                or (
                    self._entry.application_context["volumes"][self._volume_UUID][
                        "volume_state"
                    ] != constants.INITIALIZED
                )
            ):
                raise RuntimeError("%s:\t Need to initialize volume" % (
                    entry,
                ))
            else:
                #if got volume_UUID well, save volume
                self._disks = self._entry.application_context["volumes"][
                    self._volume_UUID
                ]["disks"]

        #check validity of disk_UUID (if finished getting)
        if next_state and self._arg_name == "disk_UUID":
            self._disk_UUID = self._args["disk_UUID"][0]
            #check disk_UUID. already got volume_UUID and disks by order
            if self._disk_UUID not in self._disks.keys():
                self._response_status = 500
                raise RuntimeError("%s:\t Disk not part of volume" % (
                    entry,
                ))

        #check validity of firstblock requested (if finished getting)
        if next_state and self._arg_name == "firstblock":
            self._current_block = int(self._args[self._arg_name][0])
            if self._current_block < 0:
                raise RuntimeError("%s:\t Invalid first block requested: %s" % (
                    entry,
                    self._current_block
                ))


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
            self._faulty_disk_UUID = None
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

    def handle_block(self):
        self._current_phy_UUID = disk_util.get_physical_disk_UUID(
            self._disks,
            self._disk_UUID,
            self._current_block
        )
        self._current_phy_parity_UUID = disk_util.get_parity_disk_UUID(
            self._disks,
            self._current_block
        )

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
                    self._disks,
                    self._pollables,
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
            self._faulty_disk_UUID = disk_error.disk_UUID
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
                    self._disks,
                    self._pollables,
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
        return service_util.create_get_block_contexts(
            self._disks,
            {
                disk_UUID : self._current_block
                for disk_UUID in self._disks.keys()
                if disk_UUID != self._faulty_disk_UUID
            }
        )

    def contexts_for_regular_get_block(self):
        return service_util.create_get_block_contexts(
            self._disks,
            {
                self._current_phy_UUID : self._current_block,
                self._current_phy_parity_UUID : self._current_block
            }
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

        x0 = client_responses[self._current_phy_UUID]["content"]
        x1 = self._block_data
        p0 = client_responses[self._current_phy_parity_UUID]["content"]
        p1 = disk_util.compute_missing_block([x0, x1, p0])

        #then return new client contexts
        return service_util.create_set_block_contexts(
            self._disks,
            self.create_set_request_info(dict(zip(
                [self._current_phy_UUID, self._current_phy_parity_UUID],
                [x1, p1]
            )))
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
        for disk_UUID in self._disks.keys():
            if disk_UUID != self._faulty_disk_UUID:
                blocks.append(client_responses[disk_UUID]["content"])
        faulty_content = disk_util.compute_missing_block(blocks)

        #now lets set all the block content we have
        x1 = self._block_data
        if self._faulty_disk_UUID == self._current_phy_UUID:
            x0 = faulty_content
            p0 = client_responses[self._current_phy_parity_UUID]["content"]
        else:
            #must be the other way around:
            x0 = client_responses[self._current_phy_UUID]["content"]
            p0 = faulty_content
        p1 = disk_util.compute_missing_block([x0, x1, p0])

        #finally return new client contexts
        return service_util.create_set_block_contexts(
            self._disks,
            self.create_set_request_info(dict(zip(
                [self._current_phy_UUID, self._current_phy_parity_UUID],
                [x1, p1]
            )))
        )

    #SHARED FUNCTION
    def create_set_request_info(self, disk_content):
        #disk_content needs to be a dict of { disk_UUID : content }
        request_info = {}
        for disk_UUID, content in disk_content.items():
            if (
                disk_UUID == self._faulty_disk_UUID
                and self._disks[disk_UUID]["cache"].check_if_add(self._current_block)
            ):
                self._disks[disk_UUID]["cache"].add_block(
                    self._current_block,
                    content
                )
                #adding to cache means no need for communication
                #with server
            else:
                request_info[disk_UUID] = {
                    "blocknum" : self._current_block,
                    "content" : content
                }
        return request_info
