# -*- coding: utf-8 -*-
import errno
import logging
import os
import select
import socket
import time
import traceback

from http.bds_server.services import bds_services
from http.common.pollables import callable
from http.common.pollables import pollable
from http.common.utilities import constants
from http.common.utilities import http_util
from http.common.utilities import util
from http.frontend_server.services import frontend_services

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse


CACHE_HEADERS = {
    "Cache-Control" : "no-cache, no-store, must-revalidate",
    "Pragm" : "no-cache",
    "Expires" : "0"
}

class ServerSocket(pollable.Pollable, callable.Callable):
    def __init__(self, socket, state, application_context):
        self._application_context = application_context
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
        self._socket_data = None

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, s):
        self._state = s

    @property
    def service(self):
        return self._service

    @service.setter
    def service(self, s):
        self._service = s

    @property
    def request_context(self):
        return self._request_context

    @request_context.setter
    def request_context(self, r):
        self._request_context = r

    @property
    def application_context(self):
        return self._application_context

    @application_context.setter
    def application_context(self, a):
        self._application_context = a

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


    def on_error(self):
        self._state = constants.CLOSING_STATE

    states = {
        constants.GET_REQUEST_STATE : {
            "function" : http_util.get_request_state,
            "next" : constants.GET_HEADERS_STATE
        },
        constants.GET_HEADERS_STATE : {
            "function" : http_util.get_headers_state,
            "next" : constants.GET_CONTENT_STATE
        },
        constants.GET_CONTENT_STATE : {
            "function" : http_util.get_content_state,
            "next" : constants.SEND_STATUS_STATE
        },
        constants.SEND_STATUS_STATE : {
            "function" : http_util.send_status_state,
            "next" : constants.SEND_HEADERS_STATE,
        },
        constants.SEND_HEADERS_STATE : {
            "function" : http_util.send_headers_state,
            "next" : constants.SEND_CONTENT_STATE,
        },
        constants.SEND_CONTENT_STATE : {
            "function" : http_util.send_content_state,
            "next" : constants.CLOSING_STATE,
        },
        constants.CLOSING_STATE : {
            "function" : on_error,          #should change to more appropriate name
            "next" : constants.CLOSING_STATE,
        }
    }

    def on_read(self, socket_data):
        self._socket_data = socket_data         #for some services
        try:
            http_util.get_buf(self)
            while (self._state < constants.SEND_STATUS_STATE and (
                ServerSocket.states[self._state]["function"](self)
            )):
                self._state = ServerSocket.states[self._state]["next"]
                logging.debug(
                    "%s :\t Reading, current state: %s"
                    % (
                        self,
                        self._state
                    )
                )

        except Exception as e:
            traceback.print_exc()
            logging.error("%s :\t Closing socket, got : %s " % (self, e))
            self.on_error()
            http_util.add_status(self, 500, e)


    def on_close(self):
        self._socket.close()

    def on_finish(self):
        self._state = self._service.on_finish(self)

    def on_write(self, socket_data):
        while (self._state <= constants.SEND_CONTENT_STATE and (
            ServerSocket.states[self._state]["function"](self)
        )):
            print "??"
            self._state = ServerSocket.states[self._state]["next"]
            logging.debug(
                "%s :\t Writing, current state: %s"
                % (
                    self,
                    self._state
                )
            )
        http_util.send_buf(self)

    def get_events(self, socket_data):
        event = select.POLLERR
        if (
            self._state >= constants.GET_REQUEST_STATE and
            self._state <= constants.GET_CONTENT_STATE and
            len(self._recvd_data) < self._application_context["max_buffer"]
        ):
            event |= select.POLLIN

        if (
            self._state >= constants.SEND_STATUS_STATE and
            self._state <= constants.SEND_CONTENT_STATE
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


    def handle_request(self, request):
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

        if (
            self._application_context["server_type"]
            == constants.BLOCK_DEVICE_SERVER
        ):
            services = bds_services
        elif (
            self._application_context["server_type"]
            == constants.FRONTEND_SERVER
        ):
            services = frontend_services
        else:
            raise RuntimeError(
                "Unsupported server_type %s"
                % (
                    self._application_context["server_type"]
                )
            )

        if parse.path in services.SERVICES.keys():
            if parse.path in ("/disk_read", "/disk_write"):
                self._service = services.SERVICES[parse.path](
                    self,
                    self._socket_data,
                    self._request_context["args"]
                )
            elif len(self._request_context["args"].keys()):
                self._service = services.SERVICES[parse.path](self._request_context["args"])
            else:
                self._service = services.SERVICES[parse.path]()


        elif self._request_context["method"] == "POST":
            self._service = services.FileFormService()

        else:
            file_name = os.path.normpath(
                '%s%s' % (
                    self._application_context["base"],
                    os.path.normpath(self._request_context["uri"]),
                )
            )
            #if file_name[:len(base)+1] != base + '\\':
            #    raise RuntimeError("Malicious URI %s" % self._request[1])

            self._service = services.GetFileService(file_name)


# vim: expandtab tabstop=4 shiftwidth=4
