# -*- coding: utf-8 -*-
import errno
import importlib
import logging
import os
import select
import socket
import time
import traceback

from http.common.pollables import callable
from http.common.pollables import pollable
from http.common.utilities import constants
from http.common.utilities import http_util
from http.common.utilities import util
from http.common.services import base_service

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
        self._service = base_service.BaseService()
        self._pollables = None

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

    def on_error(self, e):
        http_util.add_status(self, 500, e)
        self._state = constants.CLOSING_STATE

    def on_close(self):
        self._service.before_terminate(self)
        self._socket.close()

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

    def on_read(self, pollables):
        self._pollables = pollables         #for some services
        try:
            http_util.get_buf(self)
            while (self._state < constants.SEND_STATUS_STATE and (
                ServerSocket.states[self._state]["function"](self)
            )):
                if self._state == constants.SLEEPING_STATE:
                    return

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
            self.on_error(e)

    def on_finish(self):
        self._service.on_finish(self)

    def on_write(self, pollables):
        try:
            while (self._state <= constants.SEND_CONTENT_STATE and (
                ServerSocket.states[self._state]["function"](self)
            )):
                if self._state == constants.SLEEPING_STATE:
                    return

                self._state = ServerSocket.states[self._state]["next"]
                logging.debug(
                    "%s :\t Writing, current state: %s"
                    % (
                        self,
                        self._state
                    )
                )
            if self._state != constants.SLEEPING_STATE:
                http_util.send_buf(self)
        except Exception as e:
            traceback.print_exc()
            logging.error("%s :\t Closing socket, got : %s " % (self, e))
            self.on_error(e)


    def get_events(self, pollables):
        event = select.POLLERR
        if (
            self._state >= constants.GET_REQUEST_STATE and
            self._state <= constants.GET_CONTENT_STATE and
            len(self._recvd_data) < self._application_context["max_buffer"]
        ):
            event |= select.POLLIN

        if (
            self._state >= constants.SEND_STATUS_STATE and
            self._state <= constants.SEND_CONTENT_STATE or
            self._state == constants.CLOSING_STATE
        ):
            event |= select.POLLOUT
        return event


    def __repr__(self):
        if self._service is None:
            return "ServerSocket Object: %s" % self._fd
        return (
            "ServerSocket Object: %s, %s"
        ) % (
            self._fd,
            self._service.__class__.__name__,
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
            print uri
            time.sleep(2)
            raise RuntimeError("Invalid URI")

        #update request
        self._request_context["method"] = method
        self._request_context["uri"] = uri

        #choose service
        parse = urlparse.urlparse(self._request_context["uri"])
        self._request_context["args"] = urlparse.parse_qs(parse.query)

        for service in constants.MODULE_DICT[
            self._application_context["server_type"]
        ]:
            importlib.import_module(service)

        services = {}
        for service_class in base_service.BaseService.__subclasses__():
            services[service_class.get_name()] = service_class

        if parse.path in services.keys():
            self._service = services[parse.path](
                self,
                self._pollables,
                self._request_context["args"]
            )

        else:
            file_name = os.path.normpath(
                '%s%s' % (
                    self._application_context["base"],
                    self._request_context["uri"],
                )
            )
            #if file_name[:len(base)+1] != base + '\\':
            #    raise RuntimeError("Malicious URI %s" % self._request[1])
            self._service = services["/get_file"](self, file_name)


# vim: expandtab tabstop=4 shiftwidth=4
