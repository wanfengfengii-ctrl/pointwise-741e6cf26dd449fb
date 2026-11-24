from dataclasses import dataclass

from evidence.coverage import EvidenceCoverage, parse_coverage
from evidence.envelope import canonical_json, decode_object, require_identity
from report.account import FatigueAccount, decode_account, encode_account
from source.load_value import encode_load, parse_load
from source.series import LoadRun, Sample, require_beat, turning_runs, turning_samples, validate_series


@dataclass(frozen=True)
class EvidenceBody:
    shift_id: str
    measurement_id: str
    coverage: EvidenceCoverage
    points: tuple[Sample, ...]
    local_account: FatigueAccount


def build_evidence_body(
    shift_id: str,
    measurement_id: str,
    coverage: EvidenceCoverage,
    samples: tuple[Sample, ...],
    local_account: FatigueAccount,
) -> EvidenceBody:
    """Project a covered shift to candidate ends and interior reversals."""
    return EvidenceBody(shift_id, measurement_id, coverage, turning_samples(samples), local_account)


def encode_evidence_body(body: EvidenceBody) -> str:
    return canonical_json({
        'shift_id': body.shift_id,
        'measurement_id': body.measurement_id,
        'coverage': body.coverage.to_wire(),
        'points': [[point.beat, encode_load(point.load)] for point in body.points],
        'local_account': encode_account(body.local_account),
    })


def decode_evidence_body(serialized: str) -> EvidenceBody:
    value = decode_object(serialized)
    if value.keys() != {'shift_id', 'measurement_id', 'coverage', 'points', 'local_account'}:
        raise ValueError('invalid V1 body fields')
    coverage = parse_coverage(value['coverage'])
    if not isinstance(value['points'], list):
        raise ValueError('invalid evidence points')
    points = validate_series(value['points'])
    if points[0].beat != coverage.first or points[-1].beat > coverage.last:
        raise ValueError('evidence points are outside the declared coverage')
    if turning_samples(points) != points:
        raise ValueError('evidence points contain redundant interior points')
    return EvidenceBody(
        require_identity(value['shift_id']), require_identity(value['measurement_id']),
        coverage, points, decode_account(value['local_account']),
    )


@dataclass(frozen=True)
class DwellBody:
    shift_id: str
    measurement_id: str
    coverage: EvidenceCoverage
    runs: tuple[LoadRun, ...]
    local_account: FatigueAccount

    @property
    def points(self) -> tuple[Sample, ...]:
        return tuple(Sample(run.first, run.load) for run in self.runs)


def build_dwell_body(
    shift_id: str,
    measurement_id: str,
    coverage: EvidenceCoverage,
    samples: tuple[Sample, ...],
    local_account: FatigueAccount,
) -> DwellBody:
    """Project a covered shift to turning runs with plateau first/last beats."""
    return DwellBody(shift_id, measurement_id, coverage, turning_runs(samples), local_account)


def encode_dwell_body(body: DwellBody) -> str:
    return canonical_json({
        'shift_id': body.shift_id,
        'measurement_id': body.measurement_id,
        'coverage': body.coverage.to_wire(),
        'runs': [[run.first, run.last, encode_load(run.load)] for run in body.runs],
        'local_account': encode_account(body.local_account),
    })


def _decode_runs(value: object) -> tuple[LoadRun, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError('invalid dwell runs')
    runs = []
    previous_last = 0
    previous_load = None
    for row in value:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('invalid dwell run row')
        first, last, load = row
        first, last = require_beat(first), require_beat(last)
        if first > last:
            raise ValueError('dwell run is reversed')
        if first <= previous_last:
            raise ValueError('dwell runs must be strictly increasing')
        load = parse_load(load)
        if load == previous_load:
            raise ValueError('adjacent dwell runs share one load')
        runs.append(LoadRun(first, last, load))
        previous_last, previous_load = last, load
    return tuple(runs)


def decode_dwell_body(serialized: str) -> DwellBody:
    value = decode_object(serialized)
    if value.keys() != {'shift_id', 'measurement_id', 'coverage', 'runs', 'local_account'}:
        raise ValueError('invalid V2 body fields')
    coverage = parse_coverage(value['coverage'])
    runs = _decode_runs(value['runs'])
    if runs[0].first != coverage.first or runs[-1].last != coverage.last:
        raise ValueError('dwell runs are outside the declared coverage')
    points = tuple(Sample(run.first, run.load) for run in runs)
    if turning_samples(points) != points:
        raise ValueError('dwell runs contain non-plateau monotone interior beats')
    return DwellBody(
        require_identity(value['shift_id']), require_identity(value['measurement_id']),
        coverage, runs, decode_account(value['local_account']),
    )
