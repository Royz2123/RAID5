# -*- coding: utf-8 -*-
import errno
import os
import socket

from common.utilities import constants

#TODO: find how to generate_boundary
def generate_boundary():
    return "hellooooo"

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
