#!/usr/bin/python
## @package RAID5.frontend.pollables.bds_client_socket
# Module that defines the Block Device Server Client Socket
#

import errno
import logging
import os
import socket
import time
import traceback

from frontend.services import client_services
from common.pollables import pollable
from common.utilities import constants
from common.utilities import http_util
from common.utilities import util

## A HTTP Socket class that requests from Block Device Servers. Often
## Created by Frontend services in order to get data from the different
## Block Devices.
class BDSClientSocket(pollable.Pollable):

    ## Constructor for BDSClientSocket
    ## It can be seen that the HTTP States in this Pollable are in
    ## reverse order to the ServiceSocket, since we are requesting here
    ## and not responding.
    ## @param socket (socket) async socket we work with
    ## @param client_context (dict) the requestcontext we need to send.
    ## @param client_update (dict) pointer to dict where responses need to
    ## be updated.
    ## @param parent (ServiceSocket) the parent ServiceSocket, that is
    ## called when socket has finished (on_finish).
    def __init__(
        self,
        socket,
        client_context,
        client_update,
        parent
    ):
        ## Application_context
        self._application_context = parent.application_context

        ## Client update
        self._client_update = client_update

        ## Socket for the BDSClientSocket
        self._socket = socket

        ## File descriptor of that socket
        self._fd = socket.fileno()

        ## Data socket has recvd
        self._recvd_data = ""

        ## Data socket has to send
        self._data_to_send = ""

        ## Current HTTP State the socket is in
        self._state = constants.SEND_REQUEST_STATE

        ## Request context extracted from the client_context
        self._request_context = {
            "headers": {},
            "status": "uknown",
            "method": client_context["method"],
            "service": client_context["service"],
            "args": client_context["args"]
        }  # important to request

        ## Parent socket that called the BDSClientSocket
        self._parent = parent

        ## Client Service that updates the client update
        self._service = client_services.ClientService(self)

        # Set the services response (this is in fact the request)
        self._service.response_headers = {
            "Content-Length": len(client_context["content"])
        }
        self._service.response_headers.update(client_context["headers"])
        self._service.response_content = client_context["content"]

    ## When BDSClientSocket is terminating.
    ## required by @ref common.pollables.pollable.Pollable
    ## @returns is_terminating (bool) if is closing
    def is_terminating(self):
        return (
            self._state == constants.CLOSING_STATE
            and self._data_to_send == ""
        )


    ## Client update getter
    # @returns client_update (dict)
    @property
    def client_update(self):
        return self._client_update

    ## Client update setter
    # @param c (dict) new client_update
    @client_update.setter
    def client_update(self, c):
        self._client_update = c

    ## State getter
    # @returns State (int)
    @property
    def state(self):
        return self._state

    ## State setter
    # @param s (int) new state for the socket
    @state.setter
    def state(self, s):
        self._state = s

    ## pollables getter
    # @returns pollables (dict)
    @property
    def pollables(self):
        return self._pollables

    ## Service getter
    # @returns Service (@ref common.services.base_service.BaseService)
    @property
    def service(self):
        return self._service

    ## Service setter
    # @param Service (@ref common.services.base_service.BaseService)
    @service.setter
    def service(self, s):
        self._service = s

    ## Request context getter
    # @returns request_context (dict)
    @property
    def request_context(self):
        return self._request_context

    ## Request context setter
    # @param request_context (dict)
    @request_context.setter
    def request_context(self, r):
        self._request_context = r

    ## Application context getter
    # @returns application_context (dict)
    @property
    def application_context(self):
        return self._application_context

    ## Application context setter
    # @param application_context (dict)
    @application_context.setter
    def application_context(self, a):
        self._application_context = a

    ## recvd_data getter
    # @returns recvd_data (str)
    @property
    def recvd_data(self):
        return self._recvd_data

    ## recvd_data getter
    # @param recvd_data (str)
    @recvd_data.setter
    def recvd_data(self, r):
        self._recvd_data = r

    ## data_to_send setter
    # @returns data_to_send (str)
    @property
    def data_to_send(self):
        return self._data_to_send

    ## data_to_send getter
    # @param data_to_send (str)
    @data_to_send.setter
    def data_to_send(self, d):
        self._data_to_send = d

    ## Socket property
    @property
    def socket(self):
        return self._socket

    ## File descriptor property
    @property
    def fd(self):
        return self._fd

    ## What the client does before it closes. Call the parent's on_finish
    ## method and close socket.
    ## required by @ref common.pollables.pollable.Pollable
    def on_close(self):
        self._service.before_terminate(self)
        self._parent.on_finish()
        self._socket.close()

    ## Client State Machine. Reversed to ServiceSocket StateMachine.
    STATES = {
        constants.SEND_REQUEST_STATE: {
            "function": http_util.send_request_state,
            "next": constants.SEND_HEADERS_STATE,
        },
        constants.SEND_HEADERS_STATE: {
            "function": http_util.send_headers_state,
            "next": constants.SEND_CONTENT_STATE,
        },
        constants.SEND_CONTENT_STATE: {
            "function": http_util.send_content_state,
            "next": constants.GET_STATUS_STATE,
        },
        constants.GET_STATUS_STATE: {
            "function": http_util.get_status_state,
            "next": constants.GET_HEADERS_STATE
        },
        constants.GET_HEADERS_STATE: {
            "function": http_util.get_headers_state,
            "next": constants.GET_CONTENT_STATE
        },
        constants.GET_CONTENT_STATE: {
            "function": http_util.get_content_state,
            "next": constants.CLOSING_STATE
        },
        constants.CLOSING_STATE: {
            "next": constants.CLOSING_STATE,
        }
    }

    ## What BDSClientSocket does on read.
    ## first read from socket, then let state machine and service handle
    ## content
    ## func required by @ref common.pollables.pollable.Pollable
    def on_read(self):
        try:
            http_util.get_buf(self)
            while (self._state <= constants.GET_CONTENT_STATE and (
                BDSClientSocket.STATES[self._state]["function"](self)
            )):
                self._state = BDSClientSocket.STATES[self._state]["next"]
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

    ## What BDSClientSocket does on error.
    ## Sets state to closing state.
    ## see @ref common.pollables.pollable.Pollable
    def on_error(self):
        self._state = constants.CLOSING_STATE


    ## What BDSClientSocket does on write.
    ## First let state machine and service update any content they may have,
    ## then send it.
    ## func required by @ref common.pollables.pollable.Pollable
    def on_write(self):
        while ((
            self._state <= constants.SEND_CONTENT_STATE
        ) and (
            BDSClientSocket.STATES[self._state]["function"](self)
        )):
            self._state = BDSClientSocket.STATES[self._state]["next"]
            logging.debug(
                "%s :\t Writing, current state: %s"
                % (
                    self,
                    self._state
                )
            )
        http_util.send_buf(self)

    ## Specifies what events the BDSClientSocket listens to.
    ## Decide based on state and data in buffer.
    ## see @ref common.pollables.pollable.Pollable
    # @returns event (event_mask)
    def get_events(self):
        event = constants.POLLERR
        if (
            self._state >= constants.GET_STATUS_STATE and
            self._state <= constants.GET_CONTENT_STATE and
            len(self._recvd_data) < self._application_context["max_buffer"]
        ):
            event |= constants.POLLIN

        if (
            self._state >= constants.SEND_REQUEST_STATE and
            self._state <= constants.SEND_CONTENT_STATE
        ):
            event |= constants.POLLOUT

        return event

    ## Returns a representation of BDSClientSocket Object
    # @returns representation (str)
    def __repr__(self):
        return (
            "BDSClientSocket Object: %s, %s"
        ) % (
            self._fd,
            self._service.__class__.__name__,
        )
