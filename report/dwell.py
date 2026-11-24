from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from report.cycles import CyclePoint, settle_cycles
from report.provenance import ParentEvidence, decode_parents, encode_parents
from source.load_value import encode_load, parse_load
from source.series import LoadRun, Sample, require_beat, turning_samples


@dataclass(frozen=True)
class DwellInterval:
    load: Fraction
    first: int
    last: int

    @property
    def count(self) -> int:
        return self.last - self.first + 1


@dataclass(frozen=True)
class RetestEntry:
    amplitude: Fraction
    first_beat: int
    first_load: Fraction
    last_beat: int
    last_load: Fraction
    dwell: DwellInterval
    sources: tuple[ParentEvidence, ...]


def merge_runs(pieces_runs: Iterable[Iterable[LoadRun]]) -> tuple[LoadRun, ...]:
    """Join equal-load runs across piece seams into one dwell interval."""
    merged: list[LoadRun] = []
    for runs in pieces_runs:
        for run in runs:
            if merged and merged[-1].load == run.load:
                merged[-1] = LoadRun(merged[-1].first, run.last, run.load)
            else:
                merged.append(run)
    return tuple(merged)


def collect_entries(
    runs: tuple[LoadRun, ...],
    parents: tuple[ParentEvidence, ...],
    min_amplitude: Fraction,
    min_dwell: int,
) -> tuple[RetestEntry, ...]:
    """List full cycles meeting both thresholds in settlement order."""
    turns = turning_samples(Sample(run.first, run.load) for run in runs)
    points = tuple(CyclePoint(turn.beat, turn.load) for turn in turns)
    settlement = settle_cycles(points)
    loads = {point.beat: point.load for point in points}
    runs_by_first = {run.first: run for run in runs}
    entries = []
    for cycle in settlement.full_cycles:
        if cycle.amplitude < min_amplitude:
            continue
        first_load = loads[cycle.first_beat]
        last_load = loads[cycle.last_beat]
        high_beat = cycle.first_beat if first_load > last_load else cycle.last_beat
        run = runs_by_first[high_beat]
        dwell = DwellInterval(run.load, run.first, run.last)
        if dwell.count < min_dwell:
            continue
        sources = tuple(
            parent for parent in parents
            if parent.coverage.first <= dwell.last and dwell.first <= parent.coverage.last
        )
        entries.append(RetestEntry(
            cycle.amplitude, cycle.first_beat, first_load, cycle.last_beat, last_load,
            dwell, sources,
        ))
    return tuple(entries)


def encode_entries(entries: tuple[RetestEntry, ...]) -> list[dict]:
    return [
        {
            'amplitude': encode_load(entry.amplitude),
            'first': [entry.first_beat, encode_load(entry.first_load)],
            'last': [entry.last_beat, encode_load(entry.last_load)],
            'dwell': [entry.dwell.first, entry.dwell.last, encode_load(entry.dwell.load)],
            'sources': encode_parents(entry.sources),
        }
        for entry in entries
    ]


def _endpoint(value: object) -> tuple[int, Fraction]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('invalid retest entry endpoint')
    beat, load = value
    return require_beat(beat), parse_load(load)


def _dwell(value: object) -> DwellInterval:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError('invalid retest dwell interval')
    first, last, load = value
    first, last = require_beat(first), require_beat(last)
    if first > last:
        raise ValueError('retest dwell interval is reversed')
    return DwellInterval(parse_load(load), first, last)


def decode_entries(value: object) -> tuple[RetestEntry, ...]:
    if not isinstance(value, list):
        raise ValueError('invalid retest entries')
    entries = []
    for item in value:
        if not isinstance(item, dict) or item.keys() != {'amplitude', 'first', 'last', 'dwell', 'sources'}:
            raise ValueError('invalid retest entry')
        amplitude = parse_load(item['amplitude'])
        first_beat, first_load = _endpoint(item['first'])
        last_beat, last_load = _endpoint(item['last'])
        if amplitude <= 0 or first_beat >= last_beat or abs(first_load - last_load) != amplitude:
            raise ValueError('invalid retest cycle endpoints')
        dwell = _dwell(item['dwell'])
        high_beat = first_beat if first_load > last_load else last_beat
        if dwell.load != max(first_load, last_load) or dwell.first != high_beat:
            raise ValueError('retest dwell does not match the high-load end')
        entries.append(RetestEntry(
            amplitude, first_beat, first_load, last_beat, last_load,
            dwell, decode_parents(item['sources']),
        ))
    return tuple(entries)
