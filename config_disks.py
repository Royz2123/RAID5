import ConfigParser
import os
import sys

from common.utilities import constants
from common.utilities import config_util

def create_devices(disks):
    for disk_num in range(int(disks)):
        config_util.create_bds_config(
            "bds_server/disks/config%s.ini" % (
                disk_num
            ),
            disk_num
        )

def create_frontend():
    config_util.create_frontend_config("frontend_server/config.ini")

if __name__ == "__main__":
    create_devices(sys.argv[1])
    create_frontend()
