# -*- coding: utf-8 -*-
import errno
import logging
import os
import socket
import traceback

from http.common.services import base_service

class BDSReadClientService(base_service.BaseService):
    def __init__(self, entry):
        base_service.BaseService.__init__(self, [])

    @staticmethod
    def get_name():
        return "/requestblock"

    def handle_content(self, entry, content):
        entry.client_update["content"] += content

    def before_terminate(self, entry):
        entry.client_update["finished"] = True

class BDSGetFileService(base_service.BaseService):
    def __init__(self, entry):
        base_service.BaseService.__init__(self, [])

    @staticmethod
    def get_name():
        return "/getfile"

    def handle_content(self, entry, content):
        entry.client_update["content"] += content

    def before_terminate(self, entry):
        entry.client_update["finished"] = True

class BDSPostClientService(base_service.BaseService):
    def __init__(self, entry):
        base_service.BaseService.__init__(self, [])

    @staticmethod
    def get_name():
        return "/postform"

    def before_terminate(self, entry):
        entry.client_update["finished"] = True


class BDSWriteClientService(base_service.BaseService):
    def __init__(self, entry):
        base_service.BaseService.__init__(self, [])

    @staticmethod
    def get_name():
        return "/updateblock"

    def before_terminate(self, entry):
        entry.client_update["finished"] = True
