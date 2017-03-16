# -*- coding: utf-8 -*-

BLOCK_SIZE = 4096
CRLF = '\r\n'
CRLF_BIN = CRLF.encode('utf-8')
DEFAULT_HTTP_PORT = 8080
HTTP_SIGNATURE = 'HTTP/1.1'
MAX_HEADER_LENGTH = 4096
MAX_NUMBER_OF_HEADERS = 100

STANDARD_INPUT = 0
STANDARD_OUTPUT = 1
STANDARD_ERROR = 2

DISK_NAME = "http/bds_server/disks/disk"
TMP_FILE_NAME = "tmp_file"
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
    FRONTEND_SERVER
)=range(2)

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
