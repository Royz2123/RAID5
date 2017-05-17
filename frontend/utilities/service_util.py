# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import logging
import os
import socket
import time
import traceback

from block_device.services import get_block_service
from block_device.services import get_disk_info_service
from block_device.services import set_disk_info_service
from block_device.services import set_block_service
from block_device.services import login_service
from block_device.services import update_level_service
from common.services import form_service
from common.services import base_service
from common.utilities import constants
from common.utilities import util


# helpful functions for many frontend services, that make requests from block
# devices much easier to handle

def create_login_contexts(volume):
    # send a login request to all the disks in the volume
    client_contexts = {}
    for disk_UUID, disk in volume["disks"].items():
        client_contexts[disk_UUID] = {
            "headers": {},
            "args": {},
            "disk_UUID": disk_UUID,
            "disk_address": disk["address"],
            "method": "GET",
            "service": (
                login_service.LoginService.get_name()
            ),
            "content": "%s%s%s%s%s" % (
                volume["volume_UUID"],
                constants.CRLF_BIN,
                volume["long_password"],
                constants.CRLF_BIN,
                constants.CRLF_BIN
            ),
        }
    return client_contexts


def create_get_block_contexts(disks, request_info):
    # request_info should be a dict { disk_UUID : blocknum }
    client_contexts = {}
    for disk_UUID, blocknum in request_info.items():
        client_contexts[disk_UUID] = {
            "headers": {},
            "args": {"blocknum": blocknum},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "method": "GET",
            "service": (
                get_block_service.GetBlockService.get_name()
            ),
            "content": ""
        }
    return client_contexts


def create_get_disk_info_contexts(disks, request_info):
    # request_info should just be a list of disk_UUIDs that we want their infos
    client_contexts = {}
    for disk_UUID in request_info:
        client_contexts[disk_UUID] = {
            "headers": {},
            "args": {},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "method": "GET",
            "service": (
                get_disk_info_service.GetDiskInfoService.get_name()
            ),
            "content": ""
        }
    return client_contexts


def create_set_block_contexts(disks, request_info):
    # request_info should be a dict {
    #     disk_UUID : {
    #         "blocknum" : blocknum
    #         "content" : content
    #     }
    # }
    client_contexts = {}
    for disk_UUID in request_info.keys():
        client_contexts[disk_UUID] = {
            "headers": {},
            "method": "GET",
            "args": {"blocknum": request_info[disk_UUID]["blocknum"]},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "service": (
                set_block_service.SetBlockService.get_name()
            ),
            "content": request_info[disk_UUID]["content"],
        }
    return client_contexts


def create_update_level_contexts(disks, request_info):
    # request_info should be a dict { disk_UUID : addition }
    client_contexts = {}
    for disk_UUID, addition in request_info.items():
        client_contexts[disk_UUID] = {
            "headers": {},
            "method": "GET",
            "args": {"add": addition},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "service": (
                update_level_service.UpdateLevelService.get_name()
            ),
            "content": "",
        }
    return client_contexts


def create_file_upload_contexts(disks, request_info):
    # request_info should be a dict {
    #   disk_UUID : {
    #       "boundary" : boundary,
    #       "content" : content
    #   }
    # }
    client_contexts = {}
    for disk_UUID in request_info.keys():
        client_contexts[disk_UUID] = {
            "headers": {
                "Content-Type": "multipart/form-data; boundary=%s" % (
                    request_info[disk_UUID]["boundary"]
                )
            },
            "method": "POST",
            "args": {},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "service": (
                form_service.FileFormService.get_name()
            ),
            "content": request_info[disk_UUID]["content"],
        }
    return client_contexts


def create_set_disk_info_contexts(disks, request_info):
    # request_info should be a dict {
    #   disk_UUID : {
    #       "boundary" : boundary,
    #       "content" : content
    #   }
    # }
    client_contexts = {}
    for disk_UUID in request_info.keys():
        client_contexts[disk_UUID] = {
            "headers": {
                "Content-Type": "multipart/form-data; boundary=%s" % (
                    request_info[disk_UUID]["boundary"]
                )
            },
            "method": "POST",
            "args": {},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "service": (
                set_disk_info_service.SetDiskInfoService.get_name()
            ),
            "content": request_info[disk_UUID]["content"],
        }
    return client_contexts
