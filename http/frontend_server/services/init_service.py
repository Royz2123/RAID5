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
from http.frontend_server.utilities import disk_manager
from http.frontend_server.utilities import cache
from http.frontend_server.utilities import disk_util

class InitService(base_service.BaseService):
    (
        SCRATCH_MODE,
        EXISTING_MODE
    ) = range(2)

    (
        SETUP_STATE,
        HANDLE_INFO_STATE,
        MOUNT_STATE,
    ) = range(3)

    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(self)
        self._args = args     #args will be checked independently
        self._socket_data = socket_data

        entry.application_context["disks"] = []
        self._disks = entry.application_context["disks"]

        self._state = InitService.SETUP_STATE
        self._mode = None

        self._disk_manager = None
        self._client_contexts = {}

    @staticmethod
    def get_name():
        return "/init"

    def reset_client_contexts(self):
        self._client_contexts = {}
        for disknum in range(len(self._disks)):
            self._client_contexts[disknum] = {
                "headers" : {},
                "args" : {},
                "disknum" : disknum,
                "disk_address" : self._disks[disknum]["address"],
                "method" : "GET",
                "service" : "/%s%s" % (
                    constants.DISK_INFO_NAME,
                    disknum,
                ),
                "content" : ""
            }


    def on_finish(self, entry):
        if not self._disk_manager.check_if_finished():
            return
        client_responses = self._disk_manager.get_responses()

        if self._state == InitService.SETUP_STATE:
            if self._disk_manager.check_common_status_code("200"):
                self._mode = InitService.EXISTING_MODE
                logging.debug("SYSTEM INITIALIZING FROM EXISTING MODE")
            elif self._disk_manager.check_common_status_code("404"):
                self._mode = InitService.SCRATCH_MODE
                logging.debug("SYSTEM INITIALIZING FROM SCRATCH MODE")
            else:
                raise RuntimeError(
                    "Block Device Server sent a bad status code: %s"
                    % (
                        client_responses[0]["status"]
                    )
                )

        elif self._state == InitService.HANDLE_INFO_STATE:
            #check if got a response from ALL of the
            #block devices:
            if not self._disk_manager.check_common_status_code("200"):
                raise RuntimeError(
                    "Block Device Server sent a bad status code: %s"
                    % (
                        client_responses[0]["status"]
                    )
                )

        self._state = InitService.STATES[self._state]["next"]
        entry.state = constants.SEND_STATUS_STATE

    def setup_state(self, entry):
        #first check addresses and init disks
        for address_num, disk_address in self._args.items():
            if not util.make_address(disk_address[0]):
                raise RuntimeError("Args must be addresses: (address, port)")

            self._disks.append({
                "address" : util.make_address(disk_address[0]),
                "disk_UUID" : "",
                "common_UUID" : "",
                "level" : "",
                "state" : constants.OFFLINE,
                "cache" : cache.Cache(),
            })

        if len(self._disks) < 2:
            raise RuntimeError("Not enough disks for RAID5")

        #create client with the first address in order to classify mode
        #Now that disks have been established we can proceed
        self.reset_client_contexts()
        self._disk_manager = disk_manager.DiskManager(
            self._socket_data,
            entry,
            {0 : self._client_contexts[0]}
        )
        return False

    def before_response_headers(self, entry):
        #Re-send the management part
        self._response_content = html_util.create_html_page(
            html_util.create_disks_table(entry.application_context["disks"]),
            constants.HTML_MANAGEMENT_HEADER,
            constants.DEFAULT_REFRESH_TIME
        )

        self._response_headers = {
            "Content-Length" : "%s" % len(self._response_content),
        }
        return True

    def before_response_status(self, entry):
        while True:
            next_state = InitService.STATES[self._state]["function"](
                self,
                entry
            )
            if next_state == 0:
                return False
            elif (
                entry.state == constants.SLEEPING_STATE
                or (
                    self._state == InitService.MOUNT_STATE
                    and next_state == 1
                )
            ):
                break
            self._state = InitService.STATES[self._state]["next"]

            logging.debug(
                "%s :\t Initializing disks, current state: %s"
                % (
                    entry,
                    self._state
                )
            )
        return True

    def handle_info_scratch_mode(self, entry):
        common_uuid = str(uuid.uuid4())
        disks_uuids = []

        for disk in self._disks:
            disk["common_UUID"] = common_uuid
            disk["state"] = constants.ONLINE
            disk["level"] = 0
            disk["disk_UUID"] = str(uuid.uuid4())
            disks_uuids.append(disk["disk_UUID"])

        for disknum in range(len(self._disks)):
            self._boundary = post_util.generate_boundary()
            self._client_contexts[disknum]["method"] = "POST"
            self._client_contexts[disknum]["headers"] = {
                "Content-Type" : "multipart/form-data; boundary=%s" % (
                    self._boundary
                )
            }
            self._client_contexts[disknum][
                "service"
            ] = form_service.FileFormService.get_name()

            self._client_contexts[disknum][
                "content"
            ] += self.create_disk_info_content(
                disknum,
                disks_uuids
            )

    def handle_info_existing_mode(self, entry):
        self.reset_client_contexts()

    def mount_scratch_mode(self, entry):
        #already mounted in handle info
        pass

    def mount_existing_mode(self, entry):
        #make the disk data easily accessible
        client_responses = self._disk_manager.get_responses()
        disks_data = []
        for disknum in range(len(self._disks)):
            disks_data.append(
                client_responses[disknum]["content"].split(
                    constants.CRLF_BIN
                )
            )

        rebuild_disk = None
        for disknum in range(len(self._disks)):
            #first lets check the common_uuid:
            if disks_data[disknum][1] != disks_data[0][1]:
                raise RuntimeError(
                    "Got two different topoligies: \n%s\n%s" % (
                        disks_data[disknum][1],
                        disks_data[0][1]
                    )
                )

            #next lets check the generation level
            #By RAID5, we can only rebuild one disk at a time
            if disks_data[disknum][0] != disks_data[0][0]:
                if rebuild_disk is not None:
                    raise RuntimeError(
                        "Already rebuilding disk: %s, can't rebuild 2: %s" % (
                            disks_data[disknum][0],
                            disks_data[0][0]
                        )
                    )
                else:
                    rebuild_disk = disknum

            #Lets now check the disk UUID:
            if disks_data[disknum][3:].count(disks_data[disknum][2]) != 1:
                raise RuntimeError(
                    "Disk UUID shows up an invalid amount"
                    + " of times in peers %s" % (
                        disknum
                    )
                )

            #And finally, check all the peers UUID's:
            if disks_data[disknum][3:] != disks_data[0][3:]:
                raise RuntimeError("Unsynced peers")

        #All the checks came back positive, ready to update disks
        for disknum in range(len(self._disks)):
            self._disks[disknum]["level"] = int(disks_data[disknum][0])
            self._disks[disknum]["common_UUID"] = disks_data[disknum][1]
            self._disks[disknum]["disk_UUID"] = disks_data[disknum][2]
            self._disks[disknum]["state"] = constants.ONLINE


    def handle_info_state(self, entry):
        MODES = {
            InitService.SCRATCH_MODE : InitService.handle_info_scratch_mode,
            InitService.EXISTING_MODE : InitService.handle_info_existing_mode
        }
        MODES[self._mode](self, entry)
        #after info has been set, we can create a disk_manager:
        self._disk_manager = disk_manager.DiskManager(
            self._socket_data,
            entry,
            self._client_contexts
        )
        return False

    def mount_state(self, entry):
        MODES = {
            InitService.SCRATCH_MODE : InitService.mount_scratch_mode,
            InitService.EXISTING_MODE : InitService.mount_existing_mode
        }
        MODES[self._mode](self, entry)
        return True


    STATES = {
        SETUP_STATE: {
            "function": setup_state,
            "next": HANDLE_INFO_STATE,
        },
        HANDLE_INFO_STATE: {
            "function": handle_info_state,
            "next": MOUNT_STATE
        },
        MOUNT_STATE: {
            "function": mount_state,
            "next": MOUNT_STATE,
        }
    }

    def create_disk_info_content(
        self,
        disknum,
        disks_uuids,
    ):
        #actual file content
        #disk info files are of the following format:
        # level \r\n
        # common_uuid \r\n
        # disk_uuid \r\n
        # peer_uuids \r\n

        return post_util.make_post_content(
            self._boundary,
            {
                (
                    (
                        "Content-Disposition : form-data; filename='%s%s'"
                    ) % (
                        constants.DISK_INFO_NAME,
                        disknum
                    )
                ) : (
                    (
                        "%s"*7
                    ) % (
                        self._disks[disknum]["level"],
                        constants.CRLF_BIN,
                        self._disks[disknum]["common_UUID"],
                        constants.CRLF_BIN,
                        self._disks[disknum]["disk_UUID"],
                        constants.CRLF_BIN,
                        constants.CRLF_BIN.join(disks_uuids)
                    )
                )
            }
        )
