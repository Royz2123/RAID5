#!/usr/bin/python
## @package RAID5.common.utilities.poller
# Module that defines two polling objects: Poller and Select
#

import select
import time

from common.utilities import constants

## Poller class for Asynchronous IO.
## This is the default poller, basically just a wrap class around the existing
## poll object, that implements the methods we need. Poller is for UNIX.
## The poll object polls the file descriptors it has regsitered for IO they
## get.
class Poller():

    ## Constructor for Poller. No params, creates a poll object on it's own
    def __init__(self):
        ## Polling object
        self._poller = select.poll()

    ## Register an event to the poller
    ## @param file descriptor (int) fd that wants to listen to the event
    ## @param event (event_mask) event(s) that need to be registered
    def register(self, fd, event):
        self._poller.register(fd, event)

    ## Poll the polling object - check for IO
    ## @param timeout (int) time (in miliseconds) until poller times out
    ## @returns events (dict) dict of events that have been recognized
    def poll(self, timeout):
        return self._poller.poll(timeout)

## Select class for Asynchronous IO.
## This is the second type of poller that calls the select call.
## It has the same methods as the poll object, implemented differently.
## Select works for both Windows and UNIX.
## The poll object polls the file descriptors it has regsitered for IO they
## get.
class Select():

    ## Constructor for Poller, No params.
    def __init__(self):
        ## events that are associated with each fd
        self._events = {}

    ## Register an event to the selecter
    ## @param file descriptor (int) fd that wants to listen to the event
    ## @param event (event_mask) event(s) that need to be registered
    def register(self, fd, event):
        # if events are added one at a time we need |=
        if fd not in self._events.keys():
            self._events[fd] = 0
        self._events[fd] |= event

    ## Poll the select polling object - check for IO.
    ## Need to format events so that they match the select polling call.
    ## @param timeout (int) time (in miliseconds) until poller times out
    ## @returns events (dict) dict of events that have been recognized
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
        return event_lst
