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
import uuid

from http.common.services import base_service
from http.common.services import form_service
from http.common.utilities import constants
from http.common.utilities import html_util
from http.common.utilities import post_util
from http.common.utilities import util
from http.frontend_server.services import display_disks_service
from http.frontend_server.utilities import disk_manager
from http.frontend_server.utilities import cache
from http.frontend_server.utilities import disk_util
from http.frontend_server.utilities import service_util
from http.common.utilities.state_util import state
from http.common.utilities.state_util import state_machine

class InitService(base_service.BaseService):
    (
        SETUP_STATE,
        EXISTING_MOUNT_STATE,
        SCRATCH_MOUNT_STATE,
        FINAL_STATE,
    )=range(4)

    def __init__(self, entry, pollables, args):
        base_service.BaseService.__init__(self)
        self._args = args     #args will be checked independently
        self._pollables = pollables

        entry.application_context["disks"] = []
        self._disks = entry.application_context["disks"]

        self._mode = None

        self._disk_manager = None
        self._state_machine = None

    @staticmethod
    def get_name():
        return "/init"

    #STATE FUNCTIONS

    def before_setup(self, entry):
        #first check addresses and init disks
        for arg_name, arg_info in self._args.items():
            if "scratch" == arg_name:
                pass
            elif not util.make_address(arg_info[0]):
                raise RuntimeError("Args must be addresses: (address, port)")
            else:
                self._disks.append({
                    "address" : util.make_address(arg_info[0]),
                    "disk_UUID" : "",
                    "common_UUID" : "",
                    "level" : "",
                    "state" : constants.STARTUP,
                    "cache" : cache.Cache(),
                })

        if len(self._disks) < 2:
            raise RuntimeError(
                "%s:\tNot enough disks for RAID5: %s"
                % (
                    entry,
                    len(self._disks)
                )
            )

        if "scratch" in self._args.keys():
            return True    #this is an epsilon_path, no need to classify system

        #create client with the first address in order to classify mode
        #Now that disks have been established we can proceed
        self._disk_manager = disk_manager.DiskManager(
            self._pollables,
            entry,
            service_util.create_get_disk_info_contexts(
                self._disks,
                [0]
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False    #will always need input, not an epsilon_path

    def after_setup(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        elif self._disk_manager.check_common_status_code("200"):
            logging.debug("SYSTEM INITIALIZING FROM EXISTING MODE")
            return InitService.EXISTING_MOUNT_STATE
        elif self._disk_manager.check_common_status_code("404"):
            logging.debug("SYSTEM INITIALIZING FROM SCRATCH MODE")
            return InitService.SCRATCH_MOUNT_STATE
        else:
            raise RuntimeError(
                "Block Device Server sent a bad status code: %s"
                % (
                    self._disk_manager.get_responses()[0]["status"]
                )
            )

    def before_existing_mount(self, entry):
        self._disk_manager = disk_manager.DiskManager(
            self._pollables,
            entry,
            service_util.create_get_disk_info_contexts(
                self._disks,
                range(len(self._disks))
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False    #will always need input, not an epsilon_path

    def after_existing_mount(self, entry):
        #check if got a response from ALL of the
        #block devices:
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code: %s"
                % (
                    client_responses[0]["status"]
                )
            )
        #check the actual response topology
        client_responses = self._disk_manager.get_responses()

        #make the disks_data easily accessible
        disks_data = []
        for disk_num in range(len(self._disks)):
            disks_data.append(
                client_responses[disk_num]["content"].split(
                    constants.CRLF_BIN
                )
            )

        #check if a disk need to be rebuilt
        rebuild_disk = None
        for disk_num in range(len(self._disks)):
            #first lets check the common_uuid:
            if disks_data[disk_num][1] != disks_data[0][1]:
                raise RuntimeError(
                    "Got two different topoligies: \n%s\n%s" % (
                        disks_data[disk_num][1],
                        disks_data[0][1]
                    )
                )

            #next lets check the generation level
            #By RAID5, we can only rebuild one disk at a time
            if disks_data[disk_num][0] != disks_data[0][0]:
                if rebuild_disk is not None:
                    raise RuntimeError(
                        "Already rebuilding disk: %s, can't rebuild 2: %s" % (
                            disks_data[disk_num][0],
                            disks_data[0][0]
                        )
                    )
                else:
                    rebuild_disk = disk_num

            #Lets now check the disk UUID:
            if disks_data[disk_num][3:].count(disks_data[disk_num][2]) != 1:
                raise RuntimeError(
                    "Disk UUID shows up an invalid amount"
                    + " of times in peers %s" % (
                        disk_num
                    )
                )

            #And finally, check all the peers UUID's:
            if disks_data[disk_num][3:] != disks_data[0][3:]:
                raise RuntimeError("Unsynced peers")

        #All the checks came back positive, ready to update disks
        for disk_num in range(len(self._disks)):
            self._disks[disk_num]["level"] = int(disks_data[disk_num][0])
            self._disks[disk_num]["common_UUID"] = disks_data[disk_num][1]
            self._disks[disk_num]["disk_UUID"] = disks_data[disk_num][2]

            if disk_num == rebuild_disk:
                self._disks[disk_num]["state"] = constants.REBUILD
                #TODO: NEED TO ADD ACTUAL REBUILD TO STATE_MACHINE
                #return InitService.REBUILD_STATE
            else:
                self._disks[disk_num]["state"] = constants.ONLINE

        entry.state = constants.SEND_CONTENT_STATE
        return InitService.FINAL_STATE

    def before_scratch_mount(self, entry):
        common_uuid = str(uuid.uuid4())
        disks_uuids = []

        for disk in self._disks:
            disk["common_UUID"] = common_uuid
            disk["state"] = constants.ONLINE
            disk["level"] = 0
            disk["disk_UUID"] = str(uuid.uuid4())
            disks_uuids.append(disk["disk_UUID"])

        request_info = {}
        for disk_num in range(len(self._disks)):
            boundary = post_util.generate_boundary()
            request_info[disk_num] = {
                "boundary" : boundary,
                "content" : self.create_disk_info_content(
                    boundary,
                    disk_num,
                    disks_uuids
                )
            }

        #create a disk manager
        self._disk_manager = disk_manager.DiskManager(
            self._pollables,
            entry,
            service_util.create_file_upload_contexts(
                self._disks,
                request_info
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False    #need input, not an epsilon_path

    def after_scratch_mount(self, entry):
        #check if got a response from ALL of the
        #block devices:
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            #Should delete the disk array, initilization has failed
            raise RuntimeError(
                (
                    "Initilization failed"
                    + "Block Device Server sent a bad status code: %s"
                ) % (
                    client_responses[0]["status"]
                )
            )
        entry.state = constants.SEND_CONTENT_STATE
        return InitService.FINAL_STATE

    # STATE_MACHINE:

    #           SETUP_STATE
    #           /         \
    #    EXST_MOUNT      SCRATCH_MOUNT
    #          \          /
    #           FINAL_STATE

    STATES = [
        state.State(
            SETUP_STATE,
            [SCRATCH_MOUNT_STATE, EXISTING_MOUNT_STATE],    #order matters! scratch arg
            before_setup,
            after_setup
        ),
        state.State(
            EXISTING_MOUNT_STATE,
            [FINAL_STATE],
            before_existing_mount,
            after_existing_mount
        ),
        state.State(
            SCRATCH_MOUNT_STATE,
            [FINAL_STATE],
            before_scratch_mount,
            after_scratch_mount
        ),
        state.State(
            FINAL_STATE,
            [FINAL_STATE]
        )
    ]

    def before_response_status(self, entry):
        #create initilization state machine
        self._state_machine = state_machine.StateMachine(
            InitService.STATES,
            InitService.STATES[InitService.SETUP_STATE],
            InitService.STATES[InitService.FINAL_STATE]
        )
        return True

    def before_response_headers(self, entry):
        #pass args to the machine, will use *args to pass them on
        return self._state_machine.run_machine((self, entry))

    def before_response_content(self, entry):
        #Re-send the management part
        self._response_content = html_util.create_html_page(
            "",
            constants.HTML_DISPLAY_HEADER,
            0,
            display_disks_service.DisplayDisksService.get_name(),
        )
        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True

    def on_finish(self, entry):
        #pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    def create_disk_info_content(
        self,
        boundary,
        disk_num,
        disks_uuids,
    ):
        #actual file content
        #disk info files are of the following format:
        # level \r\n
        # common_uuid \r\n
        # disk_uuid \r\n
        # peer_uuids \r\n

        return post_util.make_post_content(
            boundary,
            {
                (
                    (
                        "Content-Disposition : form-data; filename='%s%s'"
                    ) % (
                        constants.DISK_INFO_NAME,
                        disk_num
                    )
                ) : (
                    (
                        "%s"*7
                    ) % (
                        self._disks[disk_num]["level"],
                        constants.CRLF_BIN,
                        self._disks[disk_num]["common_UUID"],
                        constants.CRLF_BIN,
                        self._disks[disk_num]["disk_UUID"],
                        constants.CRLF_BIN,
                        constants.CRLF_BIN.join(disks_uuids)
                    )
                )
            }
        )
