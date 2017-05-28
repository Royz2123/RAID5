#!/usr/bin/python
## @package RAID5.common.utilities.post_util
# Module that defines functions for HTTP POST method and multipart forms
#

import errno
import random
import os
import string
import socket
import time

from common.utilities import constants


## Generates a unique boundary to create multipart forms
## @returns boundary (string) long boundary to seperate between parts
def generate_boundary():
    return "MY-BOUNDARY-%s" % ''.join(
        [
            random.choice(string.ascii_letters + string.digits)
            for n in xrange(constants.MY_BOUNDARY_LENGTH)
        ]
    )

## Modifies a given boundary to make it an "end boundary"
## @param boundary (string) existing boundary that needs to be converted to
## an end boundary
## @returns end_boundary (string) end_boundary to show the end of the form
def end_boundary(boundary):
    return "%s--%s--%s" % (
        constants.CRLF_BIN,
        boundary,
        constants.CRLF_BIN
    )

## Modifies a given boundary to make it an "mid boundary"
## @param boundary (string) existing boundary that needs to be converted to
## a mid boundary
## @returns mid_boundary (string) mid_boundary to show that the form has
## more sections.
def mid_boundary(boundary):
    return "%s--%s%s" % (
        constants.CRLF_BIN,
        boundary,
        constants.CRLF_BIN
    )

## Creates a HTTP POST multipart form out of data.
## @param boundary (string) boundary for the form.
## @param content_dict (dict) content that needs to be in the form
## key: item_headers, value: item_content.
## @returns post_content (string) usable form to send via HTTP POST method
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
