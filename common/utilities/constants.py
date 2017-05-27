#!/usr/bin/python
## @package RAID5.common.utilities.constants
# Module that defines all of the systems constants
#

import os
import select

## Polling constants
# Define polling constants based on OS
POLLIN, POLLOUT, POLLERR, POLLHUP = (
    1, 4, 8, 16,
) if os.name == "nt" else (
    select.POLLIN, select.POLLOUT, select.POLLERR, select.POLLHUP,
)

## Polling event names (for debugging purposes mostly)
POLL_EVENTS = {
    POLLIN : "POLLIN",
    POLLOUT : "POLLOUT",
    POLLERR : "POLLERR",
    POLLHUP : "POLLHUP",
}

## Default frontend server http bind port
DEFAULT_FRONTEND_HTTP_PORT = 8000

## Default block device http bind port
DEFAULT_BDS_HTTP_PORT = 8090

## Default bind address (should always by "0.0.0.0")
DEFAULT_HTTP_ADDRESS = "0.0.0.0"

## Block size for requesting and recieving blocks.
# constant thoughout entire system
BLOCK_SIZE = 4096

## CRLF new line
CRLF = '\r\n'
CRLF_BIN = CRLF.encode('utf-8')

## Http signature we work with, http version
HTTP_SIGNATURE = 'HTTP/1.1'

## Max size of a header
MAX_HEADER_LENGTH = 4096

## Max headers allowed
MAX_NUMBER_OF_HEADERS = 100

## Max size of a disk info file
MAX_INFO_SIZE = 1000

## Maximum size of a cache. Once exceeded this amount, only block numbers are
## stored in cache (no data)
MAX_CACHE_SIZE = 2**20

## Standard input and outputs
STANDARD_INPUT = 0
STANDARD_OUTPUT = 1
STANDARD_ERROR = 2

## Default base directory for requested files
DEFAULT_BASE_DIRECTORY = "frontend/files"

## Default location for block devices configuraiton files
DEFAULT_BLOCK_CONFIG_DIR = "block_device/disks/"

## Default location for frontend configuraiton file
DEFAULT_FRONTEND_CONFIG_DIR = "frontend/"

## Name of block_device disk. (This will be concatenated with the disk num)
DISK_NAME = "block_device/disks/disk"

## Name of block_device disk info. (This will be concatenated with the disk num)
DISK_INFO_NAME = "block_device/disks/disk_info"

## Temporary file name
TMP_FILE_NAME = "tmp_file"

## Time until a non-declaring server is considered Disconnected
## Will not be able to connect to disk, but still part of list so that disk
## still has a chance to connect again
DISCONNECT_TIME = 5

## Time until a non-declaring server is considered Terminated
## Disk wiill be totally removed from list
TERMINATE_TIME = 20

## HTML headers
HTML_DEFAULT_HEADER = "RAID5 - Message"
HTML_ERROR_HEADER = "Disk Error"
HTML_MANAGEMENT_HEADER = "Management"
HTML_DISPLAY_HEADER = "Available disks"

## HTML Menu bar code
HTML_TOP_BAR_CODE = (
    '<ul>' +
    '<li><a class="active" href="/homepage.html">Home</a></li>' +
    '<li><a href="/menu.html">Menu</a></li>' +
    '<li><a href="/about.html">About</a></li>' +
    '</ul>'
)

## Default time until page refreshes. Once refreshed, the frontend server
## checks for terminated connections of disks
DEFAULT_REFRESH_TIME = 4

## Default style sheet (css)
DEFAULT_STYLE_SHEET = "mystyle.css"

## Default content space css style
DEFAULT_CONTENT_SPACE = "table-space"

## Cache headers
CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0"
}

## Length of a boundary that I create (for forms I make) multipart/form-data
# see @ref common.utilities.post_util.generate_boundary
MY_BOUNDARY_LENGTH = 50

## Length of a long password sent to blocks devices
# see @ref common.utilities.util.generate_password
LONG_PASSWORD_LENGTH = 64

## Seperator for address address:port
ADDRESS_SEPERATOR = ":"

## Mapping between file names
MIME_MAPPING = {
    'html': 'text/html',
    'png': 'image/png',
    'txt': 'text/plain',
    'css': 'text/css',
}

## Server types : Block device, Frontend
(
    BLOCK_DEVICE_SERVER,
    FRONTEND_SERVER,
) = range(2)

## Default time until a block device times out (and checks connections)
DEFAULT_BLOCK_POLL_TIMEOUT = 1000

## Default time until a frontend times out (and checks connections)
DEFAULT_FRONTEND_POLL_TIMEOUT = 200

## Dict of all the mdoules of services a Server can use
MODULE_DICT = {
    BLOCK_DEVICE_SERVER: [
        "block_device.services.get_block_service",
        "block_device.services.set_block_service",
        "block_device.services.login_service",
        "block_device.services.get_disk_info_service",
        "block_device.services.set_disk_info_service",
        "block_device.services.update_level_service",
        "common.services.get_file_service",
        "common.services.form_service",
    ],
    FRONTEND_SERVER: [
        "frontend.services.disconnect_service",
        "frontend.services.connect_service",
        "frontend.services.read_disk_service",
        "frontend.services.write_disk_service",
        "frontend.services.mul_service",
        "frontend.services.time_service",
        "frontend.services.init_service",
        "frontend.services.management_service",
        "frontend.services.display_disks_service",
        "common.services.get_file_service",
        "common.services.form_service",
    ],
}

## States a disk (block device) can be in
(
    OFFLINE,
    ONLINE,
    REBUILD,
    STARTUP,
) = range(4)

## States a volume (multiple block devices) can be in
(
    UNINITIALIZED,
    INITIALIZED,
) = range(2)

## State of disks as informative strings (for debugging purposes mostly)
DISK_STATES = {
    OFFLINE: "OFFLINE STATE",
    ONLINE: "ONLINE STATE",
    REBUILD: "REBUILD STATE",
    STARTUP: "STARTUP STATE"
}

## HTTP States
(
    GET_STATUS_STATE,
    GET_REQUEST_STATE,
    GET_HEADERS_STATE,
    GET_CONTENT_STATE,
    SEND_STATUS_STATE,
    SEND_REQUEST_STATE,
    SEND_HEADERS_STATE,
    SEND_CONTENT_STATE,
    SLEEPING_STATE,
    LISTEN_STATE,
    CLOSING_STATE,
    OFFLINE_STATE,
) = range(12)
