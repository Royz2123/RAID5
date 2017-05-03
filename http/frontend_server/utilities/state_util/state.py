
class State(object):
    # each state can be seen as an inner state machine of two states, before_input
    # and after_input. after_input checks if the input that has been recieved
    # is complete, and reports accordingly:
    # None - Incomplete
    # Some index - Complete input, next state (based on input)
    def default_before_input_func(self, entry):
        pass

    def default_after_input_func(self, entry):
        return self._next_states[0]

    def __init__(
        self,
        index,
        next_states,
        before_func = default_before_input_func,
        after_func = default_after_input_func,
    ):
        self._index = index
        self._next_states = next_states
        self._before_input_func = before_func
        self._after_input_func = after_func

    @property
    def index(self):
        return self._index

    def __repr__(self):
        return "State from State machine:\t%s\n" % self._index

    @property
    def before_input_func(self):
        return self._before_input_func

    @property
    def after_input_func(self):
        return self._after_input_func
