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

from http.bds_server.services import update_level_service
from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util
from http.frontend_server.pollables import bds_client_socket
from http.frontend_server.utilities import disk_util

class Cache(object):
    #mode
    (
        DORMANT_MODE,   # No saving cache, disk is online, default
        CACHE_MODE,     # Saving cache while server is online
        SCRATCH_MODE,   # Rebuilding disk from scratch
    )=range(3)

    MODE_NAMES = {
        DORMANT_MODE : "DORMANT MODE",
        CACHE_MODE : "CACHE MODE",
        SCRATCH_MODE : "SCRATCH MODE",
    }

    #topology
    (
        INCLUDE_DATA,
        EXCLUDE_DATA,
    )=range(2)

    def __init__(self, mode=DORMANT_MODE):
        self._topology = Cache.INCLUDE_DATA
        self._blocks = {}           # always a dict; blocknum : block_data
        self._mode = mode
        self._pointer = 0           # points to which block we are currently
                                    # rebuilding, relevant for scratch mode
        self._blocks_handled = 0


    @property
    def pointer(self):
        return self._pointer

    @pointer.setter
    def pointer(self, p):
        self._pointer = p

    def is_empty(self):
        return (
            self._mode == Cache.DORMANT_MODE
            or (
                self._mode == Cache.CACHE_MODE
                and self.size() == 0
            )
        )

    def size(self):
        return (
            len(self._blocks.keys())
            * constants.BLOCK_SIZE
        )

    def get_rebuild_percentage(self):
        if self._mode == Cache.DORMANT_MODE:
            return 100
        elif self._mode == Cache.CACHE_MODE:
            #to avoid zero divison error
            if len(self._blocks.keys()) == 0:
                return 100
            return (
                self._blocks_handled / (
                    self._blocks_handled
                    + len(self._blocks.keys())
                ) * 100
            )
        else:
            return -1

    def cache_overflow(self):
        if self._topology == Cache.EXCLUDE_DATA:
            return False
        return self.size() > constants.MAX_CACHE_SIZE

    def check_if_add(self, blocknum):
        if (
            self._mode == Cache.DORMANT_MODE
            or (
                self._mode == Cache.SCRATCH_MODE
                and blocknum > self._pointer
            )
        ):
            return False
        return True

    #return True if added successfully, False otherwise
    def add_block(self, blocknum, block_data):
        #handle overflow:
        if (
            self._topology == Cache.INCLUDE_DATA
            and self.cache_overflow()
        ):
            self.change_topology()

        #add block depending on topology,
        if self._topology == Cache.EXCLUDE_DATA:
            block_data = None
        self._blocks[blocknum] = block_data

    def next_block(self):
        #works for both topoligies, returns the block data if exists
        #and None if not
        if self._mode == Cache.SCRATCH_MODE:
            blocknum = self._pointer
            block_data = None
            self._pointer += 1
        else:
            blocknum = sorted(self._blocks.keys())[0]
            block_data = self._blocks[blocknum]
            del self._blocks[blocknum]
            self._blocks_handled += 1
        return blocknum, block_data

    def __repr__(self):
        s = "CACHE OBJECT:\n"
        s += "mode:\t%s\n" % Cache.MODE_NAMES[self._mode]

        if self._mode == Cache.SCRATCH_MODE:
            s += "Current pointer index:\t%s" % self._pointer
        else:
            for blocknum in self._blocks.keys()[:6]:
                if self._topology == Cache.EXCLUDE_DATA:
                    data = "--EXCLUDING DATA--"
                else:
                    data = "%s..." % self._blocks[blocknum][:100].replace("\n", "")

                s += "%s:\t\t%s\n" % (blocknum, data)
        return s

    #topology change from including data to excluding data
    def change_topology(self):
        self._topology = Cache.EXCLUDE_DATA

        #remove all the data for new topology
        for blocknum, data in self._blocks.items():
            self._blocks[blocknum] = None
