# -*- coding: utf-8 -*-
import contextlib
import datetime
import errno
import fcntl
import logging
import os
import socket
import time
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
        self._fields = {}
        self._state = FileFormService.START_STATE

        self._fd = None
        self._filename = None
        self._arg_name = None

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
        self._arg_name = None
        disposition_fields = headers["Content-Disposition"].replace(" ", "")
        disposition_fields = disposition_fields.split(";")[1:]

        for field in disposition_fields:
            name, info = field.split('=', 1)
            #the info part is surrounded by parenthesies
            info = info[1:-1]

            if name == "filename":
                self._filename = info
                self._fd = os.open(
                    constants.TMP_FILE_NAME,
                    os.O_RDWR | os.O_CREAT,
                    0o666
                )
            elif name == "name":
                self._arg_name = info
                self._args[info] = [""]
        return True

    def end_boundary(self):
        return "%s--%s--%s" % (
            constants.CRLF_BIN,
            self._boundary,
            constants.CRLF_BIN
        )

    def mid_boundary(self):
        return "%s--%s%s" % (
            constants.CRLF_BIN,
            self._boundary,
            constants.CRLF_BIN
        )

    def content_state(self):
        #first we must check if there are any more mid - boundaries
        if self._content.find(self.mid_boundary()) != -1:
            buf = self._content.split(self.mid_boundary(), 1)[0]
            next_state = 1
        elif self._content.find(self.end_boundary()) != -1:
            buf = self._content.split(self.end_boundary(), 1)[0]
            next_state = 2
        else:
            buf = self._content
            next_state = 0

        if self._filename is not None:
            self.file_handle(buf, next_state)
        else:
            self.arg_handle(buf, next_state)
        self._content = self._content[len(buf):]

        if next_state == 1:
            self._content = self._content.split(self.mid_boundary(), 1)[1]


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
            traceback.print_exc()
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

    def arg_handle(self, arg, next_state):
        self._args[self._arg_name][0] += buf


    def file_handle(self, buf, next_state):
        while buf:
            buf = buf[os.write(self._fd, buf):]

        self._content = buf + self._content

        if next_state:
            os.rename(
                constants.TMP_FILE_NAME,
                os.path.normpath(self._filename)
            )
            os.close(self._fd)


