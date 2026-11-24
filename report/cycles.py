from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class CyclePoint:
    beat: int
    load: Fraction


@dataclass(frozen=True)
class FullCycle:
    amplitude: Fraction
    first_beat: int
    last_beat: int


@dataclass(frozen=True)
class CycleSettlement:
    full_cycles: tuple[FullCycle, ...]
    half_amplitudes: tuple[Fraction, ...]


def settle_cycles(points: Iterable[CyclePoint]) -> CycleSettlement:
    """Settle confirmed turning points in leftmost four-point order."""
    remaining = list(points)
    full_cycles = []
    while True:
        for index in range(len(remaining) - 3):
            left, first, last, right = remaining[index:index + 4]
            middle = abs(first.load - last.load)
            if middle <= min(abs(left.load - first.load), abs(last.load - right.load)):
                full_cycles.append(FullCycle(middle, first.beat, last.beat))
                del remaining[index + 1:index + 3]
                break
        else:
            half_amplitudes = tuple(
                abs(left.load - right.load)
                for left, right in zip(remaining, remaining[1:])
            )
            return CycleSettlement(tuple(full_cycles), half_amplitudes)
