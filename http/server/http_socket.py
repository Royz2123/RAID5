# -*- coding: utf-8 -*-
import argparse
import contextlib
import datetime
import errno
import fcntl
import os
import socket
import select
import sys
import time
import traceback

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

class AsyncSocket(object):
    def __init__(self, socket):
        self._socket = socket
        self._fd = socket.fileno()
        self._recvd_data = ""
        self._data_to_send = ""

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

    def send_buf(self):
        try:
            while self._data_to_send != "":
                self._data_to_send = self._data_to_send[
                    self._socket.send(self._data_to_send):
                ]
        except socket.error, e:
            if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                raise

    def get_buf(
        self,
        max_length=constants.MAX_HEADER_LENGTH,
        block_size=constants.BLOCK_SIZE,
    ):
        try:
            t = self._socket.recv(block_size)
            if not t:
                raise util.Disconnect(
                    'Disconnected while waiting for content'
                )
            self._recvd_data += t

        except socket.error, e:
            if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
                raise

    def close_socket(self):
        self._socket.close()


class HttpSocket(AsyncSocket):
    def __init__(self, socket, state):
        super(HttpSocket, self).__init__(socket)
        self._state = state
        self._request_context = {
            "headers" : {},
            "method": "uknown",
            "uri": "uknown"
        }        #important stuff from request
        self._service = ""

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

    #state functions
    def connection_state(self, socket_data):
        new_socket, address = self._socket.accept()

        #set to non blocking
        fcntl.fcntl(
            new_socket.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(new_socket.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK
        )

        #add to database
        socket_data[new_socket.fileno()] = HttpSocket(
            new_socket,
            REQUEST_STATE,
        )

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
        self._service.handle_content(self._recvd_data)
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
        ).encode('utf-8')
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
            ).encode('utf-8')
        self._data_to_send += "\r\n".encode('utf-8')
        return True

    def response_content_state(self, max_buffer):
        finished_content = self._service.before_response_content(
            self,
            max_buffer
        )
        self._data_to_send += self._service.response_content
        self._service.response_content = ""
        return finished_content

    def closing_state(self, socket_data = None):
        if self._state != LISTEN_STATE:
            self._state = CLOSING_STATE
        else:
            if socket_data is None:
                raise RuntimeError("Didn't get socket_data")

            for fd, entry in socket_data.items():
                entry._state = CLOSING_STATE

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
            "function" : closing_state,
            "next" : CLOSING_STATE,
        }
    }

    def on_read(self, socket_data, base):
        try:
            if self._state == LISTEN_STATE:
                self.connection_state(socket_data)
                return

            self.get_buf()
            while (self._state < RESPONSE_STATUS_STATE and (
                HttpSocket.states[self._state]["function"](
                    self,
                    socket_data,
                    base,
                ))
            ):
                self._state = HttpSocket.states[self._state]["next"]

        except IOError as e:
            if e.errno != errno.ENOENT:
                raise
            traceback.print_exc()
            self.add_status(404, e)
        except Exception as e:
            traceback.print_exc()
            self.add_status(500, e)
            self.closing_state(socket_data)

    def on_error(self):
        self.close_socket()

    def on_send(self, max_buffer, socket_data = None):
        while (self._state < CLOSING_STATE and (
            HttpSocket.states[self._state]["function"](
                self,
                max_buffer,
            ))
        ):
            self._state = HttpSocket.states[self._state]["next"]
        self.send_buf()

    def get_events(self, socket_data, max_connections, max_buffer):
        event = select.POLLERR
        if (
            self._state == LISTEN_STATE and
            len(socket_data) < max_connections
        ) or (
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
    def __repr__(self):
        return (
            "\nHttpSocket Object\n"
            "socket: %s\n"
            "state: %s\n"
            "method: %s\n"
            "uri %s\n"
            "headers: %s\n"
            "service: %s\n"
            "recvd_data: \n\nSTART OF DATA\n\n%s\n\nEND OF DATA\n\n"
            "data_to_send: %s\n"
        ) % (
            self._socket,
            self._state,
            self._request_context["method"],
            self._request_context["uri"],
            self._request_context["headers"],
            self._service,
            self._recvd_data,
            self._data_to_send,
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
        ).encode('utf-8')
        self._data_to_send += ('%s' % extra).encode('utf-8')


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
