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
        # timeout needs to be in seconds for select
        r, w, x = select.select(rlist, wlist, xlist, float(timeout)/1000)

        # arrange format to fit AsyncServer
        # loop through the set of file descriptors
        poll_dict = {}
        for ready_fd in set(r + w + x):
            # start be setting the fileno to no events
            poll_dict[ready_fd] = 0

            # update events recvd from select
            if ready_fd in r:
                poll_dict[ready_fd] |= constants.POLLIN
                print "1"
            if ready_fd in w:
                poll_dict[ready_fd] |= constants.POLLOUT
                print "2"
            if ready_fd in x:
                poll_dict[ready_fd] |= constants.POLLERR
                print '3'

            print ready_fd, poll_dict[ready_fd]
        # returns a list of tuples (fd, events)
        print poll_dict
        return poll_dict.items()
