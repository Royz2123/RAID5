# -*- coding: utf-8 -*-
import argparse
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import select
import sys
import traceback

from http.common.utilities import poller
from http.common.utilities import constants
from http.frontend_server import front_server

#files
NEW_FILE = os.devnull
NEW_WORKING_DIRECTORY = "/"
LOG_FILE = "log"

POLL_TYPE = {
    "poll" : poller.Poller,
    "select" : poller.Select
}

def parse_args():
    """Parse program argument."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--bind-address',
        default=constants.DEFAULT_HTTP_ADDRESS,
        help='Bind address, default: %(default)s',
    )
    parser.add_argument(
        '--bind-port',
        default=constants.DEFAULT_FRONTEND_HTTP_PORT,
        type=int,
        help='Bind port, default: %(default)s',
    )
    parser.add_argument(
        '--base',
        default='.',
        help='Base directory to search files in, default: %(default)s',
    )
    parser.add_argument(
        '--poll-timeout',
        type=int,
        default=1000,
    )
    parser.add_argument(
        '--poll-type',
        choices=POLL_TYPE.keys(),
        default=sorted(POLL_TYPE.keys())[0],
        help='poll or select, default: poll'
    )
    parser.add_argument(
        '--max-buffer',
        type=int,
        default=constants.BLOCK_SIZE,
    )
    parser.add_argument(
        '--max-connections',
        type=int,
        default=1000,
    )
    parser.add_argument(
        '--disks',
        help="disks: address1,port1 address2,port2 ...",
        type=disk,
        nargs='+'
    )
    parser.add_argument(
        '--log-file',
        type=int,
        default=None,
    )
    args = parser.parse_args()
    args.base = os.path.normpath(os.path.realpath(args.base))
    return args


def disk(d):
    try:
        address, port = d.split(',')
        return str(address), int(port)
    except:
        raise argparse.ArgumentTypeError("Disks must be (address, port)")


def main():
    args = parse_args()

    #create disk list of dicts, start them all as offline
    disks = []
    for disk_address in args.disks:
        disks.append({
            "address" : disk_address,
            "UUID" : "",
            "level" : "",
            "state" : constants.OFFLINE
        })

    #delete the previous log
    try:
        os.remove(args.log_file)
    except:
        pass

    logging.basicConfig(filename=args.log_file, level=logging.DEBUG)

    #if args.daemon:
    #    daemonize()
    application_context = {
        "bind_address" : args.bind_address,
        "bind_port" : args.bind_port,
        "base" : args.base,
        "poll_type" : POLL_TYPE[args.poll_type],
        "poll_timeout" : args.poll_timeout,
        "max_connections" : args.max_connections,
        "max_buffer" : args.max_buffer,
        "server_type" : constants.FRONTEND_SERVER,
        "disks" : disks
    }
    server = front_server.FrontServer(application_context)
    server.run()


def daemonize():
    child = os.fork()

    if child != 0:
        os._exit(0)

    #first close all of parents fds
    os.closerange(
        NUMBER_OF_STANDARD_FILES,
        resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    )

    #redirect standards
    try:
        new_fd = os.open(NEW_FILE, os.O_RDWR)
        for standard_fd in range(NUMBER_OF_STANDARD_FILES + 1):
            os.dup2(new_fd, standard_fd)
    finally:
        os.close(new_fd)

    os.chdir(NEW_WORKING_DIRECTORY)

    signal.signal(signal.SIGINT|signal.SIGTERM, exit)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)


if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
