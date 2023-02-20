from collections import deque
from operator import itemgetter
from pprint import pprint
from typing import Optional

from src.fsm import DFA, NFA, State, Transition
from src.matcher import Context, Cursor, RegexPattern
from src.parser import EPSILON, Anchor, RegexFlag, RegexParser


class RegexNFA(NFA, RegexPattern):
    """
    A backtracking NFA based regex pattern matcher

    Examples
    --------
    >>> pattern, text = '(ab)+', 'abab'
    >>> compiled_regex = RegexNFA(pattern)
    >>> print(list(compiled_regex.finditer(text)))
    [RegexMatch(span=(0, 4), match='abab')]
    >>> print([m.groups() for m in compiled_regex.finditer(text)])
    [('ab',)]
    """

    def __init__(self, pattern: str, flags: RegexFlag = RegexFlag.NOFLAG):
        NFA.__init__(self)
        RegexPattern.__init__(self, RegexParser(pattern, flags))
        self.set_terminals(self.parser.root.accept(self))
        self.update_symbols_and_states()

    def recover(self) -> str:
        return self.parser.root.to_string()

    def _match_suffix_dfa(
        self, state: State, cursor: Cursor, context: Context
    ) -> Optional[int]:
        """
        This a fast matcher when you don't have groups or greedy quantifiers
        """
        assert self.parser.group_count == 0

        if state is not None:
            matching_cursors = []

            if state in self.accepting_states:
                matching_cursors.append(cursor)

            transitions = [
                transition
                for transition in self[state]
                if transition.matcher(cursor, context)
            ]

            for matcher, end_state in transitions:
                result = self._match_suffix_dfa(
                    end_state, matcher.update_index(cursor), context
                )

                if result is not None:
                    matching_cursors.append(result)

            if matching_cursors:
                return max(matching_cursors, key=itemgetter(0))

        return None

    def step(
        self, start_state: State, cursor: Cursor, context: Context
    ) -> list[Transition]:
        """
        Performs a depth first search to collect valid transitions the transitions reachable through epsilon transitions
        """
        explored: set[State] = set()
        stack: list[tuple[bool, State]] = [(False, start_state)]
        transitions: list[Transition] = []

        while stack:
            completed, state = stack.pop()
            if completed:
                # we can easily compute the close by append state to a closure
                # collection i.e `closure.append(state)`
                # once we are done with this state
                for transition in self[state]:
                    # augment to match epsilon transitions which lead to accepting states
                    # we could rewrite things by passing more context into the match method so that
                    # this becomes just a one-liner: transition.matcher(context)
                    if transition.matcher(cursor, context) or (
                        transition.matcher is EPSILON
                        and transition.end in self.accepting_states
                    ):
                        transitions.append(transition)

            if state in explored:
                continue

            explored.add(state)

            stack.append((True, state))
            # explore the states in the order which they are in
            stack.extend(
                (False, nxt) for nxt in self.transition(state, EPSILON, True)[::-1]
            )
        return transitions

    def step0(
        self,
        start: Transition,
        cursor: Cursor,
        context: Context,
        explored: set[Transition],
    ) -> list[tuple[Transition, Cursor]]:
        """
        Performs a depth first search to collect valid transitions the transitions reachable through epsilon transitions
        """
        stack: list[tuple[Transition, Cursor]] = [
            (nxt, start.matcher.update(cursor)) for nxt in self[start.end][::-1]
        ]
        transitions: list[tuple[Transition, Cursor]] = []

        while stack:
            transition, cursor = stack.pop()

            if transition in explored:
                continue

            explored.add(transition)

            if isinstance(transition.matcher, Anchor):
                if transition.matcher is EPSILON or transition.matcher(cursor, context):
                    if transition.end in self.accepting_states:
                        transitions.append((transition, cursor))
                    else:
                        stack.extend(
                            (nxt, transition.matcher.update(cursor))
                            for nxt in self[transition.end][::-1]
                        )
            else:
                transitions.append((transition, cursor))

        return transitions

    def _match_suffix_with_groups0(
        self, cursor: Cursor, context: Context
    ) -> Optional[Cursor]:
        # we only need to keep track of 3 state variables
        visited = set()
        queue = deque(
            self.step0(Transition(EPSILON, self.start_state), cursor, context, visited)
        )

        match = None

        while True:
            frontier, next_visited = deque(), set()

            while queue:
                transition, cursor = queue.popleft()

                if (
                    transition.matcher(cursor, context)
                    or transition.matcher is EPSILON
                    and transition.end in self.accepting_states
                ):
                    if transition.end in self.accepting_states:
                        match = transition.matcher.update(cursor)
                        break

                    if transition.end not in next_visited:
                        frontier.extend(
                            self.step0(transition, cursor, context, next_visited)
                        )

            if not frontier:
                break

            queue, visited = frontier, next_visited

        return match

    def _match_suffix_with_groups(
        self, cursor: Cursor, context: Context
    ) -> Optional[Cursor]:
        # we only need to keep track of 3 state variables
        stack = [(self.start_state, cursor, ())]

        while stack:
            state, cursor, path = stack.pop()  # type: (int, Cursor, tuple[int, ...])

            if state in self.accepting_states:
                return cursor

            for matcher, end_state in reversed(self.step(state, cursor, context)):
                if isinstance(matcher, Anchor):
                    if end_state in path:
                        continue
                    updated_path = path + (end_state,)
                else:
                    updated_path = ()

                stack.append(
                    (
                        end_state,
                        matcher.update(cursor),
                        updated_path,
                    )
                )

        return None

    def _match_suffix_no_groups(
        self, cursor: Cursor, context: Context
    ) -> Optional[int]:
        # we only need to keep track of 2 state variables
        stack = [(self.start_state, cursor, ())]

        while stack:
            state, cursor, path = stack.pop()

            if state in self.accepting_states:
                return cursor

            for matcher, end_state in reversed(self.step(state, cursor, context)):
                if isinstance(matcher, Anchor):
                    if end_state in path:
                        continue
                    updated_path = path + (end_state,)
                else:
                    updated_path = ()

                stack.append(
                    (
                        end_state,
                        matcher.update_index(cursor),
                        updated_path,
                    )
                )

        return None

    def match_suffix(self, cursor: Cursor, context: Context) -> Optional[Cursor]:
        """
        Given a cursor, and context. Match the pattern against the cursor and return
        a final cursor that matches the pattern or none if the pattern could not match

        Parameters
        ----------
        cursor: Cursor
            An initial cursor object
        context: Context
            A static context object

        Returns
        -------
        Optional[Cursor]
            A cursor object in which cursor[0] is the position where the pattern ends in context.txt
            and cursor[1] are the filled out groups

        Examples
        --------
        >>> from sys import maxsize
        >>> pattern, text = '(ab)+', 'abab'
        >>> compiled_regex = RegexNFA(pattern)
        >>> ctx = Context(text, RegexFlag.NOFLAG)
        >>> start = 0
        >>> c = compiled_regex.match_suffix((start, [maxsize, maxsize]), ctx)
        >>> c
        (4, [2, 4])
        >>> end, groups = c
        >>> assert text[start: end] == 'abab'
        """
        if isinstance(super(), DFA):
            return self._match_suffix_dfa(self.start_state, cursor, context)
        elif self.parser.group_count > 0:
            return self._match_suffix_with_groups0(cursor, context)
        else:
            return self._match_suffix_no_groups(cursor, context)

    def __repr__(self):
        return super().__repr__()


if __name__ == "__main__":
    # import doctest
    #
    # doctest.testmod()
    import re

    # regex, text = "(a+|b)*", "ab"
    regex, text = pattern = "s()?e", "searchme"
    p = RegexNFA(regex)

    expected_groups = [m.groups() for m in re.finditer(regex, text)]
    actual_groups = [m.groups() for m in p.finditer(text)]
    # p.graph()
    pprint(list(p.finditer(text)))
    pprint(list(re.finditer(regex, text)))
    pprint(actual_groups)
    pprint(expected_groups)