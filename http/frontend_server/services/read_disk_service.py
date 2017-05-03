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
from http.frontend_server.utilities import service_util
from http.frontend_server.utilities.state_util import state
from http.frontend_server.utilities.state_util import state_machine


class ReadFromDiskService(base_service.BaseService):
    (
        READ_STATE,
        FINAL_STATE
    )=range(2)

    #read mode
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
        self._disknum = None

        self._disk_manager = None
        self._state_machine = None

    @staticmethod
    def get_name():
        return "/disk_read"

    def before_read(self, entry):
        self._current_phy_disk = disk_util.get_physical_disk_num(
            self._disks,
            self._disknum,
            self._current_block
        )
        try:
            self._block_mode = ReadFromDiskService.REGULAR
            self._disk_manager = disk_manager.DiskManager(
                self._pollables,
                entry,
                service_util.create_get_block_contexts(
                    self._disks,
                    {self._current_phy_disk : self._current_block}
                ),
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

                #create request info for all the other disks
                request_info = {}
                for disknum in range(len(self._disks)):
                    if disknum != self._current_phy_disk:
                        request_info[disknum] = self._current_block

                self._disk_manager = disk_manager.DiskManager(
                    self._pollables,
                    entry,
                    service_util.create_get_block_contexts(
                        self._disks,
                        request_info
                    ),
                )
            except socket.error as e:
                #Got another bad connection (Connection refused most likely)
                raise RuntimeError(
                    (
                        "%s:\t Couldn't connect to two of the"
                         + "BDSServers, giving up: %s"
                    ) % (
                        entry,
                        e
                    )
                )
        entry.state = constants.SLEEPING_STATE

    def after_read(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
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
        if (
            self._current_block
            == (
                int(self._args["firstblock"][0])
                + int(self._args["blocks"][0])
            )
        ):
            return ReadFromDiskService.FINAL_STATE
        return ReadFromDiskService.READ_STATE

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

            self._response_content += disk_util.compute_missing_block(blocks).ljust(
                constants.BLOCK_SIZE,
                chr(0)
            )

    STATES = [
        state.State(
            READ_STATE,
            [READ_STATE, FINAL_STATE],
            before_read,
            after_read
        ),
        state.State(
            FINAL_STATE,
            [FINAL_STATE]
        )
    ]


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
        self._disknum = int(self._args["disk"][0])
        self._current_block = int(self._args["firstblock"][0])

        #initialize state machine for reading
        first_state = ReadFromDiskService.READ_STATE
        if int(self._args["blocks"][0]) == 0:
            first_state = ReadFromDiskService.FINAL_STATE

        self._state_machine = state_machine.StateMachine(
            ReadFromDiskService.STATES,
            ReadFromDiskService.STATES[first_state],
            ReadFromDiskService.STATES[ReadFromDiskService.FINAL_STATE]
        )
        return True

    def before_response_content(self, entry):
        #pass args to the machine, will use *args to pass them on
        #if the machine returns True, we know we can move on
        return self._state_machine.run_machine((self, entry))

    def on_finish(self, entry):
        #pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))
