from source.record import record_measurements
from tests.fixtures import LabTestCase, account_view, sample_file, scenario


class HistoryTests(LabTestCase):
    def _publish_versions(self):
        bench = sample_file('bench.json')
        changes = sample_file('correction.json')['changes']
        specimen = bench['specimen']
        revision = record_measurements(self.lab.measurements, specimen, bench['samples'])
        left = self.lab.freeze(specimen, revision, 1, bench['cut'])
        right = self.lab.freeze(specimen, revision, bench['cut'] + 1, 6)
        left_piece, old_piece = self.lab.issue(left.shift_id), self.lab.issue(right.shift_id)
        left_id, old_id = self.lab.accept(left_piece), self.lab.accept(old_piece)
        self.lab.close_station()
        old = self.lab.publish([left_id, old_id])

        self.lab.open_station()
        revised = self.lab.correct(specimen, revision, changes)
        new_shift = self.lab.freeze(specimen, revised, bench['cut'] + 1, 6)
        new_piece = self.lab.issue(new_shift.shift_id)
        new_id = self.lab.accept(new_piece)
        self.assertNotEqual(new_id, old_id)
        self.assertEqual(self.lab.issue(right.shift_id), old_piece)
        self.lab.close_station()
        new = self.lab.publish([left_id, new_id])
        self.assertEqual(tuple(parent.receipt_id for parent in old.report.parents), (left_id, old_id))
        self.assertEqual(tuple(parent.receipt_id for parent in new.report.parents), (left_id, new_id))
        self.assertEqual(old.report.parents[1].measurement_id, revision)
        self.assertEqual(new.report.parents[1].measurement_id, revised)
        return bench, changes, old, new, (left_piece, old_piece, new_piece)

    def test_correct_and_reopen(self):
        bench, changes, old, new, pieces = self._publish_versions()
        expected = [
            {'ranges': [['2', 1, 0], ['6', 0, 1]], 'full_cycles': [['2', 2, 5]]},
            {'ranges': [['2', 0, 1], ['4', 0, 1], ['6', 0, 1]], 'full_cycles': []},
        ]
        self.assertEqual([account_view(old.report.account), account_view(new.report.account)], expected)
        self.assertNotEqual(old.report.report_id, new.report.report_id)
        self.assertNotEqual(old.signing_receipt.signing_id, new.signing_receipt.signing_id)
        self.assertEqual(self.lab.center_counts(), (3, 2, 2))
        self.lab.close_center()
        self.lab.open_center()
        received_old = self.lab.receive_report(old.report.report_id)
        received_new = self.lab.receive_report(new.report.report_id)
        self.assertEqual((received_old, received_new), (old, new))
        left_piece, old_piece, new_piece = pieces
        wanted_originals = [(left_piece, old_piece), (left_piece, new_piece)]
        actual_originals = [tuple(entry.original for entry in item.originals) for item in (received_old, received_new)]
        self.assertEqual(actual_originals, wanted_originals)
        downstream_expected = {'records': [3, 2, 2], 'kept_originals': True, 'kept_signing_receipts': True}
        downstream_actual = {
            'records': list(self.lab.center_counts()),
            'kept_originals': actual_originals == wanted_originals,
            'kept_signing_receipts': (received_old.signing_receipt, received_new.signing_receipt)
            == (old.signing_receipt, new.signing_receipt),
        }
        self.assertEqual(downstream_actual, downstream_expected)
        scenario(
            'T8', {'bench': bench, 'changes': changes}, expected,
            [account_view(received_old.report.account), account_view(received_new.report.account)],
            downstream_expected, downstream_actual,
            ['source/correction.py', 'evidence/issuer.py', 'intake/catalog.py',
             'report/assemble.py', 'report/publication.py', 'report/repository.py'],
            'The old four-point window has differences 4, 2, 4. After correction the differences are 6, 4, 2, so none is removed. Originals are compared with the three pieces issued before publication.',
        )

    def test_repeat_init(self):
        _, _, old, new, _ = self._publish_versions()
        self.lab.open_station()
        station_before = self.lab.station_counts()
        center_before = self.lab.center_counts()
        self.assertEqual(station_before, (2, 12, 3, 3))
        self.assertEqual(center_before, (3, 2, 2))
        for _ in range(2):
            self.lab.initialize_station()
            self.lab.initialize_center()
        self.lab.close()
        self.lab.open_station()
        self.lab.open_center()
        self.assertEqual(self.lab.station_counts(), station_before)
        self.assertEqual(self.lab.center_counts(), center_before)
        for published in (old, new):
            self.assertEqual(self.lab.receive_report(published.report.report_id), published)
            for original in published.originals:
                self.assertEqual(self.lab.archive.get_by_piece(original.piece_id), original.original)
        for published, tail_values in [(old, [4, 2, 6]), (new, [6, 2, 4])]:
            origin = self.lab.measurements.get_revision(published.report.parents[1].measurement_id)
            self.assertEqual([sample.load for sample in origin.samples[3:]], tail_values)

    def test_unknown_report(self):
        revision = self.lab.record('S', 1, [0, 2])
        parent = self.lab.receive_shift('S', revision, 1, 2)
        self.lab.close_station()
        existing = self.lab.publish([parent])
        before = self.lab.center_counts()
        self.assertIsNone(self.lab.receive_report(existing.report.report_id + 1000))
        self.assertEqual(self.lab.center_counts(), before)
        self.assertEqual(self.lab.receive_report(existing.report.report_id), existing)
