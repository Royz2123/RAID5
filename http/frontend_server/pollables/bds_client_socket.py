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

from http.frontend_server.services import client_services
from http.common.pollables import pollable
from http.common.utilities import constants
from http.common.utilities import http_util
from http.common.utilities import util



class BDSClientSocket(pollable.Pollable):
    def __init__(
        self,
        socket,
        state,
        args,
        bds_service,
        parent
    ):
        self._application_context = parent.application_context
        self._socket = socket
        self._fd = socket.fileno()
        self._recvd_data = ""
        self._data_to_send = ""

        self._state = state
        self._request_context = {
            "headers" : {},
            "status": "uknown",
            "method" : "GET",
            "service" : bds_service,
            "args" : args
        }        #important to request
        self._service = client_services.SERVICES[bds_service]
        self._parent = parent

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, s):
        self._state = s

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
            "function" : on_close,
            "next" : constants.CLOSING_STATE,
        }
    }

    def on_read(self, socket_data):
        try:
            self.get_buf()
            while (self._state < RESPONSE_STATUS_STATE and (
                HttpSocket.states[self._state]["function"](self)
            )):
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

    def on_write(self, socket_data):
        while (self._state < CLOSING_STATE and (
            HttpSocket.states[self._state]["function"](self)
        )):
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
            return "BDSClientSocket Object: %s" % self._fd
        return (
            "BDSClientSocket Object: %s, %s"
        ) % (
            self._fd,
            self._service,
        )