class ReadFromDiskService(base_service.BaseService):
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    def __init__(self, entry, socket_data, args):
        base_service.BaseService.__init__(
            self,
            ["Content-Type"],
            ["disk", "firstblock", "blocks"],
            args
        )
        self._disks = entry.application_context["disks"]
        self._socket_data = socket_data

        self._block_mode = ReadFromDiskService.REGULAR
        self._current_block = None
        self._current_phy_disk = None

        self._client_updates = []
        self._client_contexts = []
        self.reset_client_updates()
        self.reset_client_contexts()

    def reset_client_updates(self):
        self._client_updates = []
        for disk_address in self._disks:
            self._client_updates.append(
                {
                    "finished_block" : False,
                    "status" : "",
                    "content" : ""
                }
            )

    def reset_client_contexts(self):
        self._client_contexts = []
        for disknum in range(len(self._disks)):
            self._client_contexts.append(
                {
                    "blocknum" : self._current_block,
                    "disknum" : disknum,
                    "disk_address" : self._disks[disknum],
                    "service" : "/getblock"
                }
            )

    @property
    def client_updates(self):
        return self._client_updates

    @client_updates.setter
    def client_updates(self, c_u):
        self._client_updates = c_u

    @property
    def client_contexts(self):
        return self._client_contexts

    @client_contexts.setter
    def client_contexts(self, c_c):
        self._client_contexts = c_c

    def on_finish(self, entry):
        if self._block_mode == ReadFromDiskService.RECONSTRUCT:
            for client_update, disknum in (
                self._client_updates,
                range(len(self._disks))
            ):
                if (
                    disknum != self._current_phy_disk
                    and not client_update["finished_block"]
                ):
                    return

        #if we have a pending block, send it back to client
        #Get ready for next block (if there is)
        #TODO: Too much in response_content
        if self.update_block(entry):
            self._current_block += 1
        entry.state = constants.SEND_CONTENT_STATE

    def before_response_status(self, entry):
        #could check on how many are active...
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

        self._current_phy_disk = DiskUtil.get_physical_disk_num(
            self._disks,
            int(self._args["disk"][0]),
            self._current_block
        )
        self.reset_client_updates()
        self.reset_client_contexts()
        entry.state = constants.SLEEPING_STATE

        try:
            self._block_mode = ReadFromDiskService.REGULAR
            DiskUtil.add_bds_client(
                entry,
                self._client_contexts[self._current_phy_disk],
                self._client_updates[self._current_phy_disk],
                self._socket_data
            )
        except socket.error as e:
            #probably got an error when trying to reach a certain BDS
            #ServerSocket. We shall try to get the data from the rest of
            #the disks. Otherwise, two disks are down and theres nothing
            #we can do
            logging.debug(
                "%s:\t Couldn't connect to one of the BDSServers, %s: %s" % (
                    entry,
                    self._current_phy_disk,
                    e
                )
            )

            try:
                self._block_mode = ReadFromDiskService.RECONSTRUCT
                for phy_disknum in range(len(self._disks)):
                    if phy_disknum == self._current_phy_disk:
                        pass
                    DiskUtil.add_bds_client(
                        entry,
                        self._client_contexts[phy_disknum],
                        self._client_updates[phy_disknum],
                        self._socket_data
                    )
            except socket.error as e:
                #Got another bad connection (Connection refused most likely)
                logging.error(
                    (
                        "%s:\t Couldn't connect to two of the"
                         + "BDSServers, giving up: %s"
                    ) % (
                        entry,
                        e
                    )
                )
                return True
        return False

    #woke up from sleeping mode, checking if got required blocks
    #returns boolean if block was recieved ok
    def update_block(self, entry):
        #regular block update, check physical disk data
        if (
            self._block_mode == ReadFromDiskService.REGULAR
            and self._client_updates[self._current_phy_disk]["status"] == "200"
        ):
            self._response_content += (
                self._client_updates[self._current_phy_disk]["content"]
            )
            return True

        #reconstruct block update, check everyone apart from physical disk
        elif self._block_mode == ReadFromDiskService.RECONSTRUCT:
            blocks = []
            for client, disknum in (
                self._client_updates,
                range(len(self._client_updates))
            ):
                if (
                    disknum != self._current_phy_disk
                    and client["status"] != "200"
                ):
                    #need to decide what to do, overall this is error
                    raise RuntimeError("Problem with one of the disks")

                blocks.append[client["content"]]
            self._response_content += DiskUtil.compute_missing_block(blocks)
            return True

        return False




