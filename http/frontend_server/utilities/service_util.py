# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import time
import traceback

from http.bds_server.services import get_block_service
from http.bds_server.services import set_block_service
from http.bds_server.services import update_level_service
from http.common.services import form_service
from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util


# helpful functions for many frontend services, that make requests from block
# devices much easier to handle

def create_get_block_contexts(disks, request_info):
    # request_info should be a dict { disknum : blocknum }
    client_contexts = {}
    for disknum, blocknum in request_info.items():
        client_contexts[disknum] = {
            "headers" : {},
            "args" : {"blocknum" : blocknum},
            "disknum" : disknum,
            "disk_address" : disks[disknum]["address"],
            "method" : "GET",
            "service" : (
                get_block_service.GetBlockService.get_name()
            ),
            "content" : ""
        }
    return client_contexts

def create_get_disk_info_contexts(disks, request_info):
    # request_info should just be a list of disknums that we want their infos
    client_contexts = {}
    for disknum in request_info:
        client_contexts[disknum] = {
            "headers" : {},
            "args" : {},
            "disknum" : disknum,
            "disk_address" : disks[disknum]["address"],
            "method" : "GET",
            "service" : "/%s%s" % (
                constants.DISK_INFO_NAME,
                disknum,
            ),
            "content" : ""
        }
    return client_contexts

def create_set_block_contexts(disks, request_info):
    # request_info should be a dict {
    #     disknum : {
    #         "blocknum" : blocknum
    #         "content" : content
    #     }
    # }
    client_contexts = {}
    for disknum in request_info.keys():
        client_contexts[disknum] = {
            "headers" : {},
            "method" : "GET",
            "args" : {"blocknum" : request_info[disknum]["blocknum"]},
            "disknum" : disknum,
            "disk_address" : disks[disknum]["address"],
            "service" : (
                set_block_service.SetBlockService.get_name()
            ),
            "content" : request_info[disknum]["content"],
        }
    return client_contexts


def create_update_level_contexts(disks, request_info):
    # request_info should be a dict { disknum : addition }
    client_contexts = {}
    for disknum, addition in request_info.items():
        client_contexts[disknum] = {
            "headers" : {},
            "method" : "GET",
            "args" : {"add" : addition},
            "disknum" : disknum,
            "disk_address" : disks[disknum]["address"],
            "service" : (
                update_level_service.UpdateLevelService.get_name()
            ),
            "content" : "",
        }
    return client_contexts


def create_file_upload_contexts(disks, request_info):
    # request_info should be a dict {
    #   disknum : {
    #       "boundary" : boundary,
    #       "content" : content
    #   }
    # }
    client_contexts = {}
    for disknum in request_info.keys():
        client_contexts[disknum] = {
            "headers" : {
                "Content-Type" : "multipart/form-data; boundary=%s" % (
                    request_info[disknum]["boundary"]
                )
            },
            "method" : "POST",
            "args" : {},
            "disknum" : disknum,
            "disk_address" : disks[disknum]["address"],
            "service" : (
                form_service.FileFormService.get_name()
            ),
            "content" : request_info[disknum]["content"],
        }
    return client_contexts
