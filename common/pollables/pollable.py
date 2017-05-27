## A Pollable base interface class.
## Base class for pollable objects, that are polled asynchronusly eiher with
## Poll or Select. All pollables must inherit from this class
class Pollable(object):

    ## What the pollable does when on idle (system on timeout)
    def on_idle(self):
        pass

    ## What the pollable does when on read
    def on_read(self):
        pass

    ## What the pollable does when on write
    def on_write(self):
        pass

    ## What the pollable does when on error
    def on_error(self):
        pass

    ## What events the pollable wants to listen to
    def get_events(self):
        return 0

    ## Is the pollable terminating or not
    def is_terminating(self):
        return False
