# -*- coding: utf-8 -*-
import errno
import random
import os
import string
import socket
import time

from common.utilities import constants


def generate_boundary():
    return "MY-BOUNDARY-%s" % ''.join(
        [
            random.choice(string.ascii_letters + string.digits)
            for n in xrange(constants.MY_BOUNDARY_LENGTH)
        ]
    )


def end_boundary(boundary):
    return "%s--%s--%s" % (
        constants.CRLF_BIN,
        boundary,
        constants.CRLF_BIN
    )


def mid_boundary(boundary):
    return "%s--%s%s" % (
        constants.CRLF_BIN,
        boundary,
        constants.CRLF_BIN
    )


def make_post_content(boundary, content_dict):
    content = mid_boundary(boundary)
    for item_headers, item_content in content_dict.items():
        content += "%s%s%s%s" % (
            item_headers,
            constants.CRLF_BIN,
            constants.CRLF_BIN,
            item_content
        )
    content += end_boundary(boundary)
    return content
