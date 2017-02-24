# -*- coding: utf-8 -*-
import argparse
import contextlib
import errno
import fcntl
import logging
import os
import select
import socket
import traceback

import pollable
import poller
import services

from ..common import constants
from ..common import util

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse

(
    LISTEN_STATE,
    REQUEST_STATE,
    HEADERS_STATE,
    CONTENT_STATE,
    RESPONSE_STATUS_STATE,
    RESPONSE_HEADERS_STATE,
    RESPONSE_CONTENT_STATE,
    CLOSING_STATE,
) = range(8)

STATUS_CODES = {
    200 : "OK",
    401 : "Unauthorized",
    404 : "File Not Found",
    500 : "Internal Error",
}

CACHE_HEADERS = {
    "Cache-Control" : "no-cache, no-store, must-revalidate",
    "Pragm" : "no-cache",
    "Expires" : "0"
}


class HttpSocket(pollable.Pollable):
    def __init__(self, socket, state):
        self._socket = socket
        self._fd = socket.fileno()
        self._recvd_data = ""
        self._data_to_send = ""

        self._state = state
        self._request_context = {
            "headers" : {},
            "method": "uknown",
            "uri": "uknown"
        }        #important stuff from request
        self._service = None

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, s):
        self._state = s

    @property
    def request_context(self):
        return self._request_context

    @request_context.setter
    def request_context(self, r):
        self._request_context = r

    @property
    def recvd_data(self):
        return self._recvd_data

    @recvd_data.setter
    def recvd_data(self, r):
        self._recvd_data = r

    @property
    def data_to_send(self):
        return self._data_to_send

    @data_to_send.setter
    def data_to_send(self, d):
        self._data_to_send = d

    @property
    def socket(self):
        return self._socket

    @property
    def fd(self):
        return self._fd


    def request_state(self, socket_data, base):
        index = self._recvd_data.find(constants.CRLF_BIN)
        if index == -1:
            return False

        req, rest = (
            self._recvd_data[:index].decode('utf-8'),
            self._recvd_data[index + len(constants.CRLF_BIN):]
        )
        self.handle_request(req, base)
        self._recvd_data = rest            #save the rest for next time

        return True

    def headers_state(self, socket_data, base):
        lines = self._recvd_data.split(constants.CRLF_BIN)
        if "" not in lines:
            return False

        #got all the headers, process them
        self._request_context["headers"] = {}
        for index in range(len(lines)):
            line = lines[index]

            if (
                len(self._request_context["headers"].items()) >
                constants.MAX_NUMBER_OF_HEADERS
            ):
                raise RuntimeError('Too many headers')

            if line == "":
                self._recvd_data = constants.CRLF_BIN.join(lines[index + 1:])
                break

            k, v = util.parse_header(line)
            if k in self._service.wanted_headers:
                self._request_context["headers"][k] = v

        self._service.before_content(self)
        return True

    def content_state(self, socket_data, base):
        if "Content-Length" not in self._request_context["headers"].keys():
            return True

        #update content_length
        self._request_context["headers"]["Content-Length"] = (
            int(self._request_context["headers"]["Content-Length"]) -
            len(self._recvd_data)
        )
        self._service.handle_content(self, self._recvd_data)
        self._recvd_data = ""

        if self._request_context["headers"]["Content-Length"] < 0:
            raise RuntimeError("Too much content")
        elif self._request_context["headers"]["Content-Length"] > 0:
            return False
        return True

    def response_status_state(self, max_buffer):
        self._service.before_response_status(self)
        self._data_to_send += (
            (
                '%s %s %s\r\n'
            ) % (
                constants.HTTP_SIGNATURE,
                self._service._response_status,
                STATUS_CODES[self._service._response_status]
            )
        )
        return True

    def response_headers_state(self, max_buffer):
        self._service.before_response_headers(self)
        headers = self._service._response_headers
        headers.update(CACHE_HEADERS)

        for header, content in headers.items():
            self._data_to_send += (
                (
                    "%s : %s\r\n"
                ) % (
                    header,
                    content,
                )
            )
        self._data_to_send += "\r\n"
        return True

    def response_content_state(self, max_buffer):
        finished_content = self._service.before_response_content(
            self,
            max_buffer
        )
        self._data_to_send += self._service.response_content
        self._service.response_content = ""
        return finished_content


    #handlers:
    states = {
        REQUEST_STATE : {
            "function" : request_state,
            "next" : HEADERS_STATE
        },
        HEADERS_STATE : {
            "function" : headers_state,
            "next" : CONTENT_STATE
        },
        CONTENT_STATE : {
            "function" : content_state,
            "next" : RESPONSE_STATUS_STATE
        },
        RESPONSE_STATUS_STATE : {
            "function" : response_status_state,
            "next" : RESPONSE_HEADERS_STATE,
        },
        RESPONSE_HEADERS_STATE : {
            "function" : response_headers_state,
            "next" : RESPONSE_CONTENT_STATE,
        },
        RESPONSE_CONTENT_STATE : {
            "function" : response_content_state,
            "next" : CLOSING_STATE,
        },
        CLOSING_STATE : {
            "next" : CLOSING_STATE,
        }
    }

    def on_read(self, socket_data, base):
        try:
            self.get_buf()
            while (self._state < RESPONSE_STATUS_STATE and (
                HttpSocket.states[self._state]["function"](
                    self,
                    socket_data,
                    base,
                ))
            ):
                self._state = HttpSocket.states[self._state]["next"]
                logging.debug(
                    "%s :\t Reading, current state: %s"
                    % (
                        self,
                        self._state
                    )
                )

        except Exception as e:
            logging.error("%s :\t Closing socket, got : %s " % (self, e))
            self.state = CLOSING_STATE
            self.add_status(500, e)

    def on_error(self):
        self._socket.close()

    def on_write(self, max_buffer, socket_data = None):
        while (self._state < CLOSING_STATE and (
            HttpSocket.states[self._state]["function"](
                self,
                max_buffer,
            ))
        ):
            self._state = HttpSocket.states[self._state]["next"]
            logging.debug(
                "%s :\t Writing, current state: %s"
                % (
                    self,
                    self._state
                )
            )
        self.send_buf()

    def get_events(self, socket_data, max_connections, max_buffer):
        event = select.POLLERR
        if (
            self._state >= REQUEST_STATE and
            self._state <= CONTENT_STATE and
            len(self._recvd_data) < max_buffer
        ):
            event |= select.POLLIN

        if (
            self._state >= RESPONSE_STATUS_STATE and
            self._state <= RESPONSE_CONTENT_STATE
        ):
            event |= select.POLLOUT
        return event


    #"util"
    def send_buf(self):
        try:
            while self._data_to_send != "":
                self._data_to_send = self._data_to_send[
                    self._socket.send(self._data_to_send.encode('utf-8')):
                ]
        except socket.error, e:
            if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            logging.debug("%s :\t Haven't finished reading yet" % self)

    def get_buf(
        self,
        max_length=constants.MAX_HEADER_LENGTH,
        block_size=constants.BLOCK_SIZE,
    ):
        try:
            t = self._socket.recv(block_size)
            if not t:
                raise util.Disconnect(
                    'Disconnected while sending content'
                )
            self._recvd_data += t

        except socket.error, e:
            if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                raise
            logging.debug("%s :\t Haven't finished writing yet" % self)


    def __repr__(self):
        if self._service is None:
            return "HttpSocket Object: %s" % self._fd
        return (
            "HttpSocket Object: %s, %s"
        ) % (
            self._fd,
            self._service,
        )

    def add_status(self, code, extra):
        self._data_to_send += (
            (
                '%s %s %s\r\n'
                'Content-Type: text/plain\r\n'
                '\r\n'
                'Error %s %s\r\n'
            ) % (
                constants.HTTP_SIGNATURE,
                code,
                STATUS_CODES[code],
                code,
                STATUS_CODES[code],
            )
        )
        self._data_to_send += ('%s' % extra)


    def handle_request(self, request, base):
        req_comps = request.split(' ', 2)

        #check validity
        if req_comps[2] != constants.HTTP_SIGNATURE:
            raise RuntimeError('Not HTTP protocol')
        if len(req_comps) != 3:
            raise RuntimeError('Incomplete HTTP protocol')

        method, uri, signature = req_comps
        if method not in ("GET", "POST"):
            raise RuntimeError(
                "HTTP unsupported method '%s'" % method
            )

        if not uri or uri[0] != '/' or '\\' in uri:
            raise RuntimeError("Invalid URI")

        #update request
        self._request_context["method"] = method
        self._request_context["uri"] = uri

        #choose service
        parse = urlparse.urlparse(self._request_context["uri"])
        self._request_context["args"] = urlparse.parse_qs(parse.query)

        if parse.path in services.SERVICES.keys():
            if len(self._request_context["args"].keys()):
                self._service = services.SERVICES[parse.path](self._request_context["args"])
            else:
                self._service = services.SERVICES[parse.path]()

        elif self._request_context["method"] == "POST":
            self._service = services.FileFormService()

        else:
            file_name = os.path.normpath(
                '%s%s' % (
                    base,
                    os.path.normpath(self._request_context["uri"]),
                )
            )
            #if file_name[:len(base)+1] != base + '\\':
            #    raise RuntimeError("Malicious URI %s" % self._request[1])

            self._service = services.GetFileService(file_name)

# vim: expandtab tabstop=4 shiftwidth=4
