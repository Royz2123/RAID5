#!/usr/bin/python
## @package RAID5.common.utilities.http_util
# Module with all the HTTP state functions
#

import argparse
import contextlib
import errno
import importlib
import logging
import os
import select
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import html_util
from common.utilities import util

# python-3 woodo
try:
    # try python-2 module name
    import urlparse
except ImportError:
    # try python-3 module name
    import urllib.parse
    urlparse = urllib.parse

STATUS_CODES = {
    200: "OK",
    401: "Unauthorized",
    404: "File Not Found",
    500: "Internal Error",
}

## State function that recvs and updates the status of a http response.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current Pollable Socket we're dealing with
## @returns next_state (bool) if finished recving first line
def get_status_state(entry):
    index = entry.recvd_data.find(constants.CRLF_BIN)
    if index == -1:
        return False

    status, rest = (
        entry.recvd_data[:index].decode('utf-8'),
        entry.recvd_data[index + len(constants.CRLF_BIN):]
    )
    entry.client_update["status"] = status.split(" ")[1]
    entry.recvd_data = rest
    return True

## State function that recvs and handles the first line of a http status.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current pollable Socket we're dealing with
## @returns next_state (bool) if finished recving first line
def get_request_state(entry):
    index = entry.recvd_data.find(constants.CRLF_BIN)
    if index == -1:
        return False

    req, rest = (
        entry.recvd_data[:index].decode('utf-8'),
        entry.recvd_data[index + len(constants.CRLF_BIN):]
    )
    handle_request(entry, req)
    entry.recvd_data = rest  # save the rest for next time
    return True

## State function that recvs and handles the headers of a http request.
## Saves the headers that the chosen service requires.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current pollable Socket we're dealing with
## @returns next_state (bool) if finished recving headers (got \\r\\n\\r\\n)
def get_headers_state(entry):
    lines = entry.recvd_data.split(constants.CRLF_BIN)
    if "" not in lines:
        return False

    # got all the headers, process them
    entry.request_context["headers"] = {}
    for index in range(len(lines)):
        line = lines[index]
        if (
            len(entry.request_context["headers"].items()) >
            constants.MAX_NUMBER_OF_HEADERS
        ):
            raise RuntimeError('Too many headers')

        if line == "":
            entry.recvd_data = constants.CRLF_BIN.join(lines[index + 1:])
            break

        k, v = util.parse_header(line)
        if k in entry.service.wanted_headers:
            entry.request_context["headers"][k] = v

    entry.service.before_content(entry)
    return True

## State function that recvs and handles the content of a http request.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current pollable Socket we're dealing with
## @returns next_state (bool) if finished recving headers (got \r\n\r\n)
def get_content_state(entry):
    if "Content-Length" not in entry.request_context["headers"].keys():
        return True

    # update content_length
    entry.request_context["headers"]["Content-Length"] = (
        int(entry.request_context["headers"]["Content-Length"]) -
        len(entry.recvd_data)
    )
    entry.service.handle_content(entry, entry.recvd_data)
    entry.recvd_data = ""

    if entry.request_context["headers"]["Content-Length"] < 0:
        raise RuntimeError("Too much content")
    elif entry.request_context["headers"]["Content-Length"] > 0:
        return False
    return True

## State function that sends the status of a http response.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current pollable Socket we're dealing with
## @returns next_state (bool) if finished updating the data_to_send.
def send_status_state(entry):
    entry.service.before_response_status(entry)
    entry.data_to_send += (
        (
            '%s %s %s\r\n'
        ) % (
            constants.HTTP_SIGNATURE,
            entry.service._response_status,
            STATUS_CODES[entry.service._response_status]
        )
    )
    return True

## State function that sends the headers of a http response.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current pollable Socket we're dealing with
## @returns next_state (bool) if finished updating the data_to_send.
def send_headers_state(entry):
    entry.service.before_response_headers(entry)
    for header, content in entry.service.response_headers.items():
        entry.data_to_send += (
            (
                "%s : %s\r\n"
            ) % (
                header,
                content,
            )
        )
    entry.data_to_send += "\r\n"
    return True

