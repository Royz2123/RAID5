#!/usr/bin/python
## @package RAID5.frontend.services.write_disk_service
## Module that implements the WriteToDiskService class.
#

import contextlib
import datetime
import errno
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

## Frontend HTTP service that knwos how to process a request to write to a
## logical disk and write the content to the corresponding physical disks.
## This service also know how handle when the wanted disk is disconnected, and
## can still access it's content based on the RAID5 protocol.
## Inherits from the FileFormService class since we are getting the file as a
## multipart form, and therefore writing to disk is a type of FileFormService.
## Weshall override the file_handle and arg_handle functions that are in the
## FileFormService so we can handle them like we want.
## Integrated StateMachine was too comlpex to insert to this class and I Found
## it simpler to build a custom state machine.
## For each writing operation, he parity needs to be updated too. If one of
## these is offline, we shall update the cache we have for each disk.
## Most complex class in the project, requires many operations.
class WriteToDiskService(
        form_service.FileFormService,
        base_service.BaseService):
    ## Writing States
    (
        READ_STATE,
        WRITE_STATE
    ) = range(2)

    ## Reading Modes
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    ## Constructor for WriteToDiskService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(WriteToDiskService, self).__init__(entry, pollables, args)
        # update Authorization
        self._wanted_headers.append("Authorization")

        ## Entry we belong to. Need to save because we won't always have the
        ## entry
        self._entry = entry

        ## pollables of the Frontend server
        self._pollables = pollables

        ## Rest of data
        self._rest_of_data = ""

        ## Finished writing data
        self._finished_data = True

        ## Mode in which we will write
        self._block_mode = WriteToDiskService.REGULAR

        ## Current writing state
        self._block_state = WriteToDiskService.READ_STATE

        ## Current block data
        self._block_data = ""

        ## Current block num
        self._current_block = None

        ## UUID of volume we're dealing with
        self._volume_UUID = None

        ## Logical disk num of disk we're writing to
        self._disk_num = None

        ## UUID of the physical disk we're writing to
        self._current_phy_UUID = None

        ## UUID of the physical parity disk we're writing to
        self._current_phy_parity_UUID = None

        ## UUID of faulty disk we tried writing to
        self._faulty_disk_UUID = None

        ## Volume we're dealing with
        self._volume = None

        ## Disks we're dealing with
        self._disks = None

        ## Disk Manager that manages all the clients
        self._disk_manager = None

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/disk_write"

    ## Before pollable recieves content service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_content(self, entry):
        # first check login
        if not util.check_user_login(entry):
            # login was unsucsessful, notify the user agent
            self._response_status = 401
            self._response_headers["WWW-Authenticate"] = "Basic realm='myRealm'"
            return True

        # otherwise continue regularly
        form_service.FileFormService.before_content(self, entry)

    ## Override arg handle from FileFormService, and check args. Check that
    ## disk and volume are OK to write to
    ## @param buf (string) buf read from socket
    ## @param next_state (int) if finished reading argument
    def arg_handle(self, buf, next_state):
        # for this function, next_state indicates if we finished getting the
        # arg
        self._args[self._arg_name][0] += buf

        # first check validity of volume_UUID (if finished getting)
        if next_state and self._arg_name == "volume_UUID":
            # update the volume_UUID
            self._volume_UUID = self._args["volume_UUID"][0]
            # check validity
            if (
                self._volume_UUID not in self._entry.application_context["volumes"].keys(
                ) or
                (
                    self._entry.application_context["volumes"][self._volume_UUID][
                        "volume_state"
                    ] != constants.INITIALIZED
                )
            ):
                raise RuntimeError("%s:\t Need to initialize volume" % (
                    entry,
                ))

            # if got volume_UUID well, save volume
            self._volume = self._entry.application_context["volumes"][
                self._volume_UUID
            ]
            self._disks = self._volume["disks"]

        # check validity of disk_UUID (if finished getting)
        if next_state and self._arg_name == "disk_num":
            self._disk_num = int(self._args["disk_num"][0])
            # check disk_UUID. already got volume_UUID and disks by order
            if self._disk_num < 0 or self._disk_num >= (len(self._disks)-1):
                self._response_status = 500
                raise RuntimeError("%s:\t Disk not part of volume %s" % (
                    entry,
                    self._disk_num
                ))

        # check validity of firstblock requested (if finished getting)
        if next_state and self._arg_name == "firstblock":
            self._current_block = int(self._args[self._arg_name][0])
            if self._current_block < 0:
                raise RuntimeError(
                    "%s:\t Invalid first block requested: %s" %
                    (entry, self._current_block))

    ## Override file handle from FileFormService. This is where we split the
    ## file content into blocks and send them to the relevant disks.
    ## @param buf (string) buf read from socket
    ## @param next_state (int) if finished reading file
    def file_handle(self, buf, next_state):
        if self._response_status != 200:
            return

        self._rest_of_data += buf
        self._finished_data = next_state

        if (
            len(self._rest_of_data) >= constants.BLOCK_SIZE or
            (self._finished_data and self._rest_of_data != "")
        ):
            self._block_data, self._rest_of_data = (
                self._rest_of_data[:constants.BLOCK_SIZE],
                self._rest_of_data[constants.BLOCK_SIZE:]
            )
            self._block_data = self._block_data.ljust(
                constants.BLOCK_SIZE, chr(0))
            self.handle_block()

    ## Called when BDSClientSocket invoke the on_finish method to wake up
    ## the ServiceSocket. Read/Write (move on to next state)
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
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
            # prepare for next block, start regularly:
            self._block_mode = WriteToDiskService.REGULAR
            self._faulty_disk_UUID = None
            self._block_state = WriteToDiskService.READ_STATE
            self._current_block += 1
            if (
                len(self._rest_of_data) >= constants.BLOCK_SIZE or
                (self._finished_data and self._rest_of_data != "")
            ):
                self._block_data, self._rest_of_data = (
                    self._rest_of_data[:constants.BLOCK_SIZE],
                    self._rest_of_data[constants.BLOCK_SIZE:]
                )
                self._block_data = self._block_data.ljust(
                    constants.BLOCK_SIZE, chr(0))
                self.handle_block()
                return

        # if we reached here, we are ready to continue
        if not self._finished_data:
            entry.state = constants.GET_CONTENT_STATE
        else:
            entry.state = constants.SEND_STATUS_STATE

    ## Hanlde a block that has been read from the file.
    ## First try to write normally. If problem arises, move on to RECONSTRUCT
    ## mode
    def handle_block(self):
        self._current_phy_UUID = disk_util.get_physical_disk_UUID(
            self._disks,
            self._disk_num,
            self._current_block
        )
        self._current_phy_parity_UUID = disk_util.get_parity_disk_UUID(
            self._disks,
            self._current_block
        )

        # first try writing the block regularly
        try:
            # First check availablity
            available_disks = entry.application_context["available_disks"]
            online, offline = util.sort_disks(available_disks)
            if self._current_phy_UUID not in online.keys():
                raise util.DiskRefused(self._current_phy_UUID)

            # step 1 - get current_block and parity block contents
            # step 2 - calculate new blocks to write
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
            # start reading from the beginning again:
            self._block_state = WriteToDiskService.READ_STATE

        # if didn't work, try with reconstruct
        try:
            # step 1 - get all other non-parity blocks
            # step 2 - XOR and write in parity
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
            # nothing to do
            logging.error(
                (
                    "%s:\t Couldn't connect to two of the" +
                    "BDSServers, giving up: %s"
                ) % (
                    self._entry,
                    disk_error
                )
            )

    # Getting the blocks we want from block devices:
    # GET BLOCKS, REGULAR AND RECONSTRUCT

    ## Get contexts_for_reconstruct_get_block
    ## @returns contexts (dict) for BDSClientSocket
    def contexts_for_reconstruct_get_block(self):
        return service_util.create_get_block_contexts(
            self._disks,
            {
                disk_UUID: {
                    "block_num" : self._current_block,
                    "password" : self._volume["long_password"],
                }
                for disk_UUID in self._disks.keys()
                if disk_UUID != self._faulty_disk_UUID
            }
        )

    ## Get contexts_for_regular_get_block
    ## @returns contexts (dict) for BDSClientSocket
    def contexts_for_regular_get_block(self):
        context = {
            "block_num" : self._current_block,
            "password" : self._volume["long_password"]
        }
        return service_util.create_get_block_contexts(
            self._disks,
            {
                self._current_phy_UUID: context,
                self._current_phy_parity_UUID: context
            }
        )

    # SET BLOCKS, REGULAR AND RECONSTRUCT

    ## Get contexts_for_regular_set_block. We need to find the exact data to
    ## write.
    ##
    ## ALGORITHM:
    ## Lets say:
    ## x0 - contents of desired block before update
    ## x1 - contents of desired block after update
    ## p0 - contents of parity block before update
    ## p1 - contents of parity block after update
    ##
    ## then:
    ## p1 = p0 XOR (x1 XOR x0)
    ## @returns contexts (dict) for BDSClientSocket
    def contexts_for_regular_set_block(self):
        # first update content
        client_responses = self._disk_manager.get_responses()

        x0 = client_responses[self._current_phy_UUID]["content"]
        x1 = self._block_data
        p0 = client_responses[self._current_phy_parity_UUID]["content"]
        p1 = disk_util.compute_missing_block([x0, x1, p0])

        # then return new client contexts
        return service_util.create_set_block_contexts(
            self._disks,
            self.create_set_request_info(dict(zip(
                [self._current_phy_UUID, self._current_phy_parity_UUID],
                [x1, p1]
            )))
        )

    ## Get contexts_for_reconstruct_set_block. We need to find the exact data
    ## to write if one of the important disks is down.
    ##
    ## ALGORITHM:
    ## Lets say:
    ## x0 - contents of desired block before update
    ## x1 - contents of desired block after update
    ## p0 - contents of parity block before update
    ## p1 - contents of parity block after update

    ## then:
    ## p1 = p0 XOR (x1 XOR x0)

    ## but:
    ## either x or p is down, or in other words, we cannot access x0 or p0
    ## In any case, we can represent x0 or p0 as XOR of the rest and continue
    ## regularly:

    ## Lets say:
    ## a0, b0, c0 ... z0 are the contents of all the disks before update

    ## if p is down:
    ## p1 = a0 XOR b0 ... XOR x0 XOR .. XOR z0 XOR (x1 XOR x0)
    ##   = a0 XOR b0 ... XOR z0 XOR (x1)         --> (x0 XOR x0 = "0")
    ## ---> Definition of p1!

    ## if x is down:
    ## p1 = p0 XOR (x1 XOR (a0 XOR b0 ... XOR z0))
    ##   = x1 XOR (a0 XOR b0 XOR ... XOR z0)         --> (p0 XOR p0 = "0")
    ## ---> Definition of p1!
    ## @returns contexts (dict) for BDSClientSocket
    def contexts_for_reconstruct_set_block(self):
        # first update content
        client_responses = self._disk_manager.get_responses()

        # first lets find the faulty disks content:
        blocks = []
        for disk_UUID in self._disks.keys():
            if disk_UUID != self._faulty_disk_UUID:
                blocks.append(client_responses[disk_UUID]["content"])
        faulty_content = disk_util.compute_missing_block(blocks)

        # now lets set all the block content we have
        x1 = self._block_data
        if self._faulty_disk_UUID == self._current_phy_UUID:
            x0 = faulty_content
            p0 = client_responses[self._current_phy_parity_UUID]["content"]
        else:
            # must be the other way around:
            x0 = client_responses[self._current_phy_UUID]["content"]
            p0 = faulty_content
        p1 = disk_util.compute_missing_block([x0, x1, p0])

        # finally return new client contexts
        return service_util.create_set_block_contexts(
            self._disks,
            self.create_set_request_info(dict(zip(
                [self._current_phy_UUID, self._current_phy_parity_UUID],
                [x1, p1]
            )))
        )

    # SHARED FUNCTION

    ## create the request_info for the wanted contexts.
    ## @returns request_info (dict) for BDSClientSocket
    def create_set_request_info(self, disk_content):
        # disk_content needs to be a dict of { disk_UUID : content }
        request_info = {}
        for disk_UUID, content in disk_content.items():
            if (
                disk_UUID == self._faulty_disk_UUID and
                self._disks[disk_UUID]["cache"].check_if_add(self._current_block)
            ):
                self._disks[disk_UUID]["cache"].add_block(
                    self._current_block,
                    content
                )
                # adding to cache means no need for communication
                # with server
            else:
                request_info[disk_UUID] = {
                    "block_num": self._current_block,
                    "password": self._volume["long_password"],
                    "content": content
                }
        return request_info
