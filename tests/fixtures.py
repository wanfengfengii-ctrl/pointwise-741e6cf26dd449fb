import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from evidence.archive import EvidenceArchive
from evidence.issuer import issue_dwell_evidence, issue_evidence
from intake.accept import accept_evidence
from intake.catalog import ReceiptCatalog
from report.assemble import assemble_report
from report.publication import get_report
from report.repository import ReportRepository
from report.retest import RetestRepository, assemble_retest_sheet, get_retest_sheet
from shift.repository import ShiftRepository
from shift.revision import freeze_shift
from source.correction import correct_measurements
from source.record import record_measurements
from source.repository import MeasurementRepository


STATION_TABLES = ('measurement_revisions', 'measurement_samples', 'frozen_shifts', 'issued_evidence')
CENTER_TABLES = ('evidence_receipts', 'fatigue_reports', 'signing_receipts')
RETEST_TABLES = ('retest_sheets', 'retest_signings')


def sample_file(name):
    path = Path(__file__).resolve().parents[1] / 'examples' / name
    return json.loads(path.read_text(encoding='utf-8'))


def account_view(account):
    return {
        'ranges': [[str(row.amplitude), row.full, row.half] for row in account.ranges],
        'full_cycles': [
            [str(cycle.amplitude), cycle.first_beat, cycle.last_beat]
            for cycle in account.full_cycles
        ],
    }


def entry_view(entry):
    return {
        'amplitude': str(entry.amplitude),
        'first': [entry.first_beat, str(entry.first_load)],
        'last': [entry.last_beat, str(entry.last_load)],
        'dwell': [entry.dwell.first, entry.dwell.last, str(entry.dwell.load), entry.dwell.count],
        'source_receipts': [source.receipt_id for source in entry.sources],
    }


def sheet_view(sheet):
    return {
        'min_amplitude': str(sheet.min_amplitude),
        'min_dwell': sheet.min_dwell,
        'entries': [entry_view(entry) for entry in sheet.entries],
    }


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': code_paths, 'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))


class Lab:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.station = None
        self.center = None

    def open_station(self):
        self.station = sqlite3.connect(self.directory / 'station.sqlite')
        self.station.execute('PRAGMA foreign_keys = ON')
        self.measurements = MeasurementRepository(self.station)
        self.shifts = ShiftRepository(self.station)
        self.archive = EvidenceArchive(self.station)
        self.initialize_station()

    def initialize_station(self):
        self.measurements.initialize()
        self.shifts.initialize()
        self.archive.initialize()

    def open_center(self):
        self.center = sqlite3.connect(self.directory / 'center.sqlite')
        self.center.execute('PRAGMA foreign_keys = ON')
        self.catalog = ReceiptCatalog(self.center)
        self.reports = ReportRepository(self.center)
        self.retest = RetestRepository(self.center)
        self.initialize_center()

    def initialize_center(self):
        self.catalog.initialize()
        self.reports.initialize()
        self.retest.initialize()

    def close_station(self):
        if self.station is not None:
            self.station.close()
            self.station = None

    def close_center(self):
        if self.center is not None:
            self.center.close()
            self.center = None

    def close(self):
        self.close_station()
        self.close_center()

    def record(self, specimen, first, loads):
        return record_measurements(self.measurements, specimen, enumerate(loads, start=first))

    def correct(self, specimen, parent_id, changes):
        return correct_measurements(self.measurements, specimen, parent_id, changes)

    def freeze(self, specimen, revision_id, first, last):
        return freeze_shift(self.measurements, self.shifts, specimen, revision_id, first, last)

    def issue(self, shift_id):
        return issue_evidence(self.measurements, self.shifts, self.archive, shift_id)

    def issue_dwell(self, shift_id):
        return issue_dwell_evidence(self.measurements, self.shifts, self.archive, shift_id)

    def accept(self, original):
        return accept_evidence(self.catalog, original)

    def receive_shift(self, specimen, revision_id, first, last):
        frozen = self.freeze(specimen, revision_id, first, last)
        return self.accept(self.issue(frozen.shift_id))

    def receive_dwell_shift(self, specimen, revision_id, first, last):
        frozen = self.freeze(specimen, revision_id, first, last)
        return self.accept(self.issue_dwell(frozen.shift_id))

    def publish(self, receipt_ids, **options):
        return assemble_report(self.catalog, self.reports, receipt_ids, **options)

    def receive_report(self, report_id):
        return get_report(self.reports, self.catalog, report_id)

    def publish_sheet(self, receipt_ids, min_amplitude, min_dwell, **options):
        return assemble_retest_sheet(
            self.catalog, self.retest, receipt_ids, min_amplitude, min_dwell, **options
        )

    def receive_sheet(self, sheet_id):
        return get_retest_sheet(self.retest, self.catalog, sheet_id)

    def station_counts(self):
        return tuple(self.station.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                     for table in STATION_TABLES)

    def center_counts(self):
        return tuple(self.center.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                     for table in CENTER_TABLES)

    def sheet_counts(self):
        return tuple(self.center.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                     for table in RETEST_TABLES)


class LabTestCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='fatigue-lab-')
        self.addCleanup(temporary.cleanup)
        self.lab = Lab(temporary.name)
        self.addCleanup(self.lab.close)
        self.lab.open_station()
        self.lab.open_center()
