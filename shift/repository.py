import json
import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from report.account import FatigueAccount, decode_account, encode_account
from shift.window import ShiftWindow


@dataclass(frozen=True)
class FrozenShift:
    shift_id: str
    measurement_id: str
    window: ShiftWindow
    account: FatigueAccount


class ShiftRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''
            CREATE TABLE IF NOT EXISTS frozen_shifts (
                id TEXT PRIMARY KEY NOT NULL,
                measurement_id TEXT NOT NULL,
                specimen TEXT NOT NULL,
                first_beat TEXT NOT NULL,
                last_beat TEXT NOT NULL,
                account TEXT NOT NULL,
                FOREIGN KEY (measurement_id, specimen)
                    REFERENCES measurement_revisions (id, specimen)
            )
        ''')

    def store_frozen(
        self, measurement_id: str, window: ShiftWindow, account: FatigueAccount
    ) -> FrozenShift:
        if self.connection.in_transaction:
            raise RuntimeError('freezing requires an idle station connection')
        shift_id = uuid4().hex
        with self.connection:
            self.connection.execute(
                'INSERT INTO frozen_shifts VALUES (?, ?, ?, ?, ?, ?)',
                (shift_id, measurement_id, window.specimen, str(window.first),
                 str(window.last), json.dumps(encode_account(account))),
            )
        return FrozenShift(shift_id, measurement_id, window, account)

    def get_frozen(self, shift_id: str) -> FrozenShift | None:
        if not isinstance(shift_id, str):
            return None
        row = self.connection.execute(
            '''SELECT measurement_id, specimen, first_beat, last_beat, account
               FROM frozen_shifts WHERE id = ?''',
            (shift_id,),
        ).fetchone()
        if row is None:
            return None
        measurement_id, specimen, first, last, account = row
        return FrozenShift(
            shift_id, measurement_id, ShiftWindow(specimen, int(first), int(last)),
            decode_account(json.loads(account)),
        )
