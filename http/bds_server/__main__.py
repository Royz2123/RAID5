# -*- coding: utf-8 -*-
import argparse
import logging
import os
import traceback

from http.common.utilities import async_server
from http.common.utilities import constants
from http.common.utilities import poller
from http.common.utilities import util

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
        default=constants.DEFAULT_BDS_HTTP_PORT,
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
        '--disk-num',
        type=str,
        default=0,
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default=None
    )
    args = parser.parse_args()
    args.base = os.path.normpath(os.path.realpath(args.base))
    return args

def main():
    args = parse_args()
    args.bind_port += int(args.disk_num)

    #delete the previous log
    try:
        if args.log_file is not None:
            os.remove(args.log_file)
    except:
        pass

    logging.basicConfig(filename=args.log_file, level=logging.DEBUG)

    #check that the disk file and dis info file is ok before running the server
    #create file if necessary
    try:
        disk_fd = os.open(
            "%s%s" % (constants.DISK_NAME, args.disk_num),
            os.O_RDONLY | os.O_CREAT,
            0o666
        )
        os.close(disk_fd)
    except Exception as e:
        logging.critical("BLOCK DEVICE STARTUP UNSUCCESSFUL:\t %s" % e)
        return

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
        "server_type" : constants.BLOCK_DEVICE_SERVER,
        "disk_name" : "%s%s" % (constants.DISK_NAME, args.disk_num),
        "disknum" : args.disk_num
    }
    server = async_server.AsyncServer(application_context)
    server.run()


def daemonize():
    child = os.fork()

    if child != 0:
        os._exit(0)

    #first close all of parents fds
    os.closerange(NUMBER_OF_STANDARD_FILES,resource.getrlimit( resource.RLIMIT_NOFILE)[1])

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
