#!/usr/bin/python
## @package RAID5.common.pollables.service_socket
# Module that defines the ServiceSocket pollable + callable
#

import errno
import logging
import os
import select
import socket
import time
import traceback

from common.pollables import callable
from common.pollables import pollable
from common.services import base_service
from common.utilities import constants
from common.utilities import http_util
from common.utilities import util


## ServiceSocket class that handles requests for services from the server
## Very important class, all of the requests from users and from the Frontend
## are handled by ServiceSockets, which extract the important information
## from the request and call the relevant services
## Inheritance from both the Pollable and Callable classes since the
## ServiceSocket is both a callable and a pollable:
## @ref common.pollables.callable.Callable
## and  @ref common.pollables.pollable.Pollable
class ServiceSocket(pollable.Pollable, callable.Callable):

    ## Constructor for ServiceSocket
    # @param socket (socket) async socket we work with
    # @param state (int) the first state the ServiceSocket will be in
    # @param application_context (dict) the application_context for the
    # server
    # @param pollables (dict) all of the pollables in the server. Many
    # service need this pointer in order to create clients to block devices
    def __init__(self, socket, state, application_context, pollables):
        ## Application_context
        self._application_context = application_context

        ## Request context - important info from request
        self._request_context = {
            "headers": {},
            "args" : [],
            "method": "uknown",
            "uri": "uknown",
        }

        ## Socket to work with
        self._socket = socket

        ## File descriptor of socket
        self._fd = socket.fileno()

        ## Data that the socket has recieved
        self._recvd_data = ""

        ## Data that the socket wishes to send
        self._data_to_send = ""

        ## Current state of the ServiceSocket. Initialized to the first state
        self._state = state

        ## Service that has been chosen to handle the request, based on uri
        self._service = base_service.BaseService()

        ## Dict of all the pollables in the server
        self._pollables = pollables

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

    ## What ServiceSocket does on error.
    ## Sets state to closing state, and adds an error status
    ## see @ref common.pollables.pollable.Pollable
    def on_error(self, e):
        http_util.add_status(self, 500, e)
        self._state = constants.CLOSING_STATE

    ## What ServiceSocket does on close.
    ## Calls the before_terminate service function then closes the socket
    ## required by @ref common.pollables.pollable.Pollable
    def on_close(self):
        self._service.before_terminate(self)
        self._socket.close()

    ## When ListenerSocket is terminating.
    ## Only if socket is closing and we have nothing left to send
    ## required by @ref common.pollables.pollable.Pollable
    def is_terminating(self):
        # check if ready to terminate
        return (
            self._state == constants.CLOSING_STATE
            and self._data_to_send == ""
        )

    ## States for the request state machine. Not implemented with the
    ## StateMachine model since inputs are different, and this case is simpler
    STATES = {
        constants.GET_REQUEST_STATE: {
            "function": http_util.get_request_state,
            "next": constants.GET_HEADERS_STATE
        },
        constants.GET_HEADERS_STATE: {
            "function": http_util.get_headers_state,
            "next": constants.GET_CONTENT_STATE
        },
        constants.GET_CONTENT_STATE: {
            "function": http_util.get_content_state,
            "next": constants.SEND_STATUS_STATE
        },
        constants.SEND_STATUS_STATE: {
            "function": http_util.send_status_state,
            "next": constants.SEND_HEADERS_STATE,
        },
        constants.SEND_HEADERS_STATE: {
            "function": http_util.send_headers_state,
            "next": constants.SEND_CONTENT_STATE,
        },
        constants.SEND_CONTENT_STATE: {
            "function": http_util.send_content_state,
            "next": constants.CLOSING_STATE,
        },
        constants.CLOSING_STATE: {
            "function": on_error,
            "next": constants.CLOSING_STATE,
        }
    }

    ## What ServiceSocket does on read.
    ## first read from socket, then let state machine and service handle
    ## content
    ## func required by @ref common.pollables.pollable.Pollable
    def on_read(self):
        try:
            http_util.get_buf(self)
            while (self._state < constants.SEND_STATUS_STATE and (
                ServiceSocket.STATES[self._state]["function"](self)
            )):
                if self._state == constants.SLEEPING_STATE:
                    return

                self._state = ServiceSocket.STATES[self._state]["next"]
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

    ## The on_finish method, lets the socket wake up after being in sleep mode
    ## see @ref common.pollables.callable.Callable
    def on_finish(self):
        self._service.on_finish(self)

    ## What ServiceSocket does on write.
    ## First let state machine and service update any content they may have,
    ## then send it.
    ## func required by @ref common.pollables.pollable.Pollable
    def on_write(self):
        try:
            while (self._state <= constants.SEND_CONTENT_STATE and (
                ServiceSocket.STATES[self._state]["function"](self)
            )):
                if self._state == constants.SLEEPING_STATE:
                    return

                self._state = ServiceSocket.STATES[self._state]["next"]
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

    ## Specifies what events the ServiceSocket listens to.
    ## Decide based on state and data in buffer.
    ## see @ref common.pollables.pollable.Pollable
    # @returns event (event_mask)
    def get_events(self):
        event = constants.POLLERR
        if (
            self._state >= constants.GET_REQUEST_STATE and
            self._state <= constants.GET_CONTENT_STATE and
            len(self._recvd_data) < self._application_context["max_buffer"]
        ):
            event |= constants.POLLIN

        if (
            self._state >= constants.SEND_STATUS_STATE and
            self._state <= constants.SEND_CONTENT_STATE or
            self._state == constants.CLOSING_STATE
        ):
            event |= constants.POLLOUT
        return event

    ## Returns a representatin of ServiceSocket Object
    # @returns representation (str)
    def __repr__(self):
        if self._service is None:
            return "ServiceSocket Object: %s" % self._fd
        return (
            "ServiceSocket Object: %s, %s"
        ) % (
            self._fd,
            self._service.__class__.__name__,
        )
