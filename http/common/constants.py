# -*- coding: utf-8 -*-

BLOCK_SIZE = 1024
CRLF = '\r\n'
CRLF_BIN = CRLF.encode('utf-8')
DEFAULT_HTTP_PORT = 8080
HTTP_SIGNATURE = 'HTTP/1.1'
MAX_HEADER_LENGTH = 4096
MAX_NUMBER_OF_HEADERS = 100

DISK_FILE = "disk"
TMP_FILE_NAME = "tmp_file"
CACHE_HEADERS = 'Cache-Control: no-cache, no-store, must-revalidate\r\nPragma: no-cache\r\nExpires: 0\r\n'

# vim: expandtab tabstop=4 shiftwidth=4
