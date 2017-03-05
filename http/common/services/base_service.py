
class BaseService(object):
    def __init__(
        self,
        wanted_headers,
        wanted_args = [],
        args = []
    ):
        self._wanted_headers = wanted_headers + ["Content-Length"]
        self._wanted_args = wanted_args
        self._response_headers = {}
        self._response_status = 200
        self._response_content = ""
        self._args = args

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, a):
        self._args = a

    @property
    def wanted_headers(self):
        return self._wanted_headers

    @wanted_headers.setter
    def wanted_headers(self, w_h):
        self._wanted_headers = w_h

    @property
    def wanted_args(self):
        return self._wanted_args

    @wanted_args.setter
    def wanted_args(self, w_a):
        self._wanted_args = w_a

    @property
    def response_status(self):
        return self._response_status

    @response_status.setter
    def response_status(self, r_s):
        self._response_status = r_s

    @property
    def response_headers(self):
        return self._response_headers

    @response_headers.setter
    def response_headers(self, r_h):
        self._response_headers = r_h

    @property
    def response_content(self):
        return self._response_content

    @response_content.setter
    def response_content(self, r_c):
        self._response_content = r_c

    def before_content(self, entry):
        return True

    def before_response_status(self, entry):
        return True

    def before_response_headers(self, entry):
        return True

    def before_response_content(self, entry, max_buffer):
        return True

    def before_terminate(self, entry):
        return True

    def handle_content(self, entry, content):
        return True

    def check_args(self):
        for arg in self._wanted_args:
            if arg not in self._args.keys():
                return False
        return len(self._wanted_args) == len(self._args)
