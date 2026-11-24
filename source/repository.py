import sqlite3
from uuid import uuid4

from source.load_value import encode_load, parse_load
from source.series import MeasurementRevision, Sample


class MeasurementRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS measurement_revisions (
                id TEXT PRIMARY KEY NOT NULL,
                specimen TEXT NOT NULL,
                parent_id TEXT,
                UNIQUE (id, specimen),
                FOREIGN KEY (parent_id, specimen)
                    REFERENCES measurement_revisions (id, specimen)
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS measurement_samples (
                revision_id TEXT NOT NULL REFERENCES measurement_revisions (id),
                position INTEGER NOT NULL,
                beat TEXT NOT NULL,
                load TEXT NOT NULL,
                PRIMARY KEY (revision_id, position),
                UNIQUE (revision_id, beat)
            )
        ''')

    def append_revision(
        self, specimen: str, samples: tuple[Sample, ...], *, parent_id: str | None = None
    ) -> str:
        """Persist a validated snapshot in one station transaction."""
        revision_id = uuid4().hex
        rows = [
            (revision_id, position, str(sample.beat), encode_load(sample.load))
            for position, sample in enumerate(samples)
        ]
        if self.connection.in_transaction:
            raise RuntimeError('recording requires an idle station connection')
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            self.connection.execute(
                'INSERT INTO measurement_revisions VALUES (?, ?, ?)',
                (revision_id, specimen, parent_id),
            )
            self.connection.executemany(
                'INSERT INTO measurement_samples VALUES (?, ?, ?, ?)', rows
            )
        return revision_id

    def get_revision(self, revision_id: str) -> MeasurementRevision | None:
        if not isinstance(revision_id, str):
            return None
        header = self.connection.execute(
            'SELECT specimen, parent_id FROM measurement_revisions WHERE id = ?',
            (revision_id,),
        ).fetchone()
        if header is None:
            return None
        rows = self.connection.execute(
            '''SELECT beat, load FROM measurement_samples
               WHERE revision_id = ? ORDER BY position''',
            (revision_id,),
        )
        samples = tuple(Sample(int(beat), parse_load(load)) for beat, load in rows)
        return MeasurementRevision(revision_id, header[0], header[1], samples)
