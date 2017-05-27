## Base class for all HTTP services
## It is important that every service that is created will inherit from this
## this class, because when a server chooses a service it looks at the
## subclass of the BaseService.
class BaseService(object):

    ## Constructor for BaseService
    ## @param (optional) wanted_headers (list) list of all the headers that
    ## the Service is interested in. Will always be interested in the
    ## Content-Length header to check validity of content
    ## @param (optional) wanted_args (list) list of all the wanted args that
    ## the service is intersted in
    ## @param (optional) args (dict) dict of the actual args that have been
    ## recieved and parsed. It is advised to check that they match the
    ## wanted_args using the function:
    ## @ref common.service.base_service.BaseService.check_args
    def __init__(
        self,
        wanted_headers=[],
        wanted_args=[],
        args={}
    ):
        ## The wanted headers, with the unavoiable Content-length
        # if Content-length is already in the wanted headers, remove it
        self._wanted_headers = list(set(
            wanted_headers + ["Content-Length"]
        ))

        ## The wanted args
        self._wanted_args = wanted_args

        ## The response_headers that the service creates
        self._response_headers = {}

        ## The response status that the service creates
        ## is initially by default 200 (OK)
        self._response_status = 200

        ## The response_content that the service creates
        self._response_content = ""

        ## The parsed args recieved by the socket
        self._args = args


    ## Checks that the args match the wanted_args
    ## @returns (bool) if args match
    def check_args(self):
        for arg in self._wanted_args:
            if arg not in self._args.keys():
                return False
        return len(self._wanted_args) == len(self._args)

    # Getters and Setters


    @property
    def args(self):
        return self._args

    @property
    def wanted_headers(self):
        return self._wanted_headers

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

    # Service Functions

    def before_content(self, entry):
        return True

    def before_response_status(self, entry):
        return True

    def before_response_headers(self, entry):
        return True

    def before_response_content(self, entry):
        return True

    def before_terminate(self, entry):
        return True

    def handle_content(self, entry, content):
        return True
