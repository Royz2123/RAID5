from http.common.utilities.state_util import state

class StateMachine(object):
    (
        BEFORE_INPUT,
        AFTER_INPUT,
    ) = range(2)

    def __init__(
        self,
        states,
        first_state,
        final_state,
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

    #we assume that all the functions called by the machine will use the same
    # args, in order to reduce compexity
    def run_machine(self, args):
        while True:
            #returns True if the machine has finished running
            if self._current_state == self._final_state:
                return True

            #after input func tells if we are to move onto the next state
            if self._inner_state == StateMachine.AFTER_INPUT:
                next_state_index = self._current_state.after_input_func(*args)
                if next_state_index is None:
                    break
                self._current_state = self._states[next_state_index]
                self._inner_state = StateMachine.BEFORE_INPUT

            #before input state returns if we need to wait for input
            if self._inner_state == StateMachine.BEFORE_INPUT:
                #before_input checks for an epsilon_path, one that doesn't
                #require input. Since our State Machine is Semi-Deterministic,
                #we can assume that there is only one state to which we can
                #reach (next_states[0])
                epsilon_path = self._current_state.before_input_func(*args)
                if epsilon_path:
                    #if there is no need for input, move to next states
                    self._current_state = self._states[
                        self._current_state.next_states[0]
                    ]
                else:
                    self._inner_state = StateMachine.AFTER_INPUT
        return False
