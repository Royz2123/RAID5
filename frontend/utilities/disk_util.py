# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util
from frontend.pollables import bds_client_socket


def add_bds_client(parent, client_context, client_update, pollables):
    new_socket = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    )
    try:
        new_socket.connect((client_context["disk_address"]))
    except socket.error as e:
        # connection refused from disk! build disk refused and raise..
        raise util.DiskRefused(client_context["disk_UUID"])

    # set to non blocking
    new_socket.setblocking(0)

    # add to database, need to specify blocknum
    new_bds_client = bds_client_socket.BDSClientSocket(
        new_socket,
        client_context,
        client_update,
        parent
    )
    pollables[new_socket.fileno()] = new_bds_client
    logging.debug(
        "%s :\t Added a new BDS client, %s"
        % (
            parent,
            new_bds_client
        )
    )


def all_empty(blocks):
    for block in blocks:
        if len(block):
            return False
    return True


def compute_missing_block(blocks):
    # compute the missing block using parity and XOR
    if blocks == []:
        return None
    new_block = blocks[0]
    for block in blocks[1:]:
        new_block = xor_blocks(new_block, block)
    return new_block


def xor_blocks(block1, block2):
    for block in (block1, block2):
        block = block.ljust(constants.BLOCK_SIZE, chr(0))

    l1 = [ord(c) for c in list(block1)]
    l2 = [ord(c) for c in list(block2)]
    ans = []
    for i in range(len(l1)):
        ans.append(chr(l1[i] ^ l2[i]))
    return "".join(ans)


def get_physical_disk_UUID(disks, logic_disk_UUID, blocknum):
    logic_disk_num = disks[logic_disk_UUID]["disk_num"]

    if get_parity_disk_num(disks, blocknum) > logic_disk_num:
        phy_disk_num = logic_disk_num
    else:
        phy_disk_num = logic_disk_num + 1

    return util.get_disk_UUID_by_num(disks, phy_disk_num)


def get_parity_disk_UUID(disks, blocknum):
    return util.get_disk_UUID_by_num(
        disks,
        get_parity_disk_num(disks, blocknum)
    )


def get_parity_disk_num(disks, blocknum):
    # The parity block (marked as pi) will be in cascading order,
    # for example, if len(disks) = 4 we will get the following division:
    #   |   a1  |   b1  |   c1  |   p1  |
    #   |   a2  |   b2  |   p2  |   c2  |
    #   |   a3  |   p3  |   b3  |   c3  |
    #   |   p4  |   a4  |   b4  |   c4  |
    #               ....
    return (len(disks) - blocknum % len(disks) - 1)
