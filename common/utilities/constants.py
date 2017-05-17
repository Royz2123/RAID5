# -*- coding: utf-8 -*-

DEFAULT_FRONTEND_HTTP_PORT = 8000
DEFAULT_BDS_HTTP_PORT = 8090
DEFAULT_HTTP_ADDRESS = "0.0.0.0"

BLOCK_SIZE = 4096
CRLF = '\r\n'
CRLF_BIN = CRLF.encode('utf-8')
HTTP_SIGNATURE = 'HTTP/1.1'

MAX_HEADER_LENGTH = 4096
MAX_NUMBER_OF_HEADERS = 100
MAX_INFO_SIZE = 1000
MAX_CACHE_SIZE = 2**20

STANDARD_INPUT = 0
STANDARD_OUTPUT = 1
STANDARD_ERROR = 2

DEFAULT_BASE_DIRECTORY = "frontend/files"
DEFAULT_BLOCK_CONFIG_DIR = "block_device/disks/"
DEFAULT_FRONTEND_CONFIG_DIR = "frontend/"

DISK_NAME = "block_device/disks/disk"
DISK_INFO_NAME = "block_device/disks/disk_info"
TMP_FILE_NAME = "tmp_file"

DISCONNECT_TIME = 5
TERMINATE_TIME = 20

HTML_DEFAULT_HEADER = "RAID5 - Message"
HTML_ERROR_HEADER = "Disk Error"
HTML_MANAGEMENT_HEADER = "Management"
HTML_DISPLAY_HEADER = "Available disks"

HTML_TOP_BAR_CODE = (
    '<ul>' +
    '<li><a class="active" href="/homepage.html">Home</a></li>' +
    '<li><a href="/menu.html">Menu</a></li>' +
    '<li><a href="/about.html">About</a></li>' +
    '</ul>'
)

DEFAULT_REFRESH_TIME = 4
DEFAULT_STYLE_SHEET = "mystyle.css"
DEFAULT_CONTENT_SPACE = "table-space"

CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0"
}

MY_BOUNDARY_LENGTH = 50
LONG_PASSWORD_LENGTH = 64

ADDRESS_SEPERATOR = ":"

MIME_MAPPING = {
    'html': 'text/html',
    'png': 'image/png',
    'txt': 'text/plain',
    'css': 'text/css',
}

# SERVER TYPES
(
    BLOCK_DEVICE_SERVER,
    frontend,
) = range(2)

DEFAULT_BLOCK_POLL_TIMEOUT = 1000
DEFAULT_FRONTEND_POLL_TIMEOUT = 200

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
    frontend: [
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

# DISK STATES
(
    OFFLINE,
    ONLINE,
    REBUILD,
    STARTUP,
) = range(4)

# VOLUME_STATES
(
    UNINITIALIZED,
    INITIALIZED,
) = range(2)

DISK_STATES = {
    OFFLINE: "OFFLINE STATE",
    ONLINE: "ONLINE STATE",
    REBUILD: "REBUILD STATE",
    STARTUP: "STARTUP STATE"
}

# HTTP STATES:
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

# vim: expandtab tabstop=4 shiftwidth=4
