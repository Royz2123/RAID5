# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import traceback

from http.common.services import base_service
from http.common.utilities import constants
from http.common.utilities import util
from http.frontend_server.pollables import bds_client_socket

class GetFileService(base_service.BaseService):
    def __init__(self, filename):
        base_service.BaseService.__init__(self, [])
        self._filename = filename
        self._fd = None

    def before_response_status(self, entry):
        try:
            self._fd = os.open(self._filename, os.O_RDONLY, 0o666)
            self._response_headers = {
                "Content-Length" : os.fstat(self._fd).st_size,
                "Content-Type" : constants.MIME_MAPPING.get(
                    os.path.splitext(
                        self._filename
                    )[1].lstrip('.'),
                    'application/octet-stream',
                )
            }
        except IOError as e:
            if e.errno != errno.ENOENT:
                raise
            logging.error("%s :\t File not found " % entry)
            self._response_status = 404
        except Exception as e:
            logging.error("%s :\t %s " % (entry, e))
            self._response_status = 500

        return True

    def before_response_content(
        self,
        entry,
        max_buffer = constants.BLOCK_SIZE
    ):
        if self._response_status != 200:
            return True

        buf = ""
        try:
            while len(entry.data_to_send) < max_buffer:
                buf = os.read(self._fd, max_buffer)
                if not buf:
                    break
                self._response_content += buf

            if buf:
                return False
            os.close(self._fd)

        except Exception as e:
            if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            logging.debug(
                "%s :\t Still reading, current response size: %s "
                % (
                    entry,
                    len(self._response_content)
                )
            )
        return True


class TimeService(base_service.BaseService):
    def __init__(self):
        base_service.BaseService.__init__(self, [])
        #super(TimeService, self).__init__(self, [])

    def before_response_headers(self, entry):
        self._response_headers = {
            "Content-Length" : len(str(datetime.datetime.now())),
        }
        self._response_content = str(datetime.datetime.now())
        logging.debug(
            "%s :\t sending content: %s"
             % (
                entry,
                self._response_content
            )
        )
        return True


class MulService(base_service.BaseService):
    def __init__(self, args):
        base_service.BaseService.__init__(self, [], ["a", "b"], args)
        #super(MulService, self).__init__(self, [], ["a", "b"], args)

    def before_response_status(self, entry):
        if not self.check_args():
            self._response_status = 500

        self._response_content = str(
            int(self._args['a'][0]) *
            int(self._args['b'][0])
        )
        self._response_headers = {
            "Content-Length" : len(self._response_content)
        }
        logging.debug(
            "%s :\t sending content: %s"
             % (
                entry,
                self._response_content
            )
        )

class FileFormService(base_service.BaseService):
    (
        START_STATE,
        HEADERS_STATE,
        CONTENT_STATE,
        END_STATE,
    ) = range(4)

    def __init__(self):
        base_service.BaseService.__init__(self, ["Content-Type"])
        #super(FileFormService, self).__init__(self, ["Content-Type"])
        self._content = ""
        self._boundary = None
        self._state = FileFormService.START_STATE
        self._fd = None

    def before_content(self, entry):
        content_type = entry.request_context["headers"]["Content-Type"]
        if (
            content_type.find("multipart/form-data") == -1 or
            content_type.find("boundary") == -1
        ):
            raise RuntimeError("Bad Form Request")
        self._boundary = content_type.split("boundary=")[1]

    def start_state(self):
        if self._content.find("--%s" % self._boundary) == -1:
            return False
        self._content = self._content.split(
            "--%s%s" % (
                self._boundary,
                constants.CRLF_BIN
            ), 1
        )[1]
        return True

    def headers_state(self):
        lines = self._content.split(constants.CRLF_BIN)
        if "" not in lines:
            return False

        #got all the headers, process them
        headers = {}
        for index in range(len(lines)):
            line = lines[index]
            if line == "":
                self._content = constants.CRLF_BIN.join(lines[index + 1:])
                break

            k, v = util.parse_header(line)
            headers[k] = v

        if "Content-Disposition" not in headers.keys():
            raise RuntimeError("Missing content-disposition header")

        self._filename = None
        disposition_fields = headers["Content-Disposition"].split("; ")[1:]
        for field in disposition_fields:
            name, info = field.split('=', 1)

            if name == "filename":
                self._filename = info
        return True

    def end_boundary(self):
        return "--%s--%s" % (
            self._boundary,
            constants.CRLF_BIN
        )

    def mid_boundary(self):
        return "--%s%s" % (
            self._boundary,
            constants.CRLF_BIN
        )

    def content_state(self):
        if self._content.find(self.end_boundary()) != -1:
            buf = self._content.split(self.end_boundary(), 1)[0]
            next_state = 2
        elif self._content.find(self.mid_boundary()) != -1:
            buf = self._content.split(self.mid_boundary(), 1)[0]
            next_state = 1
        else:
            buf = self._content
            next_state = 0

        self._content = self._content[len(buf):]
        if self._filename is not None:
            try:
                while buf:
                    buf = buf[os.write(self._fd, buf):]
            except Exception as e:
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    raise
            finally:
                self._content = buf + self._content

        if next_state == 1 and buf == "":
            self._content = self._content.split(self.end_boundary(), 1)[1]

        if next_state:
            os.rename(
                constants.TMP_FILE_NAME,
                os.path.normpath(self._filename)
            )

        return next_state

    BOUNDARY_STATES = {
        START_STATE: {
            "function": start_state,
            "next": HEADERS_STATE,
        },
        HEADERS_STATE: {
            "function": headers_state,
            "next": CONTENT_STATE
        },
        CONTENT_STATE: {
            "function": content_state,
            "next": HEADERS_STATE,
        }
    }

    def handle_content(self, entry, content):
        try:
            self._fd = os.open(constants.TMP_FILE_NAME, os.O_RDWR | os.O_CREAT, 0o666)

            self._content += content
            while True:
                next_state = FileFormService.BOUNDARY_STATES[self._state]["function"](self)
                if next_state == 0:
                    return False
                elif (self._state == FileFormService.CONTENT_STATE and next_state == 2):
                    break
                self._state = FileFormService.BOUNDARY_STATES[self._state]["next"]

                logging.debug(
                    "%s :\t handling content, current state: %s"
                    % (
                        entry,
                        self._state
                    )
                )

        except Exception as e:
            logging.error("%s :\t %s" % (entry, e))
            self._response_status = 500
        return True

    def before_response_headers(self, entry):
        if self._response_status == 200:
            self._response_content = "File was uploaded successfully"
            self._response_headers = {
                "Content-Length" : len(self._response_content),
            }
            return True


