#!/usr/bin/python
## @package RAID5.frontend.utilities.disk_util
# Module that defines many disk utilities functions.
#

import errno
import logging
import os
import socket
import time
import traceback

from common.services import base_service
from common.utilities import constants
from common.utilities import util

## Checks if a list of blocks contains only empty blocks
## @param blocks (list) list of blocks
## @returns all_empty (bool) if all the disks are empty
def all_empty(blocks):
    for block in blocks:
        if len(block):
            return False
    return True

## Computes the missing block using parity and XOR by RAID5 protocol
## @param blocks (list) list of blocks
## @returns missing_block (string) the missing block
def compute_missing_block(blocks):
    if blocks == []:
        return None
    new_block = blocks[0]
    for block in blocks[1:]:
        new_block = xor_blocks(new_block, block)
    return new_block

## XOR's two blocks
## @param block1 (string) first block
## @param block2 (string) second block
## @returns xored_block (string) the XOR between the two blocks
def xor_blocks(block1, block2):
    # add block size in case of uneven byte arrays
    b1 = bytearray(block1) + bytearray(constants.BLOCK_SIZE)
    b2 = bytearray(block2) + bytearray(constants.BLOCK_SIZE)
    b = bytearray(constants.BLOCK_SIZE)

    for i in range(len(b)):
        b[i] = b1[i] ^ b2[i]

    return str(b)

## Extracts the disk_UUID of a physical disk given the logic disk_UUID
## @param disks (dict) dictionary of disks
## @param logic_disk_UUID (string) logical disk UUID
## @param block_num (int) current block number
## @returns phy_UUID (string) physical UUID of the wanted disk
def get_physical_disk_UUID(disks, logic_disk_num, block_num):
    if get_parity_disk_num(disks, block_num) > logic_disk_num:
        phy_disk_num = logic_disk_num
    else:
        phy_disk_num = logic_disk_num + 1

    return util.get_disk_UUID_by_num(disks, phy_disk_num)

## Extracts the parity disk_UUID using RAID5 protocol
## @param disks (dict) dictionary of disks
## @param block_num (int) current block number
## @returns parity_disk_UUID (string) returns the UUID of the parity disk
def get_parity_disk_UUID(disks, block_num):
    return util.get_disk_UUID_by_num(
        disks,
        get_parity_disk_num(disks, block_num)
    )

## Mathemaitcal function that computes the disk_num of the parity block by
## RAID5 protocol given the volume size and block_num.
##
## The parity block (marked as pi) will be in cascading order,
## for example, if len(disks) = 4 we will get the following division:
##   |   a1  |   b1  |   c1  |   p1  |
##   |   a2  |   b2  |   p2  |   c2  |
##   |   a3  |   p3  |   b3  |   c3  |
##   |   p4  |   a4  |   b4  |   c4  |
##               ....
##
## therfore parity_disk_num = (len(disks) - block_num % len(disks) - 1)
##
## @param disks (dict) dictionary of disks
## @param block_num (int) current block number
## @returns parity_disk_num (int) disk_num of parity block
def get_parity_disk_num(disks, block_num):
    return (len(disks) - block_num % len(disks) - 1)
