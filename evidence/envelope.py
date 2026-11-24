import json
from dataclasses import dataclass
from hashlib import sha256

from evidence.coverage import EvidenceCoverage, parse_coverage


@dataclass(frozen=True)
class EvidenceEnvelope:
    piece_id: str
    shift_id: str
    measurement_id: str
    coverage: EvidenceCoverage
    body: str
    version: int = 1


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate evidence field: {key}')
        result[key] = value
    return result


def decode_object(serialized: str) -> dict[str, object]:
    if not isinstance(serialized, str):
        raise ValueError('evidence must be JSON text')
    value = json.loads(serialized, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError('evidence must contain a JSON object')
    return value


def require_identity(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('missing evidence identity')
    value.encode('utf-8')
    return value


def piece_identity(body: str) -> str:
    return 'sha256:' + sha256(body.encode('utf-8')).hexdigest()


def make_envelope(
    body: str, shift_id: str, measurement_id: str, coverage: EvidenceCoverage, *, version: int = 1
) -> str:
    return canonical_json({
        'version': version,
        'piece_id': piece_identity(body),
        'shift_id': shift_id,
        'measurement_id': measurement_id,
        'coverage': coverage.to_wire(),
        'body': body,
    })


def read_envelope(serialized: str) -> EvidenceEnvelope:
    value = decode_object(serialized)
    if value.keys() != {'version', 'piece_id', 'shift_id', 'measurement_id', 'coverage', 'body'}:
        raise ValueError('invalid evidence envelope fields')
    if type(value['version']) is not int or value['version'] not in (1, 2):
        raise ValueError('unsupported evidence version')
    body = value['body']
    if not isinstance(body, str):
        raise ValueError('evidence body must be JSON text')
    return EvidenceEnvelope(
        require_identity(value['piece_id']), require_identity(value['shift_id']),
        require_identity(value['measurement_id']), parse_coverage(value['coverage']), body,
        value['version'],
    )
