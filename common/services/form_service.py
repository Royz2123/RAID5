#!/usr/bin/python
## @package RAID5.common.services.form_service
# Module that implements the FileFormService service
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
from common.utilities import constants
from common.utilities import html_util
from common.utilities import util
from common.utilities import post_util
from frontend.pollables import bds_client_socket
from common.utilities.state_util import state
from common.utilities.state_util import state_machine

## FileFormService is a HTTP Service class that handles a multipart form
## Important for file upload and such
class FileFormService(base_service.BaseService):
    ## FileFormService States
    (
        START_STATE,
        HEADERS_STATE,
        CONTENT_STATE,
        FINAL_STATE,
    ) = range(4)

    ## Constructor for FileFormService
    # @param entry (pollable) the entry (probably @ref
    # common.pollables.service_socket) using the service
    # @param pollables (dict) All the pollables currently in the server
    # @param args (dict) Arguments for this service
    def __init__(self, entry, pollables, args):
        super(FileFormService, self).__init__(["Content-Type"])

        ## Current content recieved
        self._content = ""

        ## Boundary which the form uses
        self._boundary = None

        ## Fields of the form
        self._fields = {}

        ## State Machine that service uses
        self._state_machine = None

        ## File descriptor of file if file is part of the form
        self._fd = None

        ## Filename required to upload in form
        self._filename = None

        ## Temporary file name if something goes wrong
        self._tmp_filename = constants.TMP_FILE_NAME

        ## Name of argument from form
        self._arg_name = None

    ## Name of the service
    # needed for Frontend purposes, creating clients
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/fileupload"

    # STATE FUNCTIONS

    ## Start state after function. Checks if first boundary has been recieved
    ## @param entry (pollable) the entry that the service is assigned to
    ## @returns next_state (int) returns the next state of the state machine
    def after_start(self, entry):
        if self._content.find("--%s" % self._boundary) == -1:
            return None
        self._content = self._content.split(
            "--%s%s" % (
                self._boundary,
                constants.CRLF_BIN
            ), 1
        )[1]
        return FileFormService.HEADERS_STATE

    ## Form headers state after function. Checks if got all headers then
    ## processes them
    ## @param entry (pollable) the entry that the service is assigned to
    ## @returns next_state (int) returns the next state of the state machine
    def after_headers(self, entry):
        lines = self._content.split(constants.CRLF_BIN)
        if "" not in lines:
            return None

        # got all the headers, process them
        headers = {}
        for index in range(len(lines)):
            line = lines[index]
            if line == "":
                self._content = constants.CRLF_BIN.join(lines[index + 1:])
                break

            k, v = util.parse_header(line)
            headers[k] = v

        if "Content-Disposition" not in headers.keys():
            raise RuntimeError("Missing content-disposition header")

        self._filename = None
        self._arg_name = None
        disposition_fields = headers["Content-Disposition"].replace(" ", "")
        disposition_fields = disposition_fields.split(";")[1:]

        for field in disposition_fields:
            name, info = field.split('=', 1)
            # the info part is surrounded by parenthesies
            info = info[1:-1]
            if name == "filename":
                self._filename = info
                self._fd = os.open(
                    self._tmp_filename,
                    os.O_RDWR | os.O_CREAT,
                    0o666
                )
            elif name == "name":
                self._arg_name = info
                self._args[info] = [""]
        return FileFormService.CONTENT_STATE

    ## Content state after function. Checks if got all content and calls
    ## arg_handle or file_handle according to current field
    ## @param entry (pollable) the entry that the service is assigned to
    ## @returns next_state (int) returns the next state of the state machine
    def after_content(self, entry):
        # first we must check if there are any more mid - boundaries
        if self._content.find(post_util.mid_boundary(self._boundary)) != -1:
            buf = self._content.split(
                post_util.mid_boundary(self._boundary),
                1,
            )[0]
            next_state = FileFormService.HEADERS_STATE
        elif self._content.find(post_util.end_boundary(self._boundary)) != -1:
            buf = self._content.split(
                post_util.end_boundary(self._boundary),
                1,
            )[0]
            next_state = FileFormService.FINAL_STATE
        else:
            buf = self._content
            next_state = None

        if self._filename is not None:
            self.file_handle(buf, next_state)
        else:
            self.arg_handle(buf, next_state)
        self._content = self._content[len(buf):]

        if next_state == FileFormService.HEADERS_STATE:
            self._content = self._content.split(
                post_util.mid_boundary(self._boundary),
                1
            )[1]
        return next_state

    ## FileFormService State Machine States
    STATES = [
        state.State(
            START_STATE,
            [HEADERS_STATE],
            after_func=after_start,
        ),
        state.State(
            HEADERS_STATE,
            [CONTENT_STATE],
            after_func=after_headers
        ),
        state.State(
            CONTENT_STATE,
            [HEADERS_STATE, FINAL_STATE],
            after_func=after_content
        ),
        state.State(
            FINAL_STATE,
            [FINAL_STATE]
        )
    ]

    ## Before entry gets content service state. Check this is a multipart
    ## form-data. Initializes the StateMachine.
    ## @param entry (pollable) the entry that the service is assigned to
    def before_content(self, entry):
        content_type = entry.request_context["headers"]["Content-Type"]
        if (
            content_type.find("multipart/form-data") == -1 or
            content_type.find("boundary") == -1
        ):
            raise RuntimeError(
                "%s:\tBad Form Request%s" % (
                    entry,
                    content_type
                )
            )
        self._boundary = content_type.split("boundary=")[1]

        self._state_machine = state_machine.StateMachine(
            FileFormService.STATES,
            FileFormService.STATES[FileFormService.START_STATE],
            FileFormService.STATES[FileFormService.FINAL_STATE]
        )

    ## Handle content service function. Pass on to StateMachine functions
    ## @param entry (pollable) the entry that the service is assigned to
    ## @param content (string) current content that has been recieved
    def handle_content(self, entry, content):
        self._content += content
        # pass args to the machine, will use *args to pass them on
        self._state_machine.run_machine((self, entry))

    ## Before entry sends the response_headers service state.
    ## @param entry (pollable) the entry that the service is assigned to
    def before_response_headers(self, entry):
        if self._response_status == 200:
            self._response_content = html_util.create_html_page(
                "File was uploaded successfully"
            )
            self._response_headers = {
                "Content-Length": len(self._response_content),
            }
        return True

    ## Function that handles arguments from the FileFormService
    ## @param buf (string) buf read from socket
    ## @param next_state (int) if finished reading argument
    def arg_handle(self, buf, next_state):
        self._args[self._arg_name][0] += buf

    ## Function that handles files from the FileFormService
    ## @param buf (string) buf read from socket
    ## @param next_state (int) if finished reading file
    def file_handle(self, buf, next_state):
        while buf:
            buf = buf[os.write(self._fd, buf):]

        self._content = buf + self._content

        if next_state:
            os.rename(
                os.path.normpath(self._tmp_filename),
                os.path.normpath(self._save_filename)
            )
            os.close(self._fd)
