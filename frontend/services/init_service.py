#!/usr/bin/python
## @package RAID5.frontend.services.init_service
## Module that defines the InitService service class.
## The service recieves brings a logical volume online
#

import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.services import form_service
from common.utilities import config_util
from common.utilities import constants
from common.utilities import html_util
from common.utilities import post_util
from common.utilities.state_util import state
from common.utilities.state_util import state_machine
from common.utilities import util
from frontend.services import display_disks_service
from frontend.utilities import disk_manager
from frontend.utilities import cache
from frontend.utilities import disk_util
from frontend.utilities import service_util

## Frontend InitService. This service initializes a volume array of disks. It
## recognizes in which state the disks of the volume are already in, and
## initializes accordingly (SCRATCH_MODE or EXISTING_MODE)
class InitService(base_service.BaseService):
    ## Initialization modes
    (
        EXISTING_MODE,
        SCRATCH_MODE,
    ) = range(2)

    ## Initialization satates
    (
        SETUP_STATE,
        LOGIN_STATE,
        EXISTING_MOUNT_STATE,
        SCRATCH_MOUNT_STATE,
        FINAL_STATE,
    ) = range(5)

    ## Constructor for InitService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(InitService, self).__init__()

        ## Http arguments
        self._args = args  # args will be checked independently

        ## Pollables of the Frontend server
        self._pollables = pollables

        ## Volume we're dealing with
        self._volume = None  # still not sure what volume we're dealing with

        ## Initialization mode
        self._mode = None

        ## StateMachine object
        self._state_machine = None

        ## Disk Manager that manages all the clients
        self._disk_manager = None

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/init"

    # STATE FUNCTIONS

    ## Before setup function. check what volume is required.
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_setup(self, entry):
        # create a list of available_disks
        new_disks = []
        for arg_name, arg_info in self._args.items():
            new_disks.append(arg_info[0])

        # first check the number of disks requested to create a volume
        if len(new_disks) < 2:
            raise RuntimeError(
                "%s:\tNot enough disks for a RAID5 volume (need at least 2): %s" %
                (entry, len(new_disks)))

        # check if all the disks are available_disks
        for disk_UUID in new_disks:
            if disk_UUID not in entry.application_context["available_disks"].keys(
            ):
                raise RuntimeError(
                    "%s:\t One or more of the disks is offline" % entry
                )

        # check all the disks have the same volume_UUID,
        # either an empty string or something else.
        common_UUID = entry.application_context["available_disks"][
            new_disks[0]
        ]["volume_UUID"]
        for disk_UUID in new_disks:
            if (entry.application_context["available_disks"]
                    [disk_UUID]["volume_UUID"] != common_UUID):
                raise RuntimeError(
                    "%s:\t Got two different volumes" % entry
                )

        # check if volume_UUID is in the system (if not "")
        if common_UUID == "":
            self._mode == InitService.SCRATCH_MODE

            # create a new volume_UUID and write in config_file
            volume_UUID = util.generate_uuid()
            long_password = util.generate_password()

            # add volume to list of all volumes
            entry.application_context["volumes"][volume_UUID] = {
                "volume_UUID": volume_UUID,
                "volume_state": constants.INITIALIZED,
                "long_password": long_password,
                "disks": {},
            }

            # update the config_file with the new volume
            config_util.write_section_config(
                entry.application_context["config_file"],
                "volume%s" % len(entry.application_context["volumes"]),
                {
                    "volume_UUID": volume_UUID,
                    "long_password": long_password
                }
            )

        else:
            self._mode = InitService.EXISTING_MODE

            # use existing volume uuid and long password
            volume_UUID = entry.application_context["available_disks"][
                new_disks[0]
            ]["volume_UUID"]
            long_password = entry.application_context["volumes"][volume_UUID][
                "long_password"
            ]

            # check if UUID is in config file sections
            if volume_UUID not in entry.application_context["volumes"].keys():
                raise RuntimeError(
                    "%s:\tUnrecognized existing volume"
                )

            # update volume state
            entry.application_context["volumes"][volume_UUID][
                "volume_state"
            ] = constants.INITIALIZED

        # update the initialized volume index
        entry.application_context["volumes"][volume_UUID]["volume_num"] = (
            len(util.initialized_volumes(entry.application_context["volumes"]))
        )

        # add the new disks to this volume:
        for disk_num in range(len(new_disks)):
            # retrieve the disk_UUID
            disk_UUID = new_disks[disk_num]

            # create a declared_disk from the available_disks
            declared_disk = entry.application_context["available_disks"][
                disk_UUID
            ]

            # add the new disk to the volume. key is disk UUID (arg_content)
            entry.application_context["volumes"][volume_UUID]["disks"][
                disk_UUID
            ] = {
                "disk_UUID": disk_UUID,
                "disk_num": disk_num,
                "address": declared_disk["TCP_address"],
                "volume_UUID": volume_UUID,
                "state": constants.STARTUP,
                "cache": cache.Cache(),
                "level": "",
                "peers": "",
            }

        # finally we have our disks. Update as an attribute
        self._volume = entry.application_context["volumes"][volume_UUID]

        # this is an epsilon path, just setting up
        return True

    # Before login to the block devices in the new volume (set password)
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_login(self, entry):
        if self._mode == InitService.EXISTING_MODE:
            # no need to login, already updated
            return True  # epsilon_path

        # need to login to new block device
        self._disk_manager = disk_manager.DiskManager(
            self._volume["disks"],
            self._pollables,
            entry,
            service_util.create_login_contexts(
                self._volume,
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False  # will always need input, not an epsilon_path

    ## After login to each of the Block Devices
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
    def after_login(self, entry):
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "Block Device Server sent a bad status code: %s"
                % (
                    self._disk_manager.get_responses()[0]["status"]
                )
            )
        else:
            # must be in SCRATCH_MODE. return next state
            return InitService.SCRATCH_MOUNT_STATE

    ## Before we mount an existing volume
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_existing_mount(self, entry):
        self._disk_manager = disk_manager.DiskManager(
            self._volume["disks"],
            self._pollables,
            entry,
            service_util.create_get_disk_info_contexts(
                self._volume["disks"],
                self._volume["disks"].keys(),
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False  # will always need input, not an epsilon_path

    ## After we mount an existing volume
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
    def after_existing_mount(self, entry):
        # check if got a response from ALL of the
        # block devices:
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            raise RuntimeError(
                "%s:\tBlock Device Server sent a bad status code"
            )

        # check the actual response
        client_responses = self._disk_manager.get_responses()

        # make the disks_data easily accessible
        disks_data = []
        for disk_UUID in self._volume["disks"].keys():
            disks_data.append(
                client_responses[disk_UUID]["content"].split(
                    constants.MY_SEPERATOR
                )
            )

        # check if a disk need to be rebuilt
        rebuild_disk = None
        for disk_num in range(len(self._volume["disks"])):
            # first lets check the volume_UUID:
            if disks_data[disk_num][1] != disks_data[0][1]:
                raise RuntimeError(
                    "Got two different topoligies: \n%s\n%s" % (
                        disks_data[disk_num][1],
                        disks_data[0][1]
                    )
                )

            # next lets check the generation level
            # By RAID5, we can only rebuild one disk at a time
            if disks_data[disk_num][0] != disks_data[0][0]:
                raise RuntimeError(
                    "initialize only a consistent set (level mixup): %s != %s"
                    % (
                        disks_data[disk_num][0],
                        disks_data[0][0]
                    )
                )

            # Lets now check the disk UUID:
            if disks_data[disk_num][3:].count(disks_data[disk_num][2]) != 1:
                raise RuntimeError(
                    "Disk UUID shows up an invalid amount" +
                    " of times in peers %s" % (
                        disk_num
                    )
                )

            # And finally, check all the peers UUID's:
            if disks_data[disk_num][3:] != disks_data[0][3:]:
                raise RuntimeError("Unsynced peers")

        # All the checks came back positive, ready to update disks
        for disk_UUID, disk in self._volume["disks"].items():
            self._volume["disks"][disk_UUID]["level"] = int(
                disks_data[disk_num][0])
            self._volume["disks"][disk_UUID]["peers"] = disks_data[disk_num][3:]
            self._volume["disks"][disk_UUID]["state"] = constants.ONLINE


        entry.state = constants.SEND_CONTENT_STATE
        return InitService.FINAL_STATE


    ## Before we mount a new volume from scratch
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns epsilon_path (bool) if there is no need for input
    def before_scratch_mount(self, entry):
        peers = self._volume["disks"].keys()  # for order create var
        request_info = {}
        for disk_UUID in self._volume["disks"].keys():
            boundary = post_util.generate_boundary()
            request_info[disk_UUID] = {
                "boundary": boundary,
                "content": self.create_disk_info_content(
                    boundary,
                    disk_UUID,
                    peers,
                )
            }

        # update final disk stats
        for disk_UUID, disk in self._volume["disks"].items():
            self._volume["disks"][disk_UUID]["level"] = 0
            self._volume["disks"][disk_UUID]["peers"] = peers
            self._volume["disks"][disk_UUID]["state"] = constants.ONLINE

        # create a disk manager
        self._disk_manager = disk_manager.DiskManager(
            self._volume["disks"],
            self._pollables,
            entry,
            service_util.create_set_disk_info_contexts(
                self._volume["disks"],
                request_info
            )
        )
        entry.state = constants.SLEEPING_STATE
        return False  # need input, not an epsilon_path

    ## After we mount a new volume from scratch
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns next_state (int) next state of StateMachine. None if not
    ## ready to move on to next state.
    def after_scratch_mount(self, entry):
        # check if got a response from ALL of the
        # block devices:
        if not self._disk_manager.check_if_finished():
            return None
        if not self._disk_manager.check_common_status_code("200"):
            # Should delete the disk array, initilization has failed
            raise RuntimeError(
                "Initilization failed" +
                "Block Device Server sent a bad status code"
            )

        entry.state = constants.SEND_CONTENT_STATE
        return InitService.FINAL_STATE

    ## Initilization states for StateMachine
    STATES = [
        state.State(
            SETUP_STATE,
            [LOGIN_STATE],
            before_func=before_setup
        ),
        state.State(
            LOGIN_STATE,
            [EXISTING_MOUNT_STATE, SCRATCH_MOUNT_STATE],  # order matters
            before_login,
            after_login,
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

    ## Before pollable sends response status service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_status(self, entry):
        # create initilization state machine
        self._state_machine = state_machine.StateMachine(
            InitService.STATES,
            InitService.STATES[InitService.SETUP_STATE],
            InitService.STATES[InitService.FINAL_STATE]
        )
        return True

    ## Before pollable sends response headers service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_headers(self, entry):
        # pass args to the machine, will use *args to pass them on
        return self._state_machine.run_machine((self, entry))

    ## Before pollable sends response content service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_response_content(self, entry):
        # Re-send the management part
        self._response_content = html_util.create_html_page(
            "",
            constants.HTML_DISPLAY_HEADER,
            0,
            display_disks_service.DisplayDisksService.get_name(),
        )
        self._response_headers = {
            "Content-Length": "%s" % len(self._response_content),
        }
        return True

    ## Called when BDSClientSocket invoke the on_finsh method to wake up
    ## the ServiceSocket. Let StateMachine handle the wake up call.
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    def on_finish(self, entry):
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    ## Create the dictionary that can be made into POST method content
    ## multipart form-data
    ## @param boundary (string) boundary we're using
    ## @param disk_uuid (string) current UUID of disk we're initializing
    ## @param disks_uuids (list) list of all the uuids of the disks peers
    def create_disk_info_content(
        self,
        boundary,
        disk_uuid,
        disks_uuids,
    ):
        # actual file content
        # disk info files are of the following format:
        # level \r\n
        # volume_UUID \r\n
        # disk_uuid \r\n
        # peer_uuids \r\n

        return post_util.make_post_content(
            boundary,
            {
                (
                    "Content-Disposition : form-data; filename='irrelevant'"
                ): (
                    (
                        "%s" * 7
                    ) % (
                        0,
                        constants.MY_SEPERATOR,
                        self._volume["volume_UUID"],
                        constants.MY_SEPERATOR,
                        disk_uuid,
                        constants.MY_SEPERATOR,
                        constants.MY_SEPERATOR.join(disks_uuids)
                    )
                )
            }
        )