## State function that sends the content of a http response.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current pollable Socket we're dealing with
## @returns next_state (bool) if finished updating the data_to_send.
def send_content_state(entry):
    finished_content = entry.service.before_response_content(entry)
    entry.data_to_send += entry.service.response_content
    entry.service.response_content = ""
    return finished_content

## State function that sends the first line of a http request.
## @param entry (@ref common.pollables.pollable.Pollable)
## The current pollable Socket we're dealing with
## @returns next_state (bool) if finished updating the data_to_send.
def send_request_state(entry):
    entry.data_to_send += "%s %s" % (
        entry.request_context["method"],
        entry.request_context["service"]
    )
    if len(entry.request_context["args"]) != 0:
        entry.data_to_send += "?"

        for arg_name, arg_content in entry.request_context["args"].items():
            entry.data_to_send += "%s=%s&" % (
                arg_name,
                arg_content
            )
        entry.data_to_send = entry.data_to_send[:-1]

    entry.data_to_send += " %s%s" % (
        constants.HTTP_SIGNATURE,
        constants.CRLF_BIN
    )
    return True


# OTHER UTIL

## function that sends whatever the socket has in data_to_send
## @param entry (@ref common.pollables.pollable.Pollable)
def send_buf(entry):
    try:
        while entry.data_to_send != "":
            entry.data_to_send = entry.data_to_send[
                entry.socket.send(entry.data_to_send):
            ]
    except socket.error as e:
        if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
            raise
        logging.debug("%s :\t Haven't finished reading yet" % entry)

## function that recieves whatever the socket can recieve and updates
## the recvd_data buffer
## @param entry (@ref common.pollables.pollable.Pollable)
def get_buf(entry):
    try:
        t = entry.socket.recv(entry.application_context["max_buffer"])
        if not t:
            raise util.Disconnect(
                'Disconnected while recieving content'
            )
        entry.recvd_data += t

    except socket.error as e:
        traceback.print_exc()
        if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
            raise
        logging.debug("%s :\t Haven't finished writing yet" % entry)

## Adds an error response_status to the data_to_send buffer
## @param entry (@ref common.pollables.pollable.Pollable) socket we're
## handling currently.
## @param code (int) the (error) code which we got from service
## @param extra (string) extra info reagrading the error
def add_status(entry, code, extra):
    entry.data_to_send += (
        (
            '%s %s %s\r\n'
            'Content-Type: text/html\r\n'
            '\r\n'
            '%s\r\n'
        ) % (
            constants.HTTP_SIGNATURE,
            code,
            STATUS_CODES[code],
            html_util.create_html_page(
                (
                    "Error %s %s\r\n %s"
                ) % (
                    code,
                    STATUS_CODES[code],
                    extra
                )
            )
        )
    )

## Handles a request from a server, and extracts the relevant info. Also
## chooses the correct service
## @param entry (@ref common.pollables.pollable.Pollable) socket we're
## dealing with.
## @param request (string) the first line of the http request
def handle_request(entry, request):
    req_comps = request.split(' ', 2)

    # check validity
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

    # update request
    entry.request_context["method"] = method
    entry.request_context["uri"] = uri

    # choose service
    parse = urlparse.urlparse(entry.request_context["uri"])
    entry.request_context["args"] = urlparse.parse_qs(parse.query)

    # import only the services permitted to this server
    for service in constants.MODULE_DICT[
        entry.application_context["server_type"]
    ]:
        importlib.import_module(service)

    services = {}
    for service_class in base_service.BaseService.__subclasses__():
        services[service_class.get_name()] = service_class

    if parse.path in services.keys():
        entry.service = services[parse.path](
            entry,
            entry.pollables,
            entry.request_context["args"]
        )

    else:
        # Set homepage if necessary, default page
        if entry.request_context["uri"] == "/":
            entry.request_context["uri"] = "/homepage.html"

        file_name = os.path.normpath(
            '%s%s' % (
                entry.application_context["base"],
                entry.request_context["uri"],
            )
        )
        # if file_name[:len(base)+1] != base + '\\':
        #    raise RuntimeError("Malicious URI %s" % self._request[1])
        entry.service = services["/get_file"](entry, file_name)
