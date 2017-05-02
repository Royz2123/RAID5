
class StateMachine(object):
    (
        BEFORE_INPUT,
        AFTER_INPUT,
    ) = range(2)

    def __init__(
        self,
        states,
        first_state,
        final_state = state.State()
    ):
        # each state should imlpement before_input and after_input
        # before_input shouldn't return anything
        # after_input should return next state if finished recieving input,
        # and False otherwise
        # The machine doesn't handle input, input needs to be updated so that
        # after_input can recognize the new input
        # final_state is a dummy state, that states if the state machine has
        # finished running
        self._states = states
        self._current_state = first_state
        self._final_state = final_state
        self._inner_state = StateMachine.BEFORE_INPUT

    def run_machine(self):
        while True:
            if self._current_state == self._final_state:
                return

            #after input func tells if we are to move onto the next state
            if self._inner_state == StateMachine.AFTER_INPUT:
                next_state = self._current_state.after_input_func()
                if next_state is None:
                    return
                self._current_state = next_state
                self._inner_state = StateMachine.BEFORE_INPUT

            #before input state doesn't return anything
            if self._inner_state == StateMachine.BEFORE_INPUT:
                self._current_state.before_input_func()
                self._inner_state = StateMachine.BEFORE_INPUT

    
