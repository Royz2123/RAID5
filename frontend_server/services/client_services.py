# -*- coding: utf-8 -*-
import errno
import logging
import os
import socket
import traceback

from common.services import base_service

class ClientService(base_service.BaseService):
    def __init__(self, entry):
        base_service.BaseService.__init__(self, [])

    @staticmethod
    def get_name():
        return "/client_service"

    def handle_content(self, entry, content):
        entry.client_update["content"] += content

    def before_terminate(self, entry):
        entry.client_update["finished"] = True
