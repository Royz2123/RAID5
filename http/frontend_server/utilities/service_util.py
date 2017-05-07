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
    # request_info should be a dict { disk_num : blocknum }
    client_contexts = {}
    for disk_num, blocknum in request_info.items():
        client_contexts[disk_num] = {
            "headers" : {},
            "args" : {"blocknum" : blocknum},
            "disk_num" : disk_num,
            "disk_address" : disks[disk_num]["address"],
            "method" : "GET",
            "service" : (
                get_block_service.GetBlockService.get_name()
            ),
            "content" : ""
        }
    return client_contexts

def create_get_disk_info_contexts(disks, request_info):
    # request_info should just be a list of disk_nums that we want their infos
    client_contexts = {}
    for disk_num in request_info:
        client_contexts[disk_num] = {
            "headers" : {},
            "args" : {},
            "disk_num" : disk_num,
            "disk_address" : disks[disk_num]["address"],
            "method" : "GET",
            "service" : "/%s%s" % (
                constants.DISK_INFO_NAME,
                disk_num,
            ),
            "content" : ""
        }
    return client_contexts

def create_set_block_contexts(disks, request_info):
    # request_info should be a dict {
    #     disk_num : {
    #         "blocknum" : blocknum
    #         "content" : content
    #     }
    # }
    client_contexts = {}
    for disk_num in request_info.keys():
        client_contexts[disk_num] = {
            "headers" : {},
            "method" : "GET",
            "args" : {"blocknum" : request_info[disk_num]["blocknum"]},
            "disk_num" : disk_num,
            "disk_address" : disks[disk_num]["address"],
            "service" : (
                set_block_service.SetBlockService.get_name()
            ),
            "content" : request_info[disk_num]["content"],
        }
    return client_contexts


def create_update_level_contexts(disks, request_info):
    # request_info should be a dict { disk_num : addition }
    client_contexts = {}
    for disk_num, addition in request_info.items():
        client_contexts[disk_num] = {
            "headers" : {},
            "method" : "GET",
            "args" : {"add" : addition},
            "disk_num" : disk_num,
            "disk_address" : disks[disk_num]["address"],
            "service" : (
                update_level_service.UpdateLevelService.get_name()
            ),
            "content" : "",
        }
    return client_contexts


def create_file_upload_contexts(disks, request_info):
    # request_info should be a dict {
    #   disk_num : {
    #       "boundary" : boundary,
    #       "content" : content
    #   }
    # }
    client_contexts = {}
    for disk_num in request_info.keys():
        client_contexts[disk_num] = {
            "headers" : {
                "Content-Type" : "multipart/form-data; boundary=%s" % (
                    request_info[disk_num]["boundary"]
                )
            },
            "method" : "POST",
            "args" : {},
            "disk_num" : disk_num,
            "disk_address" : disks[disk_num]["address"],
            "service" : (
                form_service.FileFormService.get_name()
            ),
            "content" : request_info[disk_num]["content"],
        }
    return client_contexts
