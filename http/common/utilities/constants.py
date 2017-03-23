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

STANDARD_INPUT = 0
STANDARD_OUTPUT = 1
STANDARD_ERROR = 2

DISK_NAME = "http/bds_server/disks/disk"
DISK_INFO_NAME =  "http/bds_server/disks/disk_info"
TMP_FILE_NAME = "tmp_file"

HTML_ERROR_HEADER = "Disk Error"

CACHE_HEADERS = {
    "Cache-Control" : "no-cache, no-store, must-revalidate",
    "Pragma" : "no-cache",
    "Expires" : "0"
}

MIME_MAPPING = {
    'html': 'text/html',
    'png': 'image/png',
    'txt': 'text/plain',
}

#SERVER TYPES
(
    BLOCK_DEVICE_SERVER,
    FRONTEND_SERVER,
)=range(2)

MODULE_DICT = {
    BLOCK_DEVICE_SERVER : [
        "http.bds_server.services.get_block_service",
        "http.bds_server.services.set_block_service",
        "http.common.services.get_file_service",
    ],
    FRONTEND_SERVER : [
        "http.frontend_server.services.read_disk_service",
        "http.frontend_server.services.write_disk_service",
        "http.frontend_server.services.mul_service",
        "http.frontend_server.services.time_service",
        "http.common.services.get_file_service",
        "http.common.services.form_service",
    ],
}


#HTTP STATES:
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
) = range(11)

# vim: expandtab tabstop=4 shiftwidth=4
