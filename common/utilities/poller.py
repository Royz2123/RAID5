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
        for fd, event in self._events.keys():
            if self._events[fd] & (select.POLLHUP | select.POLLERR):
                xlist.append(fd)
            if self._events[fd] & select.POLLIN:
                rlist.append(fd)
            if self._events[fd] & select.POLLOUT:
                wlist.append(fd)

        # asynchronously recv which fd's need handling
        r, w, x = select.select(rlist, wlist, xlist, timeout)

        # arrange format to fit AsyncServer
        poll_dict = {}
        for ready_obj in r + w + x:
            # start be setting the fileno to no events
            poll_dict[ready_obj.fileno()] = 0

            # update events recvd from select
            if ready_obj in r:
                poll_dict[ready_obj.fileno()] |= select.POLLIN
            if ready_obj in w:
                poll_dict[ready_obj.fileno()] |= select.POLLOUT
            if ready_obj in x:
                poll_dict[ready_obj.fileno()] |= select.POLLERR
        # returns a list of tuples (fd, events)
        return poll_dict.items()
