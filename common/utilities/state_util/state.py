#!/usr/bin/python
## @package RAID5.common.utilities.state
# Module that implements a single State class
#

## A single state class.
## Each state can be seen as an inner state machine of two states, before_input
## and after_input. after_input checks if the input that has been recieved
## is complete, and reports accordingly:
## None - Incomplete
## Some index - Complete input, next state (based on input)
class State(object):

    ## Default before input function
    ## @param entry (pollable) entry we're working with
    ## @returns False (default no having an epsilon path)
    def default_before_input_func(self, entry):
        return False  # set default state to not have an epsilon_path

    ## Default after input function
    ## @param entry (pollable) entry we're working with
    ## @returns next_state (State) returns the first one in next_states as
    ## default
    def default_after_input_func(self, entry):
        return self._next_states[0]

    ## Constructor for State
    ## @param index (int) index of this state
    ## @param next_states (list) list of the next state indexes
    ## @param before_func (optional) (func) before_input_func
    ## @param after_func (optional) (func) after_input_func
    def __init__(
        self,
        index,
        next_states,
        before_func=default_before_input_func,
        after_func=default_after_input_func,
    ):
        ## State index
        self._index = index

        ## Next states list
        self._next_states = next_states

        ## Before input function
        self._before_input_func = before_func

        ## After input function
        self._after_input_func = after_func

    ## Index property
    ## @returns index (int)
    @property
    def index(self):
        return self._index

    ## Representation of the State
    ## @returns representation (string) representation of state as string
    def __repr__(self):
        return "State from State machine:\t%s" % self._index

    ## Before input function property
    ## @returns before_input_func (func)
    @property
    def before_input_func(self):
        return self._before_input_func

    ## next_states property
    ## @returns next_states (list)
    @property
    def next_states(self):
        return self._next_states

    ## After input function property
    ## @returns after_input_func (func)
    @property
    def after_input_func(self):
        return self._after_input_func
