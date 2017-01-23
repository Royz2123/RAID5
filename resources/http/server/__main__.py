# -*- coding: utf-8 -*-

import argparse
import contextlib
import errno
import os
import socket
import traceback


from ..common import constants
from ..common import util


MIME_MAPPING = {
    'html': 'text/html',
    'png': 'image/png',
    'txt': 'text/plain',
}


def send_status(s, code, message, extra):
    util.send_all(
        s,
        (
            (
                '%s %s %s\r\n'
                'Content-Type: text/plain\r\n'
                '\r\n'
                'Error %s %s\r\n'
            ) % (
                constants.HTTP_SIGNATURE,
                code,
                message,
                code,
                message,
            )
        ).encode('utf-8')
    )
    util.send_all(
        s,
        (
            '%s' % extra
        ).encode('utf-8')
    )


def parse_args():
    """Parse program argument."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--bind-address',
        default='0.0.0.0',
        help='Bind address, default: %(default)s',
    )
    parser.add_argument(
        '--bind-port',
        default=constants.DEFAULT_HTTP_PORT,
        type=int,
        help='Bind port, default: %(default)s',
    )
    parser.add_argument(
        '--base',
        default='.',
        help='Base directory to search files in, default: %(default)s',
    )
    args = parser.parse_args()
    args.base = os.path.normpath(os.path.realpath(args.base))
    return args


def main():
    args = parse_args()

    with contextlib.closing(
        socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    ) as sl:
        sl.bind((args.bind_address, args.bind_port))
        sl.listen(10)
        while True:
            s, addr = sl.accept()
            with contextlib.closing(s):
                status_sent = False
                try:
                    rest = bytearray()

                    #
                    # Parse request line
                    #
                    req, rest = util.recv_line(s, rest)
                    req_comps = req.split(' ', 2)
                    if req_comps[2] != constants.HTTP_SIGNATURE:
                        raise RuntimeError('Not HTTP protocol')
                    if len(req_comps) != 3:
                        raise RuntimeError('Incomplete HTTP protocol')

                    method, uri, signature = req_comps
                    if method != 'GET':
                        raise RuntimeError(
                            "HTTP unsupported method '%s'" % method
                        )

                    #
                    # Create a file out of request uri.
                    # Be extra careful, it must not escape
                    # the base path.
                    #
                    # NOTICE: os.path.commonprefix cannot be used, checkout:
                    # os.path.commonprefix(('/a/b', '/a/b1'))
                    #
                    # NOTICE: normpath does not remove leading '//', checkout:
                    # os.path.normpath('//a//b')
                    #
                    # NOTICE: os.path.join does not consider 1st component if
                    # 2nd is absolute, checkout:
                    # os.path.join('a', '/b')
                    # os.path.join('a', 'c:/b')  [windows]
                    # os.path.join('a', 'c:\\b') [windows]
                    #
                    # Each of these cases if not handled carefully enables
                    # remote to escape the base path.
                    #
                    # URI must start with / in all operating systems.
                    # Reject DOS (\) based path components.
                    # Normalize URI then append to base (which is normalized),
                    # then normalize again to remove '//.
                    #
                    if not uri or uri[0] != '/' or '\\' in uri:
                        raise RuntimeError("Invalid URI")

                    file_name = os.path.normpath(
                        '%s%s' % (
                            args.base,
                            os.path.normpath(uri),
                        )
                    )

                    #
                    # Parse headers
                    #
                    headers = {
                        'Content-Length': None,
                    }
                    for i in range(constants.MAX_NUMBER_OF_HEADERS):
                        line, rest = util.recv_line(s, rest)
                        if not line:
                            break
                        k, v = util.parse_header(line)
                        if k in headers:
                            headers[k] = v
                    else:
                        raise RuntimeError('Too many headers')

                    #
                    # Receive content if available based on
                    # Content-Length header.
                    # We must receive content as remote is expected
                    # to read response only after it finished sending
                    # content.
                    #
                    if headers['Content-Length'] is not None:
                        # Recv excacly what requested.
                        left_to_read = int(headers['Content-Length'])
                        while left_to_read > 0:
                            if not rest:
                                t = s.recv(constants.BLOCK_SIZE)
                                if not t:
                                    raise RuntimeError(
                                        'Disconnected while waiting for '
                                        'content'
                                    )
                                rest += t
                            buf, rest = (
                                rest[:left_to_read],
                                rest[left_to_read:],
                            )
                            # do something with buf?
                            left_to_read -= len(buf)

                    with open(file_name, 'rb') as f:

                        #
                        # Send headers
                        #
                        util.send_all(
                            s,
                            (
                                (
                                    '%s 200 OK\r\n'
                                    'Content-Length: %s\r\n'
                                    'Content-Type: %s\r\n'
                                    '\r\n'
                                ) % (
                                    constants.HTTP_SIGNATURE,
                                    os.fstat(f.fileno()).st_size,
                                    MIME_MAPPING.get(
                                        os.path.splitext(
                                            file_name
                                        )[1].lstrip('.'),
                                        'application/octet-stream',
                                    ),
                                )
                            ).encode('utf-8')
                        )

                        #
                        # Send content
                        #
                        while True:
                            buf = f.read(constants.BLOCK_SIZE)
                            if not buf:
                                break
                            util.send_all(s, buf)

                except IOError as e:
                    traceback.print_exc()
                    if not status_sent:
                        if e.errno == errno.ENOENT:
                            send_status(s, 404, 'File Not Found', e)
                        else:
                            send_status(s, 500, 'Internal Error', e)
                except Exception as e:
                    traceback.print_exc()
                    if not status_sent:
                        send_status(s, 500, 'Internal Error', e)


if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
