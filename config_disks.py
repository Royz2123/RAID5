#!/usr/bin/python
## @package RAID5.config_disks
# Module that can create disk configurations easily
#

import ConfigParser
import os
import sys

from common.utilities import constants
from common.utilities import config_util

## Creates the Block Devices configuration files
## @param disks (int) number of disk configuration files to create
def create_devices(disks):
    for disk_num in range(int(disks)):
        config_util.create_bds_config(
            "%sconfig%s.ini" % (
                constants.DEFAULT_BLOCK_CONFIG_DIR,
                disk_num
            ),
            disk_num
        )

## Creates the Frontend configuration files
def create_frontend():
    config_util.create_frontend_config("%sconfig.ini" % (
        constants.DEFAULT_FRONTEND_CONFIG_DIR
    ))


if __name__ == "__main__":
    create_devices(sys.argv[1])
    create_frontend()
