# -*- coding: utf-8 -*-
import select
import time

from common.utilities import constants

class Poller():
    def __init__(self):
        self._poller = select.poll()

    def register(self, fd, event):
        self._poller.register(fd, event)

    def poll(self, timeout):
        return self._poller.poll(timeout)


class Select():
    def __init__(self):
        self._events = {}

    def register(self, fd, event):
        # if events are added one at a time we need |=
        if fd not in self._events.keys():
            self._events[fd] = 0
        self._events[fd] |= event

    def poll(self, timeout):
        # set the relevant lists to events we wish listened to
        rlist, wlist, xlist = [], [], []
        for fd, event in self._events.items():
            if self._events[fd] & (constants.POLLHUP | constants.POLLERR):
                xlist.append(fd)
            if self._events[fd] & constants.POLLIN:
                rlist.append(fd)
            if self._events[fd] & constants.POLLOUT:
                wlist.append(fd)

        # asynchronously recv which fd's need handling
        # As opposed to poll timeout, select timeout needs to be in seconds
        r, w, x = select.select(rlist, wlist, xlist, float(timeout)/1000)

        # arrange format to fit AsyncServer
        # loop through the set of file descriptors
        event_lst = []
        for ready_fd in set(r + w + x):
            # start be setting the fileno to no events
            event = 0

            # update events recvd from select
            if ready_fd in r:
                event |= constants.POLLIN
            if ready_fd in w:
                event |= constants.POLLOUT
            if ready_fd in x:
                event |= constants.POLLERR

            event_lst.append((ready_fd, event))
        # returns a list of tuples (fd, events)
        print event_lst
        return event_lst
