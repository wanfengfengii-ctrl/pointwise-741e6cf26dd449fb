from collections.abc import Iterable
from dataclasses import dataclass

from evidence.coverage import EvidenceCoverage, parse_coverage
from evidence.envelope import require_identity
from intake.catalog import Receipt


@dataclass(frozen=True)
class ParentEvidence:
    receipt_id: int
    piece_id: str
    shift_id: str
    measurement_id: str
    coverage: EvidenceCoverage


def bind_parents(receipts: Iterable[Receipt]) -> tuple[ParentEvidence, ...]:
    return tuple(
        ParentEvidence(receipt.receipt_id, receipt.piece_id, receipt.shift_id,
                       receipt.measurement_id, receipt.coverage)
        for receipt in receipts
    )


def encode_parents(parents: tuple[ParentEvidence, ...]) -> list[dict]:
    return [
        {'receipt_id': parent.receipt_id, 'piece_id': parent.piece_id,
         'shift_id': parent.shift_id, 'measurement_id': parent.measurement_id,
         'coverage': parent.coverage.to_wire()}
        for parent in parents
    ]


def decode_parents(value: object) -> tuple[ParentEvidence, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError('published report lacks parent evidence')
    parents = []
    fields = {'receipt_id', 'piece_id', 'shift_id', 'measurement_id', 'coverage'}
    for item in value:
        if not isinstance(item, dict) or item.keys() != fields:
            raise ValueError('invalid report parent')
        receipt_id = item['receipt_id']
        if type(receipt_id) is not int or receipt_id < 1:
            raise ValueError('invalid parent receipt number')
        parents.append(ParentEvidence(
            receipt_id, require_identity(item['piece_id']), require_identity(item['shift_id']),
            require_identity(item['measurement_id']), parse_coverage(item['coverage']),
        ))
    return tuple(parents)