class WriteToDiskService(FileFormService):
    (
        REGULAR,
        RECONSTRUCT
    ) = range(2)

    (
        READ_STATE,
        WRITE_STATE
    ) = range(2)

    def __init__(self, entry, socket_data, args):
        FileFormService.__init__(self)
        self._disks = entry.application_context["disks"]
        self._entry = entry
        self._socket_data = socket_data

        self._rest_of_data = ""
        self._finished_data = True

        self._block_mode = WriteToDiskService.REGULAR
        self._block_state = WriteToDiskService.READ_STATE

        self._block_data = ""
        self._current_block = None
        self._current_phy_disk = None
        self._current_phy_parity_disk = None

        self._client_updates = []
        self._client_contexts = []
        self.reset_client_updates()
        self.reset_client_contexts()

    def reset_client_updates(self):
        self._client_updates = []
        for disk in self._disks:
            self._client_updates.append(
                {
                    "finished_block" : False,
                    "content" : "",
                    "status" : "",
                }
            )

    def reset_client_contexts(self):
        self._client_contexts = []
        for disknum in range(len(self._disks)):
            self._client_contexts.append(
                {
                    "blocknum" : self._current_block,
                    "disknum" : disknum,
                    "disk_address" : self._disks[disknum],
                    "service" : "/setblock",
                    "content" : "",
                }
            )

    @property
    def client_updates(self):
        return self._client_updates

    @client_updates.setter
    def client_updates(self, c_u):
        self._client_updates = c_u

    @property
    def client_contexts(self):
        return self._client_contexts

    @client_contexts.setter
    def client_contexts(self, c_c):
        self._client_contexts = c_c

    #override arg and file handle from FileFormService
    def arg_handle(self, buf, next_state):
        self._args[self._arg_name][0] += buf
        if next_state and self._arg_name == "firstblock":
            self._current_block = int(self._args[self._arg_name][0])


    def file_handle(self, buf, next_state):
        self._rest_of_data += buf
        self._finished_data = next_state

        if (
            len(self._rest_of_data) >= constants.BLOCK_SIZE
            or (self._finished_data and self._rest_of_data != "")
        ):
            self._block_data, self._rest_of_data = (
                self._rest_of_data[:constants.BLOCK_SIZE],
                self._rest_of_data[constants.BLOCK_SIZE:]
            )
            self._block_data = self._block_data.ljust(constants.BLOCK_SIZE, chr(0))
            self.handle_block()

    def on_finish(self, entry):
        if self._block_mode == WriteToDiskService.REGULAR:
            if (
                not self._client_updates[self._current_phy_disk]["finished_block"]
                or not self._client_updates[self._current_phy_parity_disk]["finished_block"]
            ):
                return

            #check responses from server
            if (
                self._client_updates[self._current_phy_disk]["status"] != "200"
                or self._client_updates[self._current_phy_parity_disk]["status"] != "200"
            ):
                raise RuntimeError("Got an error from BDS Server")

            if self._block_state == WriteToDiskService.READ_STATE:
                self._block_state = WriteToDiskService.WRITE_STATE
                self.handle_block()
                return
            elif (
                self._block_state == WriteToDiskService.WRITE_STATE
                and (
                    len(self._rest_of_data) >= constants.BLOCK_SIZE
                    or (self._finished_data and self._rest_of_data != "")
                )
            ):
                self._block_state = WriteToDiskService.READ_STATE
                self._block_data, self._rest_of_data = (
                    self._rest_of_data[:constants.BLOCK_SIZE],
                    self._rest_of_data[constants.BLOCK_SIZE:]
                )
                self._current_block += 1
                self.handle_block()
                return
            print "finished"

        '''
        elif self._block_mode == WriteToDiskService.RECONSTRUCT:
            for client_update, disknum in (
                self._client_updates,
                range(len(self._disks))
            ):
                if (
                    disknum != self._current_phy_disk
                    and not client_update["finished_block"]
                ):
                    return
        '''
        #if we reached here, we are ready to continue
        if not self._finished_data:
            entry.state = constants.GET_CONTENT_STATE
        else:
            entry.state = constants.SEND_STATUS_STATE
            
    def before_response_status(self, entry):
        self._response_headers = {
            "Content-Length" : "0"
        }
        return True

    '''
    #woke up from sleeping mode, checking if got required blocks
    #returns boolean if block was recieved ok
    def check_response(self, entry):
        #regular block update, check physical disk data
        if (
            self._block_mode == ReadFromDiskService.REGULAR
            and self._client_updates[self._current_phy_disk]["status"] == "200"
        ):
            self._response_content += (
                self._client_updates[self._current_phy_disk]["content"]
            )
            return True

        #reconstruct block update, check everyone apart from physical disk
        elif self._block_mode == ReadFromDiskService.RECONSTRUCT:
            blocks = []
            for client, disknum in (
                self._client_updates,
                range(len(self._client_updates))
            ):
                if (
                    disknum != self._current_phy_disk
                    and client["status"] != "200"
                ):
                    #need to decide what to do, overall this is error
                    raise RuntimeError("Problem with one of the disks")

                blocks.append[client["content"]]
            self._response_content += DiskUtil.compute_missing_block(blocks)
            return True

        return False
    '''

    def handle_block(self):
        self._current_phy_disk = DiskUtil.get_physical_disk_num(
            self._disks,
            int(self._args["disk"][0]),
            self._current_block
        )
        self._current_phy_parity_disk = DiskUtil.get_parity_disk_num(
            self._disks,
            self._current_block
        )
        self.reset_client_contexts()
        self._entry.state = constants.SLEEPING_STATE
        #first try writing the block regularly
        try:
            #step 1 - get current_block and parity block contents
            #step 2 - calculate new blocks to write
            self._block_mode = WriteToDiskService.REGULAR

            if self._block_state == WriteToDiskService.READ_STATE:
                service = "/getblock"
            else:
                service = "/setblock"

                #ALGORITHM:
                #Lets say:
                #x0 - contents of desired block before update
                #x1 - contents of desired block after update
                #p0 - contents of parity block before update
                #p1 - contents of parity block after update

                #then:
                #p1 = p0 XOR (x1 XOR x0)

                x0 = self._client_updates[self._current_phy_disk]["content"]
                x1 = self._block_data
                p0 = self._client_updates[self._current_phy_parity_disk]["content"]
                p1 = DiskUtil.compute_missing_block([x0, x1, p0])

                self._client_contexts[self._current_phy_disk]["content"] = x1
                self._client_contexts[self._current_phy_parity_disk]["content"] = p1

            self.reset_client_updates()

            for disk in (
                self._current_phy_disk,
                self._current_phy_parity_disk
            ):
                self._client_contexts[disk]["service"] = service

                DiskUtil.add_bds_client(
                    self._entry,
                    self._client_contexts[disk],
                    self._client_updates[disk],
                    self._socket_data
                )

        except socket.error as e:
            #connection refused of some sorts, must still try to write
            #step 1 - get all other non-parity blocks
            #step 2 - XOR and write in parity
            try:
                self._block_mode = WriteToDiskService.RECONSTRUCT


            except socket.error as e:
                #nothing to do
                logging.error(
                    (
                        "%s:\t Couldn't connect to two of the"
                         + "BDSServers, giving up: %s"
                    ) % (
                        entry,
                        e
                    )
                )
                return True




