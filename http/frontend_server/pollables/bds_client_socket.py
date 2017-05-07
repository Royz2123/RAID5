import argparse
import contextlib
import errno
import fcntl
import logging
import os
import select
import socket
import time
import traceback

from http.frontend_server.services import client_services
from http.common.pollables import pollable
from http.common.utilities import constants
from http.common.utilities import http_util
from http.common.utilities import util

class BDSClientSocket(pollable.Pollable):
    def __init__(
        self,
        socket,
        client_context,
        client_update,
        parent
    ):
        self._application_context = parent.application_context
        self._client_context = client_context
        self._client_update = client_update

        self._socket = socket
        self._fd = socket.fileno()
        self._recvd_data = ""
        self._data_to_send = ""
        self._state = constants.SEND_REQUEST_STATE

        self._request_context = {
            "headers" : {},
            "status": "uknown",
            "method" : client_context["method"],
            "service" : client_context["service"],
            "args" : client_context["args"]
        }        #important to request

        self._service = client_services.ClientService(self)
        self._service.response_headers = {
            "Content-Length" : len(client_context["content"])
        }
        self._service.response_headers.update(client_context["headers"])
        self._service.response_content = client_context["content"]
        self._parent = parent


    def is_closing(self):
        return self._state == constants.CLOSING_STATE

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
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, p):
        self._parent = p

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
    def client_update(self):
        return self._client_update

    @client_update.setter
    def client_update(self, c_u):
        self._client_update = c_u

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

    def on_close(self):
        self._service.before_terminate(self)
        self._parent.on_finish()
        self._socket.close()

    states = {
        constants.SEND_REQUEST_STATE : {
            "function" : http_util.send_request_state,
            "next" : constants.SEND_HEADERS_STATE,
        },
        constants.SEND_HEADERS_STATE : {
            "function" : http_util.send_headers_state,
            "next" : constants.SEND_CONTENT_STATE,
        },
        constants.SEND_CONTENT_STATE : {
            "function" : http_util.send_content_state,
            "next" : constants.GET_STATUS_STATE,
        },
        constants.GET_STATUS_STATE : {
            "function" : http_util.get_status_state,
            "next" : constants.GET_HEADERS_STATE
        },
        constants.GET_HEADERS_STATE : {
            "function" : http_util.get_headers_state,
            "next" : constants.GET_CONTENT_STATE
        },
        constants.GET_CONTENT_STATE : {
            "function" : http_util.get_content_state,
            "next" : constants.CLOSING_STATE
        },
        constants.CLOSING_STATE : {
            "next" : constants.CLOSING_STATE,
        }
    }

    def on_read(self):
        try:
            http_util.get_buf(self)
            while (self._state <= constants.GET_CONTENT_STATE and (
                BDSClientSocket.states[self._state]["function"](self)
            )):
                self._state = BDSClientSocket.states[self._state]["next"]
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

    def on_error(self):
        self._state = constants.CLOSING_STATE

    def on_write(self):
        while ((
            self._state <= constants.SEND_CONTENT_STATE
        ) and (
            BDSClientSocket.states[self._state]["function"](self)
        )):
            self._state = BDSClientSocket.states[self._state]["next"]
            logging.debug(
                "%s :\t Writing, current state: %s"
                % (
                    self,
                    self._state
                )
            )
        http_util.send_buf(self)

    def get_events(self):
        event = select.POLLERR
        if (
            self._state >= constants.GET_STATUS_STATE and
            self._state <= constants.GET_CONTENT_STATE and
            len(self._recvd_data) < self._application_context["max_buffer"]
        ):
            event |= select.POLLIN

        if (
            self._state >= constants.SEND_REQUEST_STATE and
            self._state <= constants.SEND_CONTENT_STATE
        ):
            event |= select.POLLOUT

        return event


    def __repr__(self):
        return (
            "BDSClientSocket Object: %s, %s"
        ) % (
            self._fd,
            self._service.__class__.__name__,
        )
