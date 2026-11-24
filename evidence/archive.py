import sqlite3

from evidence.envelope import read_envelope


class EvidenceArchive:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS issued_evidence (
                shift_id TEXT PRIMARY KEY NOT NULL REFERENCES frozen_shifts (id),
                piece_id TEXT UNIQUE NOT NULL,
                original TEXT NOT NULL
            )
        ''')

    def get_by_shift(self, shift_id: str) -> str | None:
        if not isinstance(shift_id, str):
            return None
        row = self.connection.execute(
            'SELECT original FROM issued_evidence WHERE shift_id = ?', (shift_id,)
        ).fetchone()
        return None if row is None else row[0]

    def get_by_piece(self, piece_id: str) -> str | None:
        if not isinstance(piece_id, str):
            return None
        row = self.connection.execute(
            'SELECT original FROM issued_evidence WHERE piece_id = ?', (piece_id,)
        ).fetchone()
        return None if row is None else row[0]

    def put_original(self, original: str) -> str:
        envelope = read_envelope(original)
        if self.connection.in_transaction:
            raise RuntimeError('issuance requires an idle station connection')
        with self.connection:
            self.connection.execute(
                '''INSERT INTO issued_evidence VALUES (?, ?, ?)
                   ON CONFLICT (shift_id) DO NOTHING''',
                (envelope.shift_id, envelope.piece_id, original),
            )
            archived = self.get_by_shift(envelope.shift_id)
            if archived is None:
                raise RuntimeError('issued original was not archived')
        return archived