class DiskUtil():
    @staticmethod
    def add_bds_client(parent, client_context, client_update, socket_data):
        new_socket = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        new_socket.connect((client_context["disk_address"]))

        #set to non blocking
        fcntl.fcntl(
            new_socket.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(new_socket.fileno(), fcntl.F_GETFL) | os.O_NONBLOCK
        )

        #add to database, need to specify blocknum
        new_bds_client = bds_client_socket.BDSClientSocket(
            new_socket,
            client_context,
            client_update,
            parent
        )
        socket_data[new_socket.fileno()] = new_bds_client
        logging.debug(
            "%s :\t Added a new BDS client, %s"
            % (
                parent,
                new_bds_client
            )
        )

    @staticmethod
    def compute_missing_block(blocks):
        #compute the missing block using parity and XOR
        if blocks == []:
            return None
        new_block = blocks[0]
        for block in blocks[1:]:
            new_block = DiskUtil.xor_blocks(new_block, block)
        return new_block

    @staticmethod
    def xor_blocks(block1, block2):
        if len(block1) != len(block2):
            raise RuntimeError("Illegal Block Size")

        l1 = [ord(c) for c in list(block1)]
        l2 = [ord(c) for c in list(block2)]
        ans = []
        for i in range(len(l1)):
            ans.append(chr(l1[i] ^ l2[i]))
        return "".join(ans)

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
        return (len(disks) - blocknum % len(disks) - 1)

SERVICES = {
    "/clock": TimeService,
    "/mul" :  MulService,
    "/disk_read" : ReadFromDiskService,
    "/disk_write" : WriteToDiskService
}


'''
    references
    "/secret": {"name": secret, "headers": ["Authorization"]},
    "/cookie": {"name": cookie, "headers": ["Cookie"]},
    "/login": {"name": login, "headers": None},
    "/secret2": {"name": secret2, "headers": ["Cookie"]},
'''
