# -*- coding: utf-8 -*-

import argparse
import contextlib
import os
import socket
import tempfile


from ..common import constants
from ..common import util


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
        type=int,
        default=0,
        help='Bind port, default: %(default)s',
    )
    parser.add_argument(
        '--url',
        required=True,
        help='URL to use',
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output file',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    url = util.spliturl(args.url)
    if url.scheme != 'http':
        raise RuntimeError("Invalid URL scheme '%s'" % url.scheme)

    with contextlib.closing(
        socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    ) as s:
        s.bind((args.bind_address, args.bind_port))
        s.connect((
            url.hostname,
            url.port if url.port else constants.DEFAULT_HTTP_PORT,
        ))
        util.send_all(
            s,
            (
                (
                    'GET %s HTTP/1.1\r\n'
                    'Host: %s\r\n'
                    '\r\n'
                ) % (
                    url.path,
                    url.hostname,
                )
            ).encode('utf-8'),
        )

        rest = bytearray()

        #
        # Parse status line
        #
        status, rest = util.recv_line(s, rest)
        status_comps = status.split(' ', 2)
        if status_comps[0] != constants.HTTP_SIGNATURE:
            raise RuntimeError('Not HTTP protocol')
        if len(status_comps) != 3:
            raise RuntimeError('Incomplete HTTP protocol')

        signature, code, message = status_comps
        if code != '200':
            raise RuntimeError('HTTP failure %s: %s' % (code, message))

        #
        # Parse headers
        #
        content_length = None
        for i in range(constants.MAX_NUMBER_OF_HEADERS):
            line, rest = util.recv_line(s, rest)
            if not line:
                break

            name, value = util.parse_header(line)
            if name == 'Content-Length':
                content_length = int(value)
        else:
            raise RuntimeError('Too many headers')

        #
        # Write content
        #
        # Do not write output file directly
        # Create temporary file at same directory
        # Only if all OK we overwrite the file
        #
        fd, name = tempfile.mkstemp(dir=os.path.dirname(args.output))
        try:
            with os.fdopen(fd, 'wb') as f:
                if content_length is None:
                    # Fast track, no content length
                    # Recv until disconnect
                    f.write(rest)
                    while True:
                        buf = s.recv(constants.BLOCK_SIZE)
                        if not buf:
                            break
                        f.write(buf)
                else:
                    # Safe track, we have content length
                    # Recv excacly what requested.
                    left_to_read = content_length
                    while left_to_read > 0:
                        if not rest:
                            t = s.recv(constants.BLOCK_SIZE)
                            if not t:
                                raise RuntimeError(
                                    'Disconnected while waiting for content'
                                )
                            rest += t
                        buf, rest = rest[:left_to_read], rest[left_to_read:]
                        f.write(buf)
                        left_to_read -= len(buf)

            # Commit
            os.rename(name, args.output)
            name = None
        finally:
            if name is not None:
                try:
                    os.remove(name)
                except Exception:
                    print("Cannot remove temp file '%s'" % name)


if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
