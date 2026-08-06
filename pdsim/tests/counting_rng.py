"""A counting wrapper around ``numpy.random.Generator`` (M11a Phase C, spec Design 9).

Test support ONLY — this module never ships in ``pdsim/`` and no engine code
may import it. Its job is to turn "the output matched" into "the stream was
identical": byte-comparison of a run's output usually catches a spurious RNG
draw, because a shifted stream changes everything downstream — but NOT if
the extra draw lands after the last consequential draw of the run, where
nothing remains to be perturbed. Recording the exact sequence of method
calls catches that case too, and it makes the spec's no-draw assertions
directly expressible ("this run consumed zero contest-permutation draws")
rather than inferential ("this run's output looks unshifted").

The wrapper is a delegating proxy, not a ``Generator`` subclass: every
attribute access is forwarded to the wrapped generator, and every METHOD
call is recorded as ``(method name, argument summary)`` before its result is
returned unchanged. The engine only ever touches its generator through
attribute access (``rng.random()``, ``rng.choice(...)`` and so on), so a
proxy is a drop-in wherever a dynamics class takes an injected ``rng`` —
which is exactly how the no-draw pins drive it.

One numpy fact the pins must not trip over, established by probe on numpy
2.5: ``Generator.permutation`` at sizes 0 and 1 does not advance the bit
generator's state (there is nothing to shuffle). The recorded CALL still
happens — the wrapper counts calls, not state movement — so "one
permutation call per generation whenever the gate holds" stays assertable
even in generations that admit no parents.
"""

from __future__ import annotations

import numpy as np

__all__ = ["CountingGenerator"]


def _summarise(value: object) -> object:
    """Reduce one call argument to a small, comparison-friendly summary.

    Args:
        value: A positional or keyword argument of a generator method.

    Returns:
        The value itself for scalars, ``("len", n)`` for sized containers
        (lists, tuples, arrays — the pool of a ``choice`` call), and the
        type name for anything else. Enough to tell draws apart in a
        failing test without dragging whole candidate arrays into the log.
    """
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    if isinstance(value, np.ndarray):
        return ("shape", value.shape)
    if isinstance(value, list | tuple | frozenset | set | range):
        return ("len", len(value))
    return type(value).__name__


class CountingGenerator:
    """A drop-in ``numpy.random.Generator`` proxy that logs every method call.

    Attributes:
        calls: The recorded call log, in call order — one
            ``(method_name, args_summary, kwargs_summary)`` tuple per
            generator method invoked. Inspect it directly, or use
            :meth:`count` for the common "how many draws of this kind"
            assertion.
    """

    def __init__(self, rng: np.random.Generator) -> None:
        """Wrap a generator.

        Args:
            rng: The real seeded generator every call is forwarded to.
        """
        # Plain attribute writes are safe — only __getattr__ is overridden,
        # and it fires solely for attributes NOT found the normal way.
        self._rng = rng
        self.calls: list[tuple[str, tuple[object, ...], tuple[tuple[str, object], ...]]] = []

    def __getattr__(self, name: str) -> object:
        """Forward an attribute lookup, wrapping callables to record calls.

        Args:
            name: The attribute being looked up (e.g. ``"choice"``).

        Returns:
            The wrapped generator's attribute; methods come back wrapped so
            each invocation is appended to :attr:`calls`.
        """
        attribute = getattr(self._rng, name)
        if not callable(attribute):
            return attribute

        def recorded(*args: object, **kwargs: object) -> object:
            summary_args = tuple(_summarise(a) for a in args)
            summary_kwargs = tuple(sorted((k, _summarise(v)) for k, v in kwargs.items()))
            self.calls.append((name, summary_args, summary_kwargs))
            return attribute(*args, **kwargs)

        return recorded

    def count(self, method: str) -> int:
        """Count how many times one generator method was called.

        Args:
            method: The method name, e.g. ``"permutation"``.

        Returns:
            The number of recorded calls to that method.
        """
        return sum(1 for call_name, _, _ in self.calls if call_name == method)
