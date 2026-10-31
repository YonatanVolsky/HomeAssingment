"""Turns the user's raw term into a normalized string by running a protocol's steps.

The normalizer is generic: what is accepted and how it is rewritten lives entirely in the
protocol it is given, so protocols can be swapped without changing this module.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.errors import AppError

Step = Callable[[str], str]
"""One transformation of the term, or AppError('INVALID_TERM') to reject it."""


@dataclass(frozen=True)
class TermProtocol:
    """A named, ordered chain of steps."""

    name: str
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError(f'term protocol {self.name!r} has no steps')


class TermNormalizer:
    def __init__(self, protocol: TermProtocol) -> None:
        self._protocol = protocol

    def normalize(self, raw: str) -> str:
        """Returns the normalized term, or raises INVALID_TERM."""
        text = raw
        for step in self._protocol.steps:
            text = step(text)
        if text == '':
            raise AppError('INVALID_TERM')
        return text
