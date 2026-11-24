from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from report.cycles import CycleSettlement, FullCycle
from source.load_value import encode_load, parse_load
from source.series import require_beat


@dataclass(frozen=True)
class RangeCount:
    amplitude: Fraction
    full: int
    half: int


@dataclass(frozen=True)
class FatigueAccount:
    ranges: tuple[RangeCount, ...]
    full_cycles: tuple[FullCycle, ...]


def account_cycles(settlement: CycleSettlement) -> FatigueAccount:
    full = Counter(cycle.amplitude for cycle in settlement.full_cycles)
    half = Counter(settlement.half_amplitudes)
    ranges = tuple(
        RangeCount(amplitude, full[amplitude], half[amplitude])
        for amplitude in sorted(full.keys() | half.keys())
    )
    return FatigueAccount(ranges, settlement.full_cycles)


def encode_account(account: FatigueAccount) -> dict[str, list]:
    return {
        'ranges': [[encode_load(row.amplitude), row.full, row.half] for row in account.ranges],
        'full_cycles': [
            [encode_load(cycle.amplitude), cycle.first_beat, cycle.last_beat]
            for cycle in account.full_cycles
        ],
    }


def _triples(value: object, label: str):
    if not isinstance(value, list):
        raise ValueError(f'invalid {label} list')
    for row in value:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError(f'invalid {label} row')
        yield row


def decode_account(value: object) -> FatigueAccount:
    if not isinstance(value, dict) or value.keys() != {'ranges', 'full_cycles'}:
        raise ValueError('invalid fatigue account')

    ranges = []
    previous = Fraction(0)
    for text, full, half in _triples(value['ranges'], 'range'):
        amplitude = parse_load(text)
        if amplitude <= previous:
            raise ValueError('account ranges must be positive and strictly increasing')
        if type(full) is not int or type(half) is not int or min(full, half) < 0 or full + half == 0:
            raise ValueError('invalid full or half cycle count')
        ranges.append(RangeCount(amplitude, full, half))
        previous = amplitude

    cycles = []
    used_beats: set[int] = set()
    for text, first, last in _triples(value['full_cycles'], 'full cycle'):
        amplitude = parse_load(text)
        first, last = require_beat(first), require_beat(last)
        if amplitude <= 0 or first >= last or first in used_beats or last in used_beats:
            raise ValueError('invalid full cycle attribution')
        cycles.append(FullCycle(amplitude, first, last))
        used_beats.update((first, last))

    actual_full = Counter(cycle.amplitude for cycle in cycles)
    declared_full = {row.amplitude: row.full for row in ranges if row.full}
    if actual_full != declared_full:
        raise ValueError('full cycle attribution does not match range counts')
    return FatigueAccount(tuple(ranges), tuple(cycles))
