
class State(object):
    # each state can be seen as an inner state machine of two states, before_input
    # and after_input. after_input checks if the input that has been recieved
    # is complete, and reports accordingly:
    # None - Incomplete
    # Some State - Complete input, next state (based on input)

    def __init__(
        self,
        index,
        next_states,
        before_input_func = State.default_before_input_func,
        after_input_func = State.default_after_input_func,
    ):
        self._index = index
        self._next_states = next_states
        self._before_input_func = before_input_func
        self._after_input_func = after_input_func

    def default_before_input_func(self):
        pass

    def default_after_input_func(self):
        return self._next_states[0]

    @property
    def index(self):
        return self._index

    def __repr__(self):
        return "State from State machine:\t%s\n" % self._index

    @property
    def before_input_func(self):
        return self.before_input_func

    @property
    def after_input_func(self):
        return self.after_input_func
