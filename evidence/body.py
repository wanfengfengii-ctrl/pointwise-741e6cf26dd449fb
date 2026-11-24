from dataclasses import dataclass

from evidence.coverage import EvidenceCoverage, parse_coverage
from evidence.envelope import canonical_json, decode_object, require_identity
from report.account import FatigueAccount, decode_account, encode_account
from source.load_value import encode_load
from source.series import Sample, turning_samples, validate_series


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
