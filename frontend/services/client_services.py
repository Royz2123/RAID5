#!/usr/bin/python
## @package RAID5.frontend.services.client_services
## Module that defines the ClientService class, that updates responses from
## the Block Device Servers.
#

import errno
import logging
import os
import socket
import traceback

from common.services import base_service

## Simple Client Service class for all BDSClientSocket
class ClientService(base_service.BaseService):

    ## Constructor for the ClientService class
    def __init__(self, entry):
        super(ClientService, self).__init__()

    ## Name of the service
    # required by common.services.base_service.BaseService
    # @returns (str) service name
    @staticmethod
    def get_name():
        return "/client_service"

    ## Handling content service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @param content (string) content to handle from entry
    def handle_content(self, entry, content):
        entry.client_update["content"] += content

    ## Before pollable terminates service function
    ## @param entry (@ref common.pollables.pollable.Pollable) entry we belong
    ## to
    ## @returns finished (bool) returns true if finished
    def before_terminate(self, entry):
        entry.client_update["finished"] = True
