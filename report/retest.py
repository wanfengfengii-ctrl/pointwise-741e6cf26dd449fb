import json
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fractions import Fraction

from evidence.body import decode_dwell_body
from evidence.envelope import read_envelope
from intake.catalog import Receipt, ReceiptCatalog
from intake.selection import select_receipts
from report.dwell import RetestEntry, collect_entries, decode_entries, encode_entries, merge_runs
from report.provenance import ParentEvidence, bind_parents, decode_parents, encode_parents
from source.load_value import encode_load, parse_load


class UnverifiableDwellError(ValueError):
    """The selection mixes pieces that cannot verify dwell; pending lists the receipt ids."""

    def __init__(self, pending: Iterable[int]):
        self.pending = tuple(pending)
        super().__init__(
            'selection cannot verify dwell; supplement receipts: ' + ', '.join(map(str, self.pending))
        )


@dataclass(frozen=True)
class StoredSheet:
    sheet_id: int
    specimen: str
    min_amplitude: Fraction
    min_dwell: int
    entries: tuple[RetestEntry, ...]
    parents: tuple[ParentEvidence, ...]


@dataclass(frozen=True)
class SheetSigning:
    signing_id: int
    sheet_id: int


@dataclass(frozen=True)
class PublishedSheet:
    sheet: StoredSheet
    signing: SheetSigning
    originals: tuple[Receipt, ...]


class RetestRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS retest_sheets (
                id INTEGER PRIMARY KEY,
                specimen TEXT NOT NULL,
                min_amplitude TEXT NOT NULL,
                min_dwell TEXT NOT NULL,
                entries TEXT NOT NULL,
                parents TEXT NOT NULL
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS retest_signings (
                id INTEGER PRIMARY KEY,
                sheet_id INTEGER UNIQUE NOT NULL REFERENCES retest_sheets (id)
            )
        ''')

    def store_sheet(
        self,
        min_amplitude: Fraction,
        min_dwell: int,
        entries: tuple[RetestEntry, ...],
        parents: tuple[ParentEvidence, ...],
    ) -> StoredSheet:
        if not self.connection.in_transaction:
            raise RuntimeError('sheet writes require a publication transaction')
        if not parents:
            raise ValueError('sheet requires parent evidence')
        specimen = parents[0].coverage.specimen
        cursor = self.connection.execute(
            'INSERT INTO retest_sheets (specimen, min_amplitude, min_dwell, entries, parents) '
            'VALUES (?, ?, ?, ?, ?)',
            (specimen, encode_load(min_amplitude), str(min_dwell),
             json.dumps(encode_entries(entries)), json.dumps(encode_parents(parents))),
        )
        return StoredSheet(cursor.lastrowid, specimen, min_amplitude, min_dwell, entries, parents)

    def store_signing(self, sheet_id: int) -> SheetSigning:
        if not self.connection.in_transaction:
            raise RuntimeError('signing writes require a publication transaction')
        cursor = self.connection.execute(
            'INSERT INTO retest_signings (sheet_id) VALUES (?)', (sheet_id,)
        )
        return SheetSigning(cursor.lastrowid, sheet_id)

    def read_sheet(self, sheet_id: int) -> tuple[StoredSheet, SheetSigning] | None:
        if type(sheet_id) is not int or not 0 < sheet_id < 2**63:
            return None
        row = self.connection.execute(
            '''SELECT s.specimen, s.min_amplitude, s.min_dwell, s.entries, s.parents, g.id
               FROM retest_sheets AS s
               JOIN retest_signings AS g ON g.sheet_id = s.id
               WHERE s.id = ?''',
            (sheet_id,),
        ).fetchone()
        if row is None:
            return None
        specimen, min_amplitude, min_dwell, entries, parents, signing_id = row
        sheet = StoredSheet(
            sheet_id, specimen, parse_load(min_amplitude), int(min_dwell),
            decode_entries(json.loads(entries)), decode_parents(json.loads(parents)),
        )
        return sheet, SheetSigning(signing_id, sheet_id)


def _require_min_amplitude(value: object) -> Fraction:
    amplitude = parse_load(value)
    if amplitude < 0:
        raise ValueError('amplitude threshold must be nonnegative')
    return amplitude


def _require_min_dwell(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError('dwell threshold must be a positive integer')
    return value


def assemble_retest_sheet(
    catalog: ReceiptCatalog,
    repository: RetestRepository,
    receipt_ids: Iterable[int],
    min_amplitude: object,
    min_dwell: object,
    *,
    after_sheet_write: Callable[[StoredSheet], None] | None = None,
) -> PublishedSheet:
    """Sign one high-load dwell retest sheet from immutable center receipts only."""
    if repository.connection is not catalog.connection:
        raise ValueError('sheets and receipts must use the same center connection')
    min_amplitude = _require_min_amplitude(min_amplitude)
    min_dwell = _require_min_dwell(min_dwell)
    receipts = select_receipts(catalog, receipt_ids)
    bodies = []
    pending = []
    for receipt in receipts:
        envelope = read_envelope(receipt.original)
        if envelope.version != 2:
            pending.append(receipt.receipt_id)
        else:
            bodies.append(decode_dwell_body(envelope.body))
    if pending:
        raise UnverifiableDwellError(pending)
    runs = merge_runs(body.runs for body in bodies)
    parents = bind_parents(receipts)
    entries = collect_entries(runs, parents, min_amplitude, min_dwell)
    connection = repository.connection
    if connection.in_transaction:
        raise RuntimeError('sheet publication requires an idle center connection')
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        sheet = repository.store_sheet(min_amplitude, min_dwell, entries, parents)
        if after_sheet_write is not None:
            after_sheet_write(sheet)
        signing = repository.store_signing(sheet.sheet_id)
    return PublishedSheet(sheet, signing, receipts)


def get_retest_sheet(
    repository: RetestRepository, catalog: ReceiptCatalog, sheet_id: int
) -> PublishedSheet | None:
    if repository.connection is not catalog.connection:
        raise ValueError('sheets and receipts must use the same center connection')
    published = repository.read_sheet(sheet_id)
    if published is None:
        return None
    sheet, signing = published
    originals = []
    for parent in sheet.parents:
        original = catalog.get_receipt(parent.receipt_id)
        if original is None:
            raise ValueError('signed sheet is missing an original receipt')
        originals.append(original)
    originals = tuple(originals)
    if bind_parents(originals) != sheet.parents:
        raise ValueError('original receipts conflict with the signed provenance')
    return PublishedSheet(sheet, signing, originals)
