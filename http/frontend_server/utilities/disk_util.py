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

from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util
from http.frontend_server.pollables import bds_client_socket


class DiskUtil():
    @staticmethod
    def add_bds_client(parent, client_context, client_update, pollables):
        new_socket = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        try:
            new_socket.connect((client_context["disk_address"]))
        except socket.error as e:
            #connection refused from disk! build disk refused and raise..
            raise util.DiskRefused(client_context["disknum"])


        #set to non blocking
        fcntl.fcntl(
            new_socket.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(new_socket.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK
        )

        #add to database, need to specify blocknum
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

    @staticmethod
    def all_empty(blocks):
        for block in blocks:
            if len(block):
                return False
        return True

    @staticmethod
    def compute_missing_block(blocks):
        #compute the missing block using parity and XOR
        if blocks == []:
            return None
        new_block = blocks[0]
        for block in blocks[1:]:
            new_block = DiskUtil.xor_blocks(new_block, block)
        return new_block

    @staticmethod
    def xor_blocks(block1, block2):
        for block in (block1, block2):
            block = block.ljust(constants.BLOCK_SIZE, chr(0))

        l1 = [ord(c) for c in list(block1)]
        l2 = [ord(c) for c in list(block2)]
        ans = []
        for i in range(len(l1)):
            ans.append(chr(l1[i] ^ l2[i]))
        return "".join(ans)

    @staticmethod
    def get_physical_disk_num(disks, logic_disk_num, blocknum):
        if DiskUtil.get_parity_disk_num(disks, blocknum) > logic_disk_num:
            return logic_disk_num
        return logic_disk_num + 1

    @staticmethod
    def get_parity_disk_num(disks, blocknum):
        #The parity block (marked as pi) will be in cascading order,
        #for example, if len(disks) = 4 we will get the following division:
        #   |   a1  |   b1  |   c1  |   p1  |
        #   |   a2  |   b2  |   p2  |   c2  |
        #   |   a3  |   p3  |   b3  |   c3  |
        #   |   p4  |   a4  |   b4  |   c4  |
        #               ....
        return (len(disks) - blocknum % len(disks) - 1)
