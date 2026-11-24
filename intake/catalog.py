import sqlite3
from dataclasses import dataclass

from evidence.coverage import EvidenceCoverage
from evidence.envelope import read_envelope
from intake.identity import VerifiedEvidence


@dataclass(frozen=True)
class Receipt:
    receipt_id: int
    piece_id: str
    shift_id: str
    measurement_id: str
    coverage: EvidenceCoverage
    original: str


class ReceiptCatalog:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS evidence_receipts (
                id INTEGER PRIMARY KEY,
                piece_id TEXT UNIQUE NOT NULL,
                shift_id TEXT NOT NULL,
                measurement_id TEXT NOT NULL,
                specimen TEXT NOT NULL,
                first_beat TEXT NOT NULL,
                last_beat TEXT NOT NULL,
                original TEXT NOT NULL
            )
        ''')

    @staticmethod
    def _receipt(row: tuple) -> Receipt:
        receipt_id, piece_id, shift_id, measurement_id, specimen, first, last, original = row
        return Receipt(
            receipt_id, piece_id, shift_id, measurement_id,
            EvidenceCoverage(specimen, int(first), int(last)), original,
        )

    def register_original(self, verified: VerifiedEvidence) -> Receipt:
        envelope = verified.envelope
        coverage = envelope.coverage
        if self.connection.in_transaction:
            raise RuntimeError('intake requires an idle center connection')
        with self.connection:
            self.connection.execute(
                '''INSERT INTO evidence_receipts (
                       piece_id, shift_id, measurement_id, specimen, first_beat, last_beat, original
                   ) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (piece_id) DO NOTHING''',
                (envelope.piece_id, envelope.shift_id, envelope.measurement_id, coverage.specimen,
                 str(coverage.first), str(coverage.last), verified.original),
            )
            row = self.connection.execute(
                '''SELECT id, piece_id, shift_id, measurement_id, specimen,
                          first_beat, last_beat, original
                   FROM evidence_receipts WHERE piece_id = ?''',
                (envelope.piece_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError('verified piece was not registered')
            receipt = self._receipt(row)
            if read_envelope(receipt.original).body != envelope.body:
                raise ValueError('piece identity conflicts with a registered original')
        return receipt

    def get_receipt(self, receipt_id: int) -> Receipt | None:
        if type(receipt_id) is not int or not 0 < receipt_id < 2**63:
            return None
        row = self.connection.execute(
            '''SELECT id, piece_id, shift_id, measurement_id, specimen,
                      first_beat, last_beat, original
               FROM evidence_receipts WHERE id = ?''',
            (receipt_id,),
        ).fetchone()
        return None if row is None else self._receipt(row)
