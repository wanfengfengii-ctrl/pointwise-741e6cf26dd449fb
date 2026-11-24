import json
import sqlite3
from dataclasses import dataclass

from report.account import FatigueAccount, decode_account, encode_account
from report.provenance import ParentEvidence, decode_parents, encode_parents


@dataclass(frozen=True)
class StoredReport:
    report_id: int
    specimen: str
    account: FatigueAccount
    parents: tuple[ParentEvidence, ...]


@dataclass(frozen=True)
class SigningReceipt:
    signing_id: int
    report_id: int


class ReportRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS fatigue_reports (
                id INTEGER PRIMARY KEY,
                specimen TEXT NOT NULL,
                account TEXT NOT NULL,
                parents TEXT NOT NULL
            )
        ''')
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS signing_receipts (
                id INTEGER PRIMARY KEY,
                report_id INTEGER UNIQUE NOT NULL REFERENCES fatigue_reports (id)
            )
        ''')

    def store_report(
        self, account: FatigueAccount, parents: tuple[ParentEvidence, ...]
    ) -> StoredReport:
        if not self.connection.in_transaction:
            raise RuntimeError('report writes require a publication transaction')
        if not parents:
            raise ValueError('report requires parent evidence')
        specimen = parents[0].coverage.specimen
        cursor = self.connection.execute(
            'INSERT INTO fatigue_reports (specimen, account, parents) VALUES (?, ?, ?)',
            (specimen, json.dumps(encode_account(account)), json.dumps(encode_parents(parents))),
        )
        return StoredReport(cursor.lastrowid, specimen, account, parents)

    def store_signing_receipt(self, report_id: int) -> SigningReceipt:
        if not self.connection.in_transaction:
            raise RuntimeError('receipt writes require a publication transaction')
        cursor = self.connection.execute(
            'INSERT INTO signing_receipts (report_id) VALUES (?)', (report_id,)
        )
        return SigningReceipt(cursor.lastrowid, report_id)

    def read_published(self, report_id: int) -> tuple[StoredReport, SigningReceipt] | None:
        if type(report_id) is not int or not 0 < report_id < 2**63:
            return None
        row = self.connection.execute(
            '''SELECT r.specimen, r.account, r.parents, s.id
               FROM fatigue_reports AS r
               JOIN signing_receipts AS s ON s.report_id = r.id
               WHERE r.id = ?''',
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        specimen, account, parents, signing_id = row
        report = StoredReport(
            report_id, specimen, decode_account(json.loads(account)), decode_parents(json.loads(parents))
        )
        return report, SigningReceipt(signing_id, report_id)
