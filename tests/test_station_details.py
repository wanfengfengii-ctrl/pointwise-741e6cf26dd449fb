from fractions import Fraction

from evidence.body import decode_evidence_body
from evidence.envelope import read_envelope
from source.record import record_measurements
from tests.fixtures import LabTestCase, account_view


class StationDetailsTests(LabTestCase):
    def test_exact_load(self):
        revision_id = self.lab.record('R', 1, [0, '4/3', '2/3', 2])
        self.lab.close_station()
        self.lab.open_station()
        revision = self.lab.measurements.get_revision(revision_id)
        self.assertEqual([sample.load for sample in revision.samples],
                         [Fraction(0), Fraction(4, 3), Fraction(2, 3), Fraction(2)])
        self.assertTrue(all(isinstance(sample.load, Fraction) for sample in revision.samples))
        account = self.lab.freeze('R', revision_id, 1, 4).account
        self.assertEqual(account.ranges[0].amplitude, Fraction(2, 3))
        self.assertEqual(account_view(account), {
            'ranges': [['2/3', 1, 0], ['2', 0, 1]], 'full_cycles': [['2/3', 2, 3]],
        })

    def test_atomic_ingest(self):
        prior = self.lab.record('R', 1, [0])
        existing = self.lab.measurements.get_revision(prior)
        before = self.lab.station_counts()
        for invalid in ([], [(1, 0), (2, '')], [(1, 0), (1, 2)], [(2, 0), (1, 2)],
                        [(1, 0), (2, '1/0')], [(1, 0), (2, 0.5)], [(True, 2)]):
            with self.subTest(rows=invalid):
                with self.assertRaises(ValueError):
                    record_measurements(self.lab.measurements, 'R', iter(invalid))
                self.assertEqual(self.lab.station_counts(), before)
        self.assertEqual(self.lab.measurements.get_revision(prior), existing)

    def test_invalid_correction(self):
        source = self.lab.record('R', 4, [4, 2, 6])
        frozen = self.lab.freeze('R', source, 4, 6)
        before = self.lab.station_counts()
        for specimen, parent, changes in [
            ('R', 'missing', [(4, 6)]), ('OTHER', source, [(4, 6)]),
            ('R', source, [(4, 6), (7, 2)]), ('R', source, [(4, 6), (6, None)]),
        ]:
            with self.subTest(specimen=specimen, parent=parent, changes=changes):
                with self.assertRaises(ValueError):
                    self.lab.correct(specimen, parent, changes)
                self.assertEqual(self.lab.station_counts(), before)
        self.assertEqual(self.lab.shifts.get_frozen(frozen.shift_id), frozen)
        self.assertEqual([sample.load for sample in self.lab.measurements.get_revision(source).samples], [4, 2, 6])

    def test_fixed_reissue(self):
        source = self.lab.record('R', 1, [0, 1, 1, 3, 4])
        frozen = self.lab.freeze('R', source, 1, 5)
        original = self.lab.issue(frozen.shift_id)
        envelope = read_envelope(original)
        body = decode_evidence_body(envelope.body)
        self.assertEqual([(point.beat, point.load) for point in body.points], [(1, 0), (5, 4)])
        self.lab.close_station()
        self.lab.open_station()
        self.assertEqual(self.lab.issue(frozen.shift_id), original)
        self.assertEqual(self.lab.archive.get_by_shift(frozen.shift_id), original)
        self.assertEqual(self.lab.archive.get_by_piece(envelope.piece_id), original)
        self.assertEqual(self.lab.station_counts(), (1, 5, 1, 1))

    def test_unknown_shift(self):
        source = self.lab.record('R', 1, [0, 2])
        actual = self.lab.freeze('R', source, 1, 2)
        self.lab.issue(actual.shift_id)
        before = self.lab.station_counts()
        with self.assertRaisesRegex(ValueError, 'unknown frozen shift'):
            self.lab.issue('missing-shift')
        self.assertEqual(self.lab.station_counts(), before)
        self.assertIsNone(self.lab.archive.get_by_shift('missing-shift'))

    def test_evidence_preserves_order(self):
        first = self.lab.record('R', 4, [4, 2, 6])
        second = self.lab.record('R', 4, [6, 2, 4])
        expected = {'ranges': [['2', 0, 1], ['4', 0, 1]], 'full_cycles': []}
        for revision, loads in [(first, [4, 2, 6]), (second, [6, 2, 4])]:
            with self.subTest(loads=loads):
                frozen = self.lab.freeze('R', revision, 4, 6)
                envelope = read_envelope(self.lab.issue(frozen.shift_id))
                body = decode_evidence_body(envelope.body)
                self.assertEqual(account_view(body.local_account), expected)
                self.assertEqual([(point.beat, point.load) for point in body.points],
                                 list(zip([4, 5, 6], loads)))
                self.assertEqual((body.shift_id, body.measurement_id), (frozen.shift_id, revision))
                self.assertEqual((body.coverage.specimen, body.coverage.first, body.coverage.last), ('R', 4, 6))

    def test_source_snapshot_and_frozen_origin(self):
        old_id = self.lab.record('R', 4, [4, 2, 6])
        old_shift = self.lab.freeze('R', old_id, 4, 6)
        new_id = self.lab.correct('R', old_id, [(4, 6), (6, 4)])
        new_shift = self.lab.freeze('R', new_id, 4, 6)
        self.assertEqual(self.lab.station_counts()[3], 0)
        self.lab.close_station()
        self.lab.open_station()
        old = self.lab.measurements.get_revision(old_id)
        new = self.lab.measurements.get_revision(new_id)
        self.assertIsNone(old.parent_id)
        self.assertEqual(new.parent_id, old_id)
        self.assertEqual(self.lab.shifts.get_frozen(old_shift.shift_id).measurement_id, old_id)
        self.assertEqual(self.lab.shifts.get_frozen(new_shift.shift_id).measurement_id, new_id)
        for source, frozen, loads in [(old, old_shift, [4, 2, 6]), (new, new_shift, [6, 2, 4])]:
            with self.subTest(loads=loads):
                expected = list(zip([4, 5, 6], loads))
                self.assertEqual([(sample.beat, sample.load) for sample in source.samples], expected)
                envelope = read_envelope(self.lab.issue(frozen.shift_id))
                body = decode_evidence_body(envelope.body)
                self.assertEqual(envelope.measurement_id, source.revision_id)
                self.assertEqual(body.measurement_id, source.revision_id)
                self.assertEqual(body.shift_id, frozen.shift_id)
                self.assertEqual([(point.beat, point.load) for point in body.points], expected)
