#!/usr/bin/python
## @package RAID5.frontend.utilities.cahce
# Module that defines the Cache class for disconnected disks
#

import errno
import logging
import os
import socket
import time
import traceback

from block_device.services import update_level_service
from common.services import base_service
from common.utilities import constants
from common.utilities import util
from frontend.pollables import bds_client_socket
from frontend.utilities import disk_util

## Cache class that saves the data that needs to be written to disks that are
## offline. A cache instance will be present in every disk dictionary.
class Cache(object):
    ## Cache mode
    (
        DORMANT_MODE,   # No saving cache, disk is online, default
        CACHE_MODE,     # Saving cache while server is online
        SCRATCH_MODE,   # Rebuilding disk from scratch
    ) = range(3)

    ## Cache Mode names (for debugging purposes mostly)
    MODE_NAMES = {
        DORMANT_MODE: "DORMANT MODE",
        CACHE_MODE: "CACHE MODE",
        SCRATCH_MODE: "SCRATCH MODE",
    }

    ## Cache topology
    (
        INCLUDE_DATA,
        EXCLUDE_DATA,
    ) = range(2)

    ## Constructor for Cache class.
    ## @param mode (optional) (int) mode in which the cache will operate
    def __init__(self, mode=DORMANT_MODE):
        ## topology for the cache. initially set to INCLUDE_DATA but once we
        ## fill the cache up too much we will drop it
        self._topology = Cache.INCLUDE_DATA

        ## blocks we saved in the cache. Always a dict; block_num:block_data.
        self._blocks = {}

        ## Cache mode
        self._mode = mode

        ## Points to which block we are currently (relevant for SCRATCH_MODE)
        self._pointer = 0

        ## Blocks handled when rebuilding (relevant for SCRATCH_MODE)
        self._blocks_handled = 0

    ## Mode property
    ## @retruns mode (int)
    @property
    def mode(self):
        return self._mode

    ## Mode property setter
    ## @param mode (int)
    @mode.setter
    def mode(self, m):
        self._mode = m

    ## Pointer property
    ## @returns pointer (int)
    @property
    def pointer(self):
        return self._pointer

    ## Pointer property setter
    ## @param pointer (int)
    @pointer.setter
    def pointer(self, p):
        self._pointer = p

    ## Checks if cache is empty
    ## @returns is_empty (bool)
    def is_empty(self):
        return (
            self._mode == Cache.DORMANT_MODE or
            (
                self._mode == Cache.CACHE_MODE and
                self.size() == 0
            )
        )

    ## Returns the cache size in bytes
    ## @returns size (int) size of cache
    def size(self):
        return (
            len(self._blocks.keys()) *
            constants.BLOCK_SIZE
        )

    ## Returns the percentage of the disk that has been rebuilt. relevant for
    ## SCRATCH_MODE
    ## @returns percentage (float) percentage rebuilt. returns -1 if in
    ## SCRATCH_MODE and percentage is uncalcuable
    def get_rebuild_percentage(self):
        if self._mode == Cache.DORMANT_MODE:
            return 100
        elif self._mode == Cache.CACHE_MODE:
            # to avoid zero divison error
            if len(self._blocks.keys()) == 0:
                return 100
            return (
                float(self._blocks_handled) / (
                    self._blocks_handled +
                    len(self._blocks.keys())
                ) * 100
            )
        else:
            return -1

    ## Checks if the Cache has an overflow in size
    ## @returns overflow (bool) Cache has overflown
    def cache_overflow(self):
        if self._topology == Cache.EXCLUDE_DATA:
            return False
        return self.size() > constants.MAX_CACHE_SIZE

    ## Checks if a block should be added to the Cache. Should not be added if
    ## Cache is in DORMANT_MODE or if in SCRATCH_MODE and haven't reached
    ## the block_num whilst rebuilding.
    ## @param block_num (int) current block_num in writing
    ## @returns to_add (bool) if cache should add block
    def check_if_add(self, block_num):
        if (
            self._mode == Cache.DORMANT_MODE or
            (
                self._mode == Cache.SCRATCH_MODE and
                block_num > self._pointer
            )
        ):
            return False
        return True

    ## Adds a block to the cache. Considers cache overflow
    ## @param block_num (int) current block_num in writing
    ## @param block_data (int) current block_data in writing
    def add_block(self, block_num, block_data):
        # handle overflow:
        if (
            self._topology == Cache.INCLUDE_DATA and
            self.cache_overflow()
        ):
            self.change_topology()

        # add block depending on topology,
        if self._topology == Cache.EXCLUDE_DATA:
            block_data = None
        self._blocks[block_num] = block_data

    ## Returns the next_block in the cache. Works for both topoligies.
    ## @returns block_num, block_data (tuple) Returns the block data if exists
    # and None if not of the next block in cache
    def next_block(self):
        if self._mode == Cache.SCRATCH_MODE:
            block_num = self._pointer
            block_data = None
            self._pointer += 1
        else:
            block_num = sorted(self._blocks.keys())[0]
            block_data = self._blocks[block_num]
            del self._blocks[block_num]
            self._blocks_handled += 1
        return block_num, block_data

    ## representation of Cache objec with first few cache entries.
    ## @returns (str) representation of cache
    def __repr__(self):
        s = "CACHE OBJECT:\n"
        s += "mode:\t%s\n" % Cache.MODE_NAMES[self._mode]

        if self._mode == Cache.SCRATCH_MODE:
            s += "Current pointer index:\t%s" % self._pointer
        else:
            for block_num in self._blocks.keys()[:6]:
                if self._topology == Cache.EXCLUDE_DATA:
                    data = "--EXCLUDING DATA--"
                else:
                    data = "%s..." % self._blocks[block_num][:100].replace(
                        "\n", "")

                s += "%s:\t\t%s\n" % (block_num, data)
        return s

    ## Changes topology from INCLUDE_DATA to EXCLUDE_DATA
    def change_topology(self):
        self._topology = Cache.EXCLUDE_DATA

        # remove all the data for new topology
        for block_num, data in self._blocks.items():
            self._blocks[block_num] = None
