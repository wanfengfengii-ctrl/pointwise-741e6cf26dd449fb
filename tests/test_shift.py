from source.record import record_measurements
from tests.fixtures import LabTestCase, account_view, scenario


class ShiftTests(LabTestCase):
    def test_local_account(self):
        loads = [0, 4, 2, 6]
        revision = self.lab.record('S', 1, loads)
        frozen = self.lab.freeze('S', revision, 1, 4)
        expected = {'ranges': [['2', 1, 0], ['6', 0, 1]], 'full_cycles': [['2', 2, 3]]}
        self.assertEqual(account_view(frozen.account), expected)
        stored = self.lab.shifts.get_frozen(frozen.shift_id)
        self.assertEqual(stored, frozen)
        self.assertEqual(stored.measurement_id, revision)
        scenario(
            'T1', {'loads_kn': loads, 'coverage': [1, 4]}, expected, account_view(frozen.account),
            {'same_revision': True, 'stored_account': expected},
            {'same_revision': stored.measurement_id == revision, 'stored_account': account_view(stored.account)},
            ['shift/revision.py', 'shift/local_account.py', 'report/cycles.py', 'shift/repository.py'],
            'Adjacent differences are 4, 2 and 4. Removing beats 2 and 3 leaves a range of 6.',
        )

    def test_gap(self):
        revision = record_measurements(self.lab.measurements, 'GAP', [(1, 0), (2, 4), (4, 6)])
        before = self.lab.station_counts()
        with self.assertRaisesRegex(ValueError, 'missing original beats'):
            self.lab.freeze('GAP', revision, 1, 4)
        self.assertEqual(self.lab.station_counts(), before)
        self.assertEqual([sample.beat for sample in self.lab.measurements.get_revision(revision).samples],
                         [1, 2, 4])

    def test_invalid_binding(self):
        revision = self.lab.record('S', 1, [0, 2, 4])
        before = self.lab.station_counts()
        for specimen, source, first, last in [
            ('OTHER', revision, 1, 3), ('S', 'unknown', 1, 3),
            ('S', revision, 3, 1), ('S', revision, 0, 2), ('S', revision, 1, 4),
        ]:
            with self.subTest(specimen=specimen, revision=source, first=first, last=last):
                with self.assertRaises(ValueError):
                    self.lab.freeze(specimen, source, first, last)
                self.assertEqual(self.lab.station_counts(), before)
