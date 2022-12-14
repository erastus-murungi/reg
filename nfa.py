from collections import defaultdict
from functools import reduce
from parser import Epsilon
from typing import Iterable, Optional

from core import (DFAState, FiniteStateAutomaton, Matchable, NullState,
                  State, Transition)

StatePair = tuple[State, State]


class NFA(FiniteStateAutomaton):
    """Formally, an NFA is a 5-tuple (Q, Σ, q0, T, δ) where
        • Q is finite set of states;
        • Σ is alphabet of input symbols;
        • q0 is start state;
        • T is subset of Q giving the ``accept`` states;
        and
        • δ is the transition function.
    Now the transition function specifies a set of states rather than a state: it maps Q × Σ to { subsets of Q }."""

    def __init__(
        self,
        transitions: Optional[defaultdict[State, set[Transition]]] = None,
        states: Optional[set[State]] = None,
        symbols: Optional[set[Matchable]] = None,
        start_state: Optional[State] = None,
        accept: Optional[State] = None,
    ):
        super(FiniteStateAutomaton, self).__init__(set)
        assert transitions is not None
        self.update(transitions)
        assert symbols is not None
        self.symbols = symbols
        assert states is not None
        self.states = states
        assert start_state is not None
        self.set_start(start_state)
        assert accept is not None
        self.set_accept(accept)
        self.accept = accept

    def set_accept(self, accept: State):
        self.accept = accept
        accept.accepts = True

    def all_transitions(self):
        for start, table in self.items():
            for symbol, end in table:
                yield symbol, start, end

    def transition(self, state: State, symbol: Matchable) -> list[State]:
        states = []
        for sym, state in self[state]:
            if sym == symbol:
                states.append(state)
        if not states:
            states = [NullState]
        return states

    def __repr__(self):
        return (
            f"FSM(states={self.states}, "
            f"symbols={self.symbols}, "
            f"start_state={self.start_state}, "
            f"accept_states={self.accept}) "
        )

    def filter(self, start: State, matchable: Matchable) -> tuple[Transition, ...]:
        return tuple(state for symbol, state in self[start] if symbol == matchable)

    def epsilon_closure(self, states: Iterable) -> frozenset:
        """
        This is the set of all the nodes which can be reached by following epsilon labeled edges
        This is done here using a depth first search

        https://castle.eiu.edu/~mathcs/mat4885/index/Webview/examples/epsilon-closure.pdf
        """

        seen = set()

        stack = list(states)
        closure = set()

        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)

            stack.extend(self.filter(u, Epsilon))
            closure.add(u)

        return frozenset(closure)

    def move(self, states: Iterable, symbol: Matchable) -> frozenset[State]:
        return frozenset(
            reduce(set.union, (self.filter(state, symbol) for state in states), set())
        )

    def find_state(self, state_id: int) -> Optional[State]:
        for state in self.states:
            if state_id == state.id:
                return state
        return None

    def gen_dfa_state_set_flags(self, sources) -> DFAState:
        state = DFAState(from_states=sources)
        if self.accept in state.sources:
            state.accepts = True
        state.lazy = any(s.lazy for s in sources)
        return state

    def compute_transitions_for_dfa_state(
        self,
        dfa,
        dfa_from: DFAState,
        seen: set[frozenset],
        stack: list[DFAState],
    ):
        # what is the epsilon closure of the dfa_states
        eps = self.epsilon_closure(dfa_from.sources)
        d = self.gen_dfa_state_set_flags(eps)
        if d.accepts:
            dfa.accept.add(d)

        # next we want to see which states are reachable from each of the states in the epsilon closure
        for symbol in self.symbols:
            next_states_set = self.epsilon_closure(self.move(eps, symbol))
            # new DFAState
            df = self.gen_dfa_state_set_flags(next_states_set)
            dfa[d].add(Transition(symbol, df))
            if next_states_set not in seen:
                seen.add(next_states_set)
                stack.append(df)
        return d
