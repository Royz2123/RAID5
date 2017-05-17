

class Pollable(object):
    def on_idle(self):
        pass

    def on_read(self):
        pass

    def on_write(self):
        pass

    def on_error(self):
        pass

    def get_events(self):
        pass

    def is_closing(self):
        return False
