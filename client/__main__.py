#!/usr/bin/python
import argparse
import contextlib
import logging
import socket

from ..common.utilities import constants
from ..common.utilities import util

DATA_TO_SEND = "hello this is a nice data"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dst-address",
        default="0.0.0.0",
        help="Server bind address. Default: %(default)s",
    )
    parser.add_argument(
        "--dst-port",
        type=int,
        default=8080,
        help="Initial server bind port. Default: %(default)s",
    )
    parser.add_argument(
        "--action",
        choices=["setblock", "getblock"],
        default="getblock",
        help="Whether to read or write from block device",
    )
    parser.add_argument(
        "--block",
        type=int,
        default=0,
        help="Which block to read/write from",
    )
    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    logging.basicConfig(filename=None, level=logging.DEBUG)

    DATA_TO_SEND = ""
    if args.action == "setblock":
        util.write(constants.STANDARD_OUTPUT, "ENTER DATA_TO_SEND:\n")
        DATA_TO_SEND = util.read(constants.STANDARD_INPUT, 2)

    with contextlib.closing(
        socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    ) as s:
        s.connect((args.dst_address, args.dst_port))
        s.settimeout(1)
        cmd = "GET /%s?blocknum=%d %s\r\n" % (
            args.action,
            args.block,
            constants.HTTP_SIGNATURE
        )
        if args.action == "getblock":
            cmd += "\r\n"
        if args.action == "setblock":
            cmd += "Content-Length: %s\r\n\r\n" % (len(DATA_TO_SEND))

        util.send_all(s, cmd)
        util.send_all(s, DATA_TO_SEND)

        # Wait for answer
        data = s.recv(constants.BLOCK_SIZE)
        while data:
            logging.debug(data)
            data = s.recv(constants.BLOCK_SIZE)


if __name__ == "__main__":
    main()
