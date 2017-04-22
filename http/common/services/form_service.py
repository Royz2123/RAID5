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
from http.common.utilities import html_util
from http.common.utilities import util
from http.common.utilities import post_util
from http.frontend_server.pollables import bds_client_socket


class FileFormService(base_service.BaseService):
    (
        START_STATE,
        HEADERS_STATE,
        CONTENT_STATE,
        END_STATE,
    ) = range(4)

    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(self, ["Content-Type"])
        #super(FileFormService, self).__init__(self, ["Content-Type"])
        self._content = ""
        self._boundary = None
        self._fields = {}
        self._state = FileFormService.START_STATE

        self._fd = None
        self._filename = None
        self._arg_name = None

    @staticmethod
    def get_name():
        return "/fileupload"

    def before_content(self, entry):
        content_type = entry.request_context["headers"]["Content-Type"]
        if (
            content_type.find("multipart/form-data") == -1 or
            content_type.find("boundary") == -1
        ):
            raise RuntimeError("Bad Form Request")
        self._boundary = content_type.split("boundary=")[1]

    def start_state(self):
        if self._content.find("--%s" % self._boundary) == -1:
            return False
        self._content = self._content.split(
            "--%s%s" % (
                self._boundary,
                constants.CRLF_BIN
            ), 1
        )[1]
        return True

    def headers_state(self):
        lines = self._content.split(constants.CRLF_BIN)
        if "" not in lines:
            return False

        #got all the headers, process them
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
            #the info part is surrounded by parenthesies
            info = info[1:-1]
            print name
            if name == "filename":
                self._filename = info
                self._fd = os.open(
                    constants.TMP_FILE_NAME,
                    os.O_RDWR | os.O_CREAT,
                    0o666
                )
            elif name == "name":
                self._arg_name = info
                self._args[info] = [""]
        return True

    def end_boundary(self):
        return "%s--%s--%s" % (
            constants.CRLF_BIN,
            self._boundary,
            constants.CRLF_BIN
        )

    def mid_boundary(self):
        return "%s--%s%s" % (
            constants.CRLF_BIN,
            self._boundary,
            constants.CRLF_BIN
        )

    def content_state(self):
        #first we must check if there are any more mid - boundaries
        if self._content.find(post_util.mid_boundary(self._boundary)) != -1:
            buf = self._content.split(
                post_util.mid_boundary(self._boundary),
                1,
            )[0]
            next_state = 1
        elif self._content.find(post_util.end_boundary(self._boundary)) != -1:
            buf = self._content.split(
                post_util.end_boundary(self._boundary),
                1,
            )[0]
            next_state = 2
        else:
            buf = self._content
            next_state = 0

        if self._filename is not None:
            self.file_handle(buf, next_state)
        else:
            self.arg_handle(buf, next_state)
        self._content = self._content[len(buf):]

        if next_state == 1:
            self._content = self._content.split(
                post_util.mid_boundary(self._boundary),
                1
            )[1]

        return next_state

    BOUNDARY_STATES = {
        START_STATE: {
            "function": start_state,
            "next": HEADERS_STATE,
        },
        HEADERS_STATE: {
            "function": headers_state,
            "next": CONTENT_STATE
        },
        CONTENT_STATE: {
            "function": content_state,
            "next": HEADERS_STATE,
        }
    }

    def handle_content(self, entry, content):
        self._content += content
        while True:
            next_state = FileFormService.BOUNDARY_STATES[self._state]["function"](self)
            if next_state == 0:
                return False
            elif (self._state == FileFormService.CONTENT_STATE and next_state == 2):
                break
            self._state = FileFormService.BOUNDARY_STATES[self._state]["next"]

            logging.debug(
                "%s :\t handling content, current state: %s"
                % (
                    entry,
                    self._state
                )
            )
        return True

    def before_response_headers(self, entry):
        if self._response_status == 200:
            self._response_content = html_util.create_html_page(
                "File was uploaded successfully"
            )
            self._response_headers = {
                "Content-Length" : len(self._response_content),
            }
            return True

    def arg_handle(self, arg, next_state):
        self._args[self._arg_name][0] += buf


    def file_handle(self, buf, next_state):
        while buf:
            buf = buf[os.write(self._fd, buf):]

        self._content = buf + self._content

        if next_state:
            os.rename(
                constants.TMP_FILE_NAME,
                os.path.normpath(self._filename)
            )
            os.close(self._fd)
