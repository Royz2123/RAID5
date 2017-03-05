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

from .. import poller

from ..pollables import pollable
from ..services import services

from .. ..common import constants
from .. ..common import util

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse

(
    CLOSING_STATE,
    SLEEPING_STATE,
    GET_REQUEST_STATE,
    GET_HEADERS_STATE,
    GET_CONTENT_STATE,
    SEND_STATUS_STATE,
    SEND_HEADERS_STATE,
    SEND_CONTENT_STATE,
) = range(7)

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

class HttpSocket(pollable.Pollable, callable.Callable):
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

    states = {
        GET_REQUEST_STATE : {
            "function" : http_util.get_request_state,
            "next" : GET_HEADERS_STATE
        },
        GET_HEADERS_STATE : {
            "function" : http_util.get_headers_state,
            "next" : GET_CONTENT_STATE
        },
        GET_CONTENT_STATE : {
            "function" : http_util.get_content_state,
            "next" : SEND_STATUS_STATE
        },
        SEND_STATUS_STATE : {
            "function" : http_util.send_status_state,
            "next" : SEND_HEADERS_STATE,
        },
        SEND_HEADERS_STATE : {
            "function" : http_util.send_headers_state,
            "next" : SEND_CONTENT_STATE,
        },
        SEND_CONTENT_STATE : {
            "function" : http_util.send_content_state,
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
            self.on_error()
            self.add_status(500, e)

    def on_error(self):
        self._state = CLOSING_STATE

    def on_close(self):
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
