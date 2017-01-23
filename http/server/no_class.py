# -*- coding: utf-8 -*-
import argparse
import contextlib
import errno
import fcntl
import os
import socket
import select
import sys
import time
import traceback

from ..common import constants
from ..common import util

#files
NEW_FILE = os.devnull
NEW_WORKING_DIRECTORY = "/"
LOG_FILE = "log"

WAIT_TIME = 1
LISTEN_MODE, ACTIVE_MODE, CLOSING_MODE  = range(3)
REQUEST_STATE, HEADERS_STATE, CONTENT_STATE, REPLY_STATE = range(4)

MIME_MAPPING = {
    'html': 'text/html',
    'png': 'image/png',
    'txt': 'text/plain',
}

keep_running = True

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
    parser.add_argument(
        '--poll-timeout',
        type=int,
        default=1000,
    )
    parser.add_argument(
        '--max-buffer',
        type=int,
        default=1000,
    )
    parser.add_argument(
        '--max-connections',
        type=int,
        default=1000,
    )
    args = parser.parse_args()
    args.base = os.path.normpath(os.path.realpath(args.base))
    return args


def main():
    args = parse_args()
    log_fd = os.open(LOG_FILE, os.O_CREAT | os.O_WRONLY, 0o666)

    try:
        sl = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        fcntl.fcntl(
            sl.fileno(),
            fcntl.F_SETFL, fcntl.fcntl(sl.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK,
        )

        sl.bind((args.bind_address, args.bind_port))
        sl.listen(10)

        socket_data = {
            sl.fileno() : {
                "fd" : sl.fileno(),
                "mode" : LISTEN_MODE,
                "socket" : sl,
                "data_to_send" : "",
            }
        }

        status_sent = False

        global keep_running
        while socket_data and keep_running:
            close_all(socket_data)
            poller = create_poller(socket_data, args.max_connections, args.max_buffer)

            #handle events from poller
            for curr_fd, event in poller.poll(args.poll_timeout):
                entry = socket_data[curr_fd]

                try:
                    #socket has close
                    if event & (select.POLLHUP | select.POLLERR):
                        raise RuntimeError()

                    #socket recvd data
                    if event & select.POLLIN:
                        recv_handler(entry, socket_data, args.base)

                    #socket has send
                    if event & select.POLLOUT:
                        send_handler(entry, args.max_buffer)

                except Disconnect as e:
                    set_closing(entry, socket_data)

                except Exception as e:
                    write(log_fd, e)
                    #traceback.print_exc(file = log_fd)
                    set_closing(entry, socket_data)
    except Exception as e:
        raise e

    try:
        sl.close()
    except OSError as e:
        pass


#poller:
def create_poller(socket_data, max_connections, max_buffer):
    poller = select.poll()

    for fd, entry in socket_data.items():
        event = select.POLLERR

        if (
            entry["mode"] == LISTEN_MODE and
            len(socket_data) < max_connections
        ) or (
            entry["mode"] == ACTIVE_MODE and
            entry["state"] in range(CONTENT_STATE + 1) and
            len(entry["current_data"]) < max_buffer
        ):
            event |= select.POLLIN
        if (
            entry["mode"] == ACTIVE_MODE and
            entry["state"] == REPLY_STATE and
            entry["data_to_send"] != ""
        ):
            event |= select.POLLOUT

        poller.register(entry["fd"], event)
    return poller


#handlers:

#close handlers:
def set_closing(entry, socket_data):
    if entry["mode"] != LISTEN_MODE:
        entry["mode"] = CLOSING_MODE
    else:
        for fd, entry in socket_data.items():
            entry["mode"] = CLOSING_MODE

def close_all(socket_data):
    for fd, entry in socket_data.items():
        if (
            entry["mode"] == CLOSING_MODE and
            entry["data_to_send"] == ""
        ):
            close_handler(socket_data, entry)

def close_handler(socket_data, entry):
    entry["socket"].close()
    del socket_data[entry["fd"]]


#check_validity
def check_validity(entry, buf):
    if entry["state"] == REQUEST_STATE:
        req_comps = buf.split(' ', 2)
        if req_comps[2] != constants.HTTP_SIGNATURE:
            raise RuntimeError('Not HTTP protocol')
        if len(req_comps) != 3:
            raise RuntimeError('Incomplete HTTP protocol')

        method, uri, signature = req_comps
        if method != 'GET':
            raise RuntimeError(
                "HTTP unsupported method '%s'" % method
            )

        if not uri or uri[0] != '/' or '\\' in uri:
            raise RuntimeError("Invalid URI")

        entry["request"] = req_comps


#recv handler
def recv_handler(entry, socket_data, base):
    read = False                            #have we finished a stage?

    try:
        #STAGE0
        if entry["mode"] == LISTEN_MODE:
            new_socket, address = entry["socket"].accept()

            #set to non blocking
            fcntl.fcntl(
                new_socket.fileno(),
                fcntl.F_SETFL, fcntl.fcntl(new_socket.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK
            )

            #add to database
            socket_data[new_socket.fileno()] = {
                "fd" : new_socket.fileno(),
                "socket" : new_socket,
                "headers" : {},
                "current_data" : "",
                "data_to_send" : "",
                "file_name" : "",
                "mode" : ACTIVE_MODE,
                "state": REQUEST_STATE,
                "request" : "",
            }
            return

        #STATE1
        if entry["state"]  == REQUEST_STATE:
            #first we recv, until some point
            util.add_buf(entry)
            read = True

            index = entry["current_data"].find(constants.CRLF_BIN)
            if index == -1:
                return

            req, rest = (
                entry["current_data"][:index].decode('utf-8'),
                entry["current_data"][index + len(constants.CRLF_BIN):]
            )

            #next check validity
            try:
                check_validity(entry, req)
            except:
                #handle disconnections, other stuff..
                pass

            entry["file_name"] = os.path.normpath(
                '%s%s' % (
                    base,
                    os.path.normpath(entry["request"][1]),
                )
            )

            #finally move on to the next mode
            entry["state"] += 1                     #move on to the next mode
            entry["current_data"] = rest            #save the rest for next time

            #wanted headers:
            entry["headers"]["Content-Length"] = None

        #STAGE2
        if entry["state"] == HEADERS_STATE:
            if "" not in entry["current_data"].split(constants.CRLF_BIN):
                if read:
                    util.add_buf(entry)
                return

            #got all the headers, process them
            lines = entry["current_data"].split(constants.CRLF_BIN)
            for index in range(len(lines)):
                line = lines[index]

                if len(entry["headers"].items()) > constants.MAX_NUMBER_OF_HEADERS:
                    raise RuntimeError('Too many headers')

                if line == "":
                    entry["state"] += 1             #move on to the next mode
                    entry["current_data"] = constants.CRLF_BIN.join(
                        lines[index + 1:]
                    )
                    break

                k, v = util.parse_header(line)
                if k in entry["headers"].keys():
                    entry["headers"][k] = v

        #STAGE3
        if entry["state"] == CONTENT_STATE:
            if entry["headers"]["Content-Length"] is None:
                entry["state"] += 1                  #move on to the next mode

            else:
                content_length = int(entry["headers"]["Content-Length"])

                if not read and len(entry["current_data"]) < content_length:
                    read = True
                    util.add_buf(entry)

                if len(entry["current_data"]) > content_length:
                    raise RuntimeError("Too much content")
                elif len(entry["current_data"]) == content_length:
                    entry["state"] += 1               #move on to the next mode

        #STAGE4 - initialize
        if entry["state"] == REPLY_STATE:
            with open(entry["file_name"], 'rb') as f:
                entry["data_to_send"] = (
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
                                entry["file_name"]
                            )[1].lstrip('.'),
                            'application/octet-stream',
                        ),
                    )
                ).encode('utf-8')

    except IOError as e:
        traceback.print_exc()
        if not status_sent:
            if e.errno == errno.ENOENT:
                send_status(entry["socket"], 404, 'File Not Found', e)
            else:
                send_status(entry["socket"], 500, 'Internal Error', e)
    except Exception as e:
        traceback.print_exc()
        if not status_sent:
            send_status(entry["socket"], 500, 'Internal Error', e)


#send hander
def send_handler(entry, max_buffer):
    fd = None
    try:
        fd = os.open(entry["file_name"], os.O_RDONLY, 0o666)

        while len(entry["data_to_send"]) < max_buffer:
            buf = os.read(fd, constants.BLOCK_SIZE)
            if not buf:
                entry["mode"] = CLOSING_MODE        #start closing the socket
                break
            entry["data_to_send"] += buf

    except socket.error, e:
        if e.errno != errno.EAGAIN and e.errno != errno.EWOULDBLOCK:
            raise
    finally:
        if fd is not None:
            os.close(fd)

    util.send_all(entry)


#Http:
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


class Disconnect(RuntimeError):
    def __init__(self):
        super(Disconnect, self).__init__("Disconnect")

if __name__ == '__main__':
    main()


# vim: expandtab tabstop=4 shiftwidth=4
