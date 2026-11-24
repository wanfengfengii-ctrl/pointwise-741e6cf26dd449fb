from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from source.load_value import parse_load


@dataclass(frozen=True)
class Sample:
    beat: int
    load: Fraction


@dataclass(frozen=True)
class MeasurementRevision:
    revision_id: str
    specimen: str
    parent_id: str | None
    samples: tuple[Sample, ...]


def require_beat(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError('original beat must be a positive integer')
    return value


def require_specimen(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('specimen must be nonempty text')
    value.encode('utf-8')
    return value


def validate_series(rows: Iterable[object]) -> tuple[Sample, ...]:
    """Validate caller order and preserve physical gaps."""
    try:
        iterator = iter(rows)
    except TypeError as error:
        raise ValueError('measurements must be an iterable of beat/load pairs') from error

    samples = []
    previous = 0
    for row in iterator:
        if isinstance(row, Sample):
            beat, load = row.beat, row.load
        elif isinstance(row, (tuple, list)) and len(row) == 2:
            beat, load = row
        else:
            raise ValueError('each measurement requires one beat and one load')
        beat = require_beat(beat)
        if beat <= previous:
            raise ValueError('original beats must be strictly increasing')
        samples.append(Sample(beat, parse_load(load)))
        previous = beat
    if not samples:
        raise ValueError('empty measurement batch')
    return tuple(samples)


def turning_samples(samples: Iterable[Sample]) -> tuple[Sample, ...]:
    """Keep the first beat of each plateau and retain ends and reversals."""
    plateaus: list[Sample] = []
    for sample in samples:
        if not plateaus or plateaus[-1].load != sample.load:
            plateaus.append(sample)
    if len(plateaus) < 3:
        return tuple(plateaus)

    turns = [plateaus[0]]
    for left, middle, right in zip(plateaus, plateaus[1:], plateaus[2:]):
        rises_to_middle = left.load < middle.load
        rises_from_middle = middle.load < right.load
        if rises_to_middle != rises_from_middle:
            turns.append(middle)
    turns.append(plateaus[-1])
    return tuple(turns)
