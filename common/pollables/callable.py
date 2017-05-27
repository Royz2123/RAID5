#!/usr/bin/python
## @package RAID5.common.pollables.callable
# Module that defines the Callable interface class
#

## A Callable base interface class.
## The class's only method is the on_finish method, which when called,
## wakes up the callable from sleep mode
class Callable(object):

    ## The on_finish method, which should be overriden by deried classes
    def on_finish(self):
        pass