class ReadFromDiskService(base_service.BaseService):
    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(
            self,
            ["Content-Type"],
            ["disk", "firstblock", "blocks"],
            args
        )
        self._client_update = {
            "status" : "",
            "content" : ""
        }
        self._disks = entry.application_context["disks"]
        self._socket_data = socket_data

    @property
    def client_update(self):
        return self._client_update

    @client_update.setter
    def client_update(self, c_u):
        self._client_update = c_u

    def on_finish(self, entry):
        entry.state = constants.SEND_CONTENT_STATE
        self._current_block += 1

    def before_response_headers(self, entry):
        self._response_headers = {
            "Content-Length" : (
                int(self._args["blocks"][0])
                * constants.BLOCK_SIZE
            )
        }
        self._current_block = int(self._args["firstblock"][0])
        return True

    def before_response_content(self, entry):
        #we shouldnt get here, but for now
        if entry.state == constants.SLEEPING_STATE:
            return False

        #check if there are no more blocks to send
        if (
            self._current_block
            == (
                int(self._args["firstblock"][0])
                + int(self._args["blocks"][0])
            )
        ):
            return True

        #if we have a pending block, send it back to client
        #TODO: Too much in response_content
        if self._client_update["status"] == "200 OK":
            self._response_content = self._client_update["content"]

        self._client_update = {
            "status" : "",
            "content" : ""
        }

        #get another block from BDS
        physical_disknum = DiskUtil.get_physical_disk_num(
            self._disks,
            int(self._args["disk"][0]),
            self._current_block
        )
        args = {
            "blocknum" : self._current_block
        }

        self.add_bds_client(entry, physical_disknum, self._current_block)
        entry.state = constants.SLEEPING_STATE


    def add_bds_client(self, entry, disknum, args):
        with contextlib.closing(
            socket.socket(
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
            )
        ) as new_socket:
            new_socket.connect((self._disks[disknum]))

            #set to non blocking
            fcntl.fcntl(
                new_socket.fileno(),
                fcntl.F_SETFL,
                fcntl.fcntl(new_socket.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK
            )

            #add to database, need to specify blocknum
            new_bds_client = bds_client_socket.BDSClientSocket(
                new_socket,
                constants.SEND_REQUEST_STATE,
                args,
                "/getblock",
                entry,
            )
            self._socket_data[new_socket.fileno()] = new_bds_client
            logging.debug(
                "%s :\t Added a new BDS client, %s"
                % (
                    self,
                    new_bds_client
                )
            )

class WriteToDiskService(base_service.BaseService):
    def __init__(self, entry, socket_data, disks, args):
        base_service.BaseService.__init__(self,
            ["Content-Type"],
            ["disk", "firstblock"],
            args
        )
        self._entry = entry
        self.disks = disks
        self._socket_data = socket_data




class DiskUtil():
    @staticmethod
    def get_physical_disk_num(disks, logic_disk_num, blocknum):
        if DiskUtil.get_parity_disk_num(disks, blocknum) > logic_disk_num:
            return logic_disk_num
        return logic_disk_num + 1

    @staticmethod
    def get_parity_disk_num(disks, blocknum):
        #The parity block (marked as pi) will be in cascading order,
        #for example, if len(disks) = 4 we will get the following division:
        #   |   a1  |   b1  |   c1  |   p1  |
        #   |   a2  |   b2  |   p2  |   c2  |
        #   |   a3  |   p3  |   b3  |   c3  |
        #   |   p4  |   a4  |   b4  |   c4  |
        #               ....
        return (len(disks) - blocknum % len(disks))

SERVICES = {
    "/clock": TimeService,
    "/mul" :  MulService,
    "/disk_read" : ReadFromDiskService,
}


'''
    references
    "/secret": {"name": secret, "headers": ["Authorization"]},
    "/cookie": {"name": cookie, "headers": ["Cookie"]},
    "/login": {"name": login, "headers": None},
    "/secret2": {"name": secret2, "headers": ["Cookie"]},
'''
