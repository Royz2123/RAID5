# -*- coding: utf-8 -*-
import argparse
import ConfigParser
import logging
import os
import traceback

from common.utilities import async_server
from common.utilities import config_util
from common.utilities import poller
from common.utilities import constants

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
        default=constants.DEFAULT_BASE_DIRECTORY,
        help='Base directory to search files in, default: %(default)s',
    )
    parser.add_argument(
        '--poll-timeout',
        type=int,
        default=constants.DEFAULT_FRONTEND_POLL_TIMEOUT,
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
        '--log-file',
        type=str,
        default=None,
    )
    parser.add_argument(
        '--config-file',
        type=str,
        required=True,
    )
    parser.add_argument(
        '--daemon',
        type=bool,
        default=False,
    )
    args = parser.parse_args()
    args.base = os.path.normpath(os.path.realpath(args.base))
    return args


def main():
    #parse args
    args = parse_args()
    #parse the config file
    config_sections = config_util.parse_config(args.config_file)

    #delete the previous log
    try:
        os.remove(args.log_file)
    except:
        pass
    logging.basicConfig(filename=args.log_file, level=logging.DEBUG)

    #create volumes out of volume_UUID's in config_file, might
    #be recreated
    volumes = {}
    for section, content in config_sections.items():
        if "volume" in section:
            volumes[content["volume_uuid"]] = {
                "volume_UUID" : content["volume_uuid"],
                "volume_state" : constants.UNINITIALIZED,
                "long_password" : content["long_password"],
                "disks" : {},
            }

    #handle daemon state
    if args.daemon:
        daemonize()

    #create opplication context from config_file and args
    application_context = {
        "bind_address" : args.bind_address,
        "bind_port" : args.bind_port,
        "base" : args.base,
        "poll_type" : POLL_TYPE[args.poll_type],
        "poll_timeout" : args.poll_timeout,
        "max_connections" : args.max_connections,
        "max_buffer" : args.max_buffer,
        "server_type" : constants.FRONTEND_SERVER,
        "volumes" : volumes,
        "available_disks" : {},
        "multicast_group" : config_sections["MulticastGroup"],
        "authentication" : config_sections["Authentication"],
        "config_file" : args.config_file,
    }
    server = async_server.AsyncServer(application_context)
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
