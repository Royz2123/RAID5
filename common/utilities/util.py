#!/usr/bin/python
## @package RAID5.common.utilities.util
# Module that defines many utilities for the project
#

import base64
import errno
import os
import random
import socket
import string
import time
import uuid

from common.utilities import constants

## Generates a multipurpose UUID as a string. Uses uuid4.
## @returns UUID (string) generated uuid
def generate_uuid():
    return str(uuid.uuid4())

## Generates a long password for communication with Block Device Server.
## @param size (optional) (int) size of the generated password
## @returns password (string) generated long password
def generate_password(size=constants.LONG_PASSWORD_LENGTH):
    return ''.join(
        [
            random.choice(string.ascii_letters + string.digits)
            for n in xrange(size)
        ]
    )

## Checks the Basic Authentication of an entry, returns if there has been a
## successful_login to the frontend by the user.
## @param entry (Pollable) pollable we're dealing with
## @returns successful_login (bool) returns if there has been a successful
## login
def check_user_login(entry):
    successful_login = False
    auth_content = extract_basic_auth_content(entry)
    if auth_content is not None:
        username, password = decode_authorization(auth_content)
        application_auth = entry.application_context["authentication"]
        successful_login = (
            username == application_auth["common_user"] and
            password == application_auth["common_password"]
        )
    return successful_login

## Checks the Basic Authentication of an entry, returns if there has been a
## successful login to the Block Device by the Frontend. checked with the
## long password that the Frontend provided.
## @param entry (Pollable) pollable we're dealing with
## @returns successful_login (bool) returns if there has been a successful
## login.
def check_frontend_login(entry):
    auth_content = extract_basic_auth_content(entry)
    if auth_content is not None:
        return (
            base64.b64decode(auth_content)
            == entry.application_context["authentication"]["long_password"]
        )
    return False

## Extracts the Basic Authentication authorization content.
## @param entry (Pollable) pollable we're dealing with.
## @returns auth_content (string) if exists, returns the authorization
## content, otherwise None
def extract_basic_auth_content(entry):
    if "Authorization" in entry.request_context["headers"].keys():
        auth_type, auth_content = entry.request_context["headers"][
            "Authorization"
        ].split(" ", 2)
        if auth_type == "Basic":
            return auth_content.strip(" ")
    return None

## Decodes the convention of Basic Authentication using base64.
## @param auth_content (string) auth_content recieved.
## @returns decode_content (tuple) of username, password.
def decode_authorization(auth_content):
    return tuple(base64.b64decode(auth_content).split(':', 1))

## Encodes the convention of Basic Authentication using base64.
## @param username (string) username of the user.
## @param password (string) password of the user.
## @returns encoded_content (string) of username:password.
def encode_authorization(username, password):
    return base64.b64encode("%s:%s" % (username, password))

## Returns a dict of only the initialized volumes.
## @param volumes (dict) dictionary of all the volumes in the system.
## @returns initialized_volumes (dict) initialized subset of the volumes.
def initialized_volumes(volumes):
    init_volumes = {}
    for volume_UUID, volume in volumes.items():
        if volume["volume_state"] == constants.INITIALIZED:
            init_volumes[volume_UUID] = volume
    return init_volumes

## Returns the disk_UUID of a specific disk num.
## @param disks (dict) dictionary of all the disks.
## @param disk_num (int) disk_num we are looking for.
## @returns disk_UUID (string) the disk_UUID of the given disk_num.
def get_disk_UUID_by_num(disks, disk_num):
    for disk_UUID, disk in disks.items():
        if disk["disk_num"] == disk_num:
            return disk_UUID
    raise RuntimeError("Disk not found by disk num")

## Recieves a dict of disks and seperates into two subsets:
## onlines and offlines.
## @param disks (dict) dictionary of all the disks.
## @returns online_disks, offline_disks (tuple) returns two subsets of all
## the disks.
def sort_disks(disks):
    online_disks, offline_disks = {}, {}
    for disk_UUID, disk in disks.items():
        if disk["state"] == constants.ONLINE:
            online_disks[disk_UUID] = disk
        else:
            offline_disks[disk_UUID] = disk
    return online_disks, offline_disks

## Converts a string address to tuple
## @param address (string) address as address:port
## @returns address (tuple) returns (address, port)
def make_address(address):
    try:
        address, port = address.split(constants.ADDRESS_SEPERATOR)
        return (str(address), int(port))
    except BaseException:
        return False

## Makes a tuple address printable
## @param address (tuple) address as (address, port)
## @returns printable_address (string) returns "address:port"
def printable_address(address):
    return "%s%s%s" % (
        address[0],
        constants.ADDRESS_SEPERATOR,
        address[1],
    )

## Writes a buf to a file.
## @param file descriptor (int) open file for writing to which we are writing.
## @param buf (string) buf to write into file.
def write(fd, buf):
    while buf:
        buf = buf[os.write(fd, buf):]

## Reads from a file a certain size
## @param file descriptor (int) open file for reading from which we are
## reading
## @param max_buf (int) max_siz we are willing to read
## @returns file_content (string) file content of size up to max_buffer
def read(fd, max_buffer):
    ret = ""
    while True:
        buf = os.read(fd, max_buffer - len(ret))
        if buf == "":
            break
        ret += buf
    return ret


## Parse a header from a HTTP request or response
## @param line (string) unparsed header line
## @returns parsed_header (tuple) tuple of the header:
## header name, header content
def parse_header(line):
    SEP = ':'
    n = line.find(SEP)
    if n == -1:
        raise RuntimeError('Invalid header received')
    return line[:n].rstrip(), line[n + len(SEP):].lstrip()


# Important Error classes

## Disconnect Error. called when a socket has disconnected ungraceully.
## Inherits from RuntimeError.
class Disconnect(RuntimeError):

    ## Constructor for Disconnect
    ## @param desc (optional) (string) string descrbing the disconnection
    def __init__(self, desc="Disconnect"):
        super(Disconnect, self).__init__(desc)

## InvalidArguments Error.
## Called when recieved invalid arguments for a request from a service.
## Inherits from RuntimeError.
class InvalidArguments(RuntimeError):

    ## Constructor for InvalidArguments.
    ## @param desc (optional) (string) string descrbing the invalid arguments
    def __init__(self, desc="Bad Arguments"):
        super(InvalidArguments, self).__init__(desc)

## DiskRefused Error. called when a disk server is offline.
## Inherits from RuntimeError.
class DiskRefused(RuntimeError):

    ## Constructor for DiskRefused.
    ## @param disk_UUID (string) faulty disk_UUID
    ## @param desc (optional) (string) string descrbing the refused connection
    def __init__(self, disk_UUID, desc="Disk Refused to connect"):
        super(DiskRefused, self).__init__(desc)

        ## Disk UUID
        self._disk_UUID = disk_UUID

    ## Disk UUID property
    ## @returns disk_UUID (string) returns the faulty disk UUID
    @property
    def disk_UUID(self):
        return self._disk_UUID
