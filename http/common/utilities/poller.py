# -*- coding: utf-8 -*-
import select


class Poller():
    def __init__(self):
        self._poller = select.poll()

    def register(self, fd, event):
        self._poller.register(fd, event)

    def poll(self, timeout):
        return self._poller.poll(timeout)


class Select():
    def __init__(self, pollables, max_connections, max_buffer):
        self._poller = select.select()

    def poll(self, timeout):
        pass
