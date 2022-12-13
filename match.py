import re
from dataclasses import dataclass
from parser import Anchor
from typing import Optional

from core import RegexContext, State
from pyreg import compile_regex


@dataclass(frozen=True, slots=True)
class Match:
    start: int
    end: int
    substr: str

    @property
    def span(self):
        return self.start, self.end

    def __repr__(self):
        return (
            f"{self.__class__.__name__}"
            f"(span={self.span}, "
            f"match={self.substr!r})"
        )


class RegexMatcher:
    def __init__(self, regexp: str, text: str):
        self.text = text
        self.regexp = regexp
        self.compiled_regex = compile_regex(regexp)

    def _try_match_from_index(
        self, state: State, context: RegexContext
    ) -> Optional[int]:
        if state is not None:
            matches = self.compiled_regex[state].match(context)

            indices = []
            lazy = state.lazy

            for symbol, next_state in matches:
                index = self._try_match_from_index(
                    next_state,
                    context.copy()
                    if isinstance(symbol, Anchor)
                    else context.increment(),
                )

                if index is not None:
                    indices.append(index)
                state = next_state

            if indices:
                return min(indices) if lazy else max(indices)

            if state.accepts:
                return context.position if not matches else context.position + 1
        return None

    def __iter__(self):
        index = 0
        while index <= len(self.text):
            position = self._try_match_from_index(
                self.compiled_regex.start_state, RegexContext(self.text, index)
            )
            if position is not None:
                yield Match(index, position, self.text[index:position])
                index = position + 1 if position == index else position
            else:
                index = index + 1

    def __repr__(self):
        return f"{self.__class__.__name__}(regex={self.regexp!r}, text={self.text!r})"


if __name__ == "__main__":
    regex, t = ("[^\\s\\S]", "aaaaaaa")
    matcher = RegexMatcher(regex, t)

    for span in re.finditer(regex, t):
        print(span)

    print(matcher)
    for span in matcher:
        print(span)
