# -*- coding: utf-8 -*-
import argparse
import contextlib
import errno
import logging
import os
import select
import socket
import time
import traceback

import html_util

from common.utilities import constants
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


def get_request_state(entry):
    index = entry.recvd_data.find(constants.CRLF_BIN)
    if index == -1:
        return False

    req, rest = (
        entry.recvd_data[:index].decode('utf-8'),
        entry.recvd_data[index + len(constants.CRLF_BIN):]
    )
    entry.handle_request(req)
    entry.recvd_data = rest  # save the rest for next time
    return True


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


def send_headers_state(entry):
    entry.service.before_response_headers(entry)
    headers = entry.service.response_headers
    for header, content in headers.items():
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


def send_content_state(entry):
    finished_content = entry.service.before_response_content(entry)
    entry.data_to_send += entry.service.response_content
    entry.service.response_content = ""
    return finished_content


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
