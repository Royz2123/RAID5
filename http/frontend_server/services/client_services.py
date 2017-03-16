# -*- coding: utf-8 -*-
import errno
import logging
import os
import socket
import traceback

from http.common.services import base_service

class BDSReadClientService(base_service.BaseService):
    def __init__(self):
        base_service.BaseService.__init__(self, [])

    def handle_content(self, entry, content):
        entry.client_update["content"] += content

    def before_terminate(self, entry):
        entry.client_update["finished_block"] = True


class BDSWriteClientService(base_service.BaseService):
    def __init__(self):
        base_service.BaseService.__init__(self, [])

    def before_terminate(self, entry):
        entry.client_update["finished_block"] = True


SERVICES = {
    "/getblock" : BDSReadClientService,
    "/setblock" : BDSWriteClientService
}
