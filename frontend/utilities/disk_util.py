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

#check if a list of blocks contains only empty blocks
def all_empty(blocks):
    for block in blocks:
        if len(block):
            return False
    return True

# computes the missing block using parity and XOR
def compute_missing_block(blocks):
    if blocks == []:
        return None
    new_block = blocks[0]
    for block in blocks[1:]:
        new_block = xor_blocks(new_block, block)
    return new_block

# XORs two blocks
def xor_blocks(block1, block2):
    for block in (block1, block2):
        block = block.ljust(constants.BLOCK_SIZE, chr(0))

    l1 = [ord(c) for c in list(block1)]
    l2 = [ord(c) for c in list(block2)]
    ans = []
    for i in range(len(l1)):
        ans.append(chr(l1[i] ^ l2[i]))
    return "".join(ans)

# extracts the disk_UUID of a physical disk given the logic disk_UUID
def get_physical_disk_UUID(disks, logic_disk_UUID, block_num):
    logic_disk_num = disks[logic_disk_UUID]["disk_num"]

    if get_parity_disk_num(disks, block_num) > logic_disk_num:
        phy_disk_num = logic_disk_num
    else:
        phy_disk_num = logic_disk_num + 1

    return util.get_disk_UUID_by_num(disks, phy_disk_num)


def get_parity_disk_UUID(disks, block_num):
    return util.get_disk_UUID_by_num(
        disks,
        get_parity_disk_num(disks, block_num)
    )

# Mathemaitcal function that computes the disk_num of the parity block
# given the volume size and block_num
def get_parity_disk_num(disks, block_num):
    # The parity block (marked as pi) will be in cascading order,
    # for example, if len(disks) = 4 we will get the following division:
    #   |   a1  |   b1  |   c1  |   p1  |
    #   |   a2  |   b2  |   p2  |   c2  |
    #   |   a3  |   p3  |   b3  |   c3  |
    #   |   p4  |   a4  |   b4  |   c4  |
    #               ....
    return (len(disks) - block_num % len(disks) - 1)
