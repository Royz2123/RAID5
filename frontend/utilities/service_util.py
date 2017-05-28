#!/usr/bin/python
## @package RAID5.frontend.utilities.disk_util
## Module that defines many service utilities functions. Helpful functions for
## many frontend services, that make requests from block devices much easier to
## handle
#

import base64
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


## Creates login service request_contexts
## @param volume (dict) current volume we're handling
## @returns request_contexts (dict) returns built request contexts for this
## service
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

## Creates get_block service request_contexts
## @param disks (dict) current disks we're handling
## @request_info (dict) specific request info for this context,
## {
##    disk_UUID : {
##        "block_num": block_num,
##        "password" : long_password
##    }
## }
## @returns request_contexts (dict) returns built request contexts for this
## service
def create_get_block_contexts(disks, request_info):
    client_contexts = {}
    for disk_UUID, info in request_info.items():
        client_contexts[disk_UUID] = {
            "headers": {
                "Authorization" : "Basic %s" % (
                    base64.b64encode(info["password"])
                )
            },
            "args": {"block_num": info["block_num"]},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "method": "GET",
            "service": (
                get_block_service.GetBlockService.get_name()
            ),
            "content": ""
        }
    return client_contexts

## Creates get_disk_info service request_contexts
## @param disks (dict) current disks we're handling
## @request_info (list) specific request info for this context,
## request_info should just be a list of disk_UUIDs that we want their infos
## @returns request_contexts (dict) returns built request contexts for this
## service
def create_get_disk_info_contexts(disks, request_info):
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

## Creates set_block service request_contexts
## @param disks (dict) current disks we're handling
## @request_info (dict) specific request info for this context,
## {
##     disk_UUID : {
##         "block_num" : block_num
##         "long_password" : password
##         "content" : content
##     }
## }
## @returns request_contexts (dict) returns built request contexts for this
## service
def create_set_block_contexts(disks, request_info):
    client_contexts = {}
    for disk_UUID, info in request_info.items():
        client_contexts[disk_UUID] = {
            "headers": {
                "Authorization" : "Basic %s" % (
                    base64.b64encode(info["password"])
                )
            },
            "method": "GET",
            "args": {"block_num": info["block_num"]},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "service": (
                set_block_service.SetBlockService.get_name()
            ),
            "content":info["content"],
        }
    return client_contexts

## Creates update_level service request_contexts
## @param disks (dict) current disks we're handling
## @request_info (dict) specific request info for this context,
## {
##    disk_UUID : {
##        "password": long_password,
##        "addition" : addition
##    }
## }
## @returns request_contexts (dict) returns built request contexts for this
## service
def create_update_level_contexts(disks, request_info):
    client_contexts = {}
    for disk_UUID, info in request_info.items():
        client_contexts[disk_UUID] = {
            "headers": {
                "Authorization" : "Basic %s" % (
                    base64.b64encode(info["password"])
                )
            },
            "method": "GET",
            "args": {"add": info["addition"]},
            "disk_UUID": disk_UUID,
            "disk_address": disks[disk_UUID]["address"],
            "service": (
                update_level_service.UpdateLevelService.get_name()
            ),
            "content": "",
        }
    return client_contexts

## Creates set_disk_info service request_contexts
## @param disks (dict) current disks we're handling
## @request_info (dict) specific request info for this context,
## {
##   disk_UUID : {
##       "boundary" : boundary,
##       "content" : content
##   }
## }
## @returns request_contexts (dict) returns built request contexts for this
## service
def create_set_disk_info_contexts(disks, request_info):
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
