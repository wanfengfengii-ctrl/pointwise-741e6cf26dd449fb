import json
from fractions import Fraction

from evidence.body import decode_dwell_body
from evidence.envelope import canonical_json, piece_identity, read_envelope
from report.retest import UnverifiableDwellError
from tests.fixtures import LabTestCase, account_view, entry_view, scenario, sheet_view


class SheetInterrupted(Exception):
    pass


class RetestSheetTests(LabTestCase):
    def _cross_seam_selection(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 2, 6])
        left = self.lab.receive_dwell_shift('S', revision, 1, 3)
        right = self.lab.receive_dwell_shift('S', revision, 4, 6)
        return revision, left, right

    def test_cross_seam_dwell(self):
        revision, left, right = self._cross_seam_selection()
        self.lab.close_station()
        published = self.lab.publish_sheet([left, right], 2, 3)
        self.assertEqual(published.sheet.specimen, 'S')
        self.assertEqual((published.sheet.min_amplitude, published.sheet.min_dwell), (Fraction(2), 3))
        self.assertEqual(len(published.sheet.entries), 1)
        entry = published.sheet.entries[0]
        self.assertEqual((entry.amplitude, entry.first_beat, entry.last_beat), (Fraction(2), 2, 5))
        self.assertEqual((entry.first_load, entry.last_load), (Fraction(4), Fraction(2)))
        self.assertEqual(
            (entry.dwell.load, entry.dwell.first, entry.dwell.last, entry.dwell.count),
            (Fraction(4), 2, 4, 3),
        )
        self.assertEqual(tuple(source.receipt_id for source in entry.sources), (left, right))
        self.assertEqual(
            tuple(source.shift_id for source in entry.sources),
            tuple(self.lab.catalog.get_receipt(receipt).shift_id for receipt in (left, right)),
        )
        self.assertEqual(
            tuple(source.measurement_id for source in entry.sources), (revision, revision)
        )
        self.assertEqual(tuple(parent.receipt_id for parent in published.sheet.parents), (left, right))
        # both thresholds are inclusive; raising either one excludes the cycle
        self.assertEqual(self.lab.publish_sheet([left, right], 2, 4).sheet.entries, ())
        self.assertEqual(self.lab.publish_sheet([left, right], 3, 3).sheet.entries, ())
        # the whole-record account settles the same cycles from V2 pieces
        report = self.lab.publish([left, right])
        self.assertEqual(account_view(report.report.account), {
            'ranges': [['2', 1, 0], ['6', 0, 1]], 'full_cycles': [['2', 2, 5]],
        })
        # the signed sheet is retrievable by its number after reopening the center
        sheet_id = published.sheet.sheet_id
        self.lab.close_center()
        self.lab.open_center()
        self.assertEqual(self.lab.receive_sheet(sheet_id), published)
        self.assertEqual(self.lab.sheet_counts(), (3, 3))

    def test_three_piece_seam(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 4, 2, 6])
        first = self.lab.receive_dwell_shift('S', revision, 1, 2)
        middle = self.lab.receive_dwell_shift('S', revision, 3, 4)
        last = self.lab.receive_dwell_shift('S', revision, 5, 7)
        self.lab.close_station()
        published = self.lab.publish_sheet([first, middle, last], 2, 4)
        self.assertEqual(len(published.sheet.entries), 1)
        entry = published.sheet.entries[0]
        self.assertEqual((entry.amplitude, entry.first_beat, entry.last_beat), (Fraction(2), 2, 6))
        self.assertEqual((entry.dwell.first, entry.dwell.last, entry.dwell.count), (2, 5, 4))
        self.assertEqual(
            tuple(source.receipt_id for source in entry.sources), (first, middle, last)
        )

    def test_revision_shortens_dwell(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 4, 2, 6])
        left = self.lab.receive_dwell_shift('S', revision, 1, 4)
        right = self.lab.receive_dwell_shift('S', revision, 5, 7)
        self.lab.close_station()
        old = self.lab.publish_sheet([left, right], 2, 4)
        self.assertEqual(len(old.sheet.entries), 1)
        self.assertEqual(
            (old.sheet.entries[0].dwell.first, old.sheet.entries[0].dwell.last,
             old.sheet.entries[0].dwell.count),
            (2, 5, 4),
        )
        self.lab.open_station()
        revised = self.lab.correct('S', revision, [(5, 3)])
        new_left = self.lab.receive_dwell_shift('S', revised, 1, 4)
        new_right = self.lab.receive_dwell_shift('S', revised, 5, 7)
        self.lab.close_station()
        # the shortened dwell no longer meets the original dwell threshold
        strict = self.lab.publish_sheet([new_left, new_right], 2, 4)
        self.assertEqual(strict.sheet.entries, ())
        # adjusting the dwell threshold signs another sheet
        adjusted = self.lab.publish_sheet([new_left, new_right], 2, 3)
        self.assertEqual(len(adjusted.sheet.entries), 1)
        self.assertEqual(adjusted.sheet.entries[0].dwell.count, 3)
        sheet_ids = {old.sheet.sheet_id, strict.sheet.sheet_id, adjusted.sheet.sheet_id}
        self.assertEqual(len(sheet_ids), 3)
        # every signed sheet stays retrievable by its own number after reopening
        self.lab.close_center()
        self.lab.open_center()
        for published in (old, strict, adjusted):
            self.assertEqual(self.lab.receive_sheet(published.sheet.sheet_id), published)
        self.assertEqual(self.lab.receive_sheet(old.sheet.sheet_id).sheet.min_dwell, 4)

    def test_unverifiable_mix(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 2, 6])
        good_left = self.lab.receive_dwell_shift('S', revision, 1, 3)
        good_right = self.lab.receive_dwell_shift('S', revision, 4, 6)
        old_shift = self.lab.freeze('S', revision, 1, 3)
        old_receipt = self.lab.accept(self.lab.issue(old_shift.shift_id))
        self.lab.close_station()
        old_sheet = self.lab.publish_sheet([good_left, good_right], 2, 3)
        # old-version pieces still sign the whole-record fatigue account
        account = self.lab.publish([old_receipt, good_right])
        self.assertEqual(account_view(account.report.account), {
            'ranges': [['2', 1, 0], ['6', 0, 1]], 'full_cycles': [['2', 2, 5]],
        })
        center_before = self.lab.center_counts()
        sheets_before = self.lab.sheet_counts()
        with self.assertRaises(UnverifiableDwellError) as caught:
            self.lab.publish_sheet([old_receipt, good_right], 2, 3)
        self.assertEqual(caught.exception.pending, (old_receipt,))
        # the failed application writes nothing and keeps old pieces and old results
        self.assertEqual(self.lab.center_counts(), center_before)
        self.assertEqual(self.lab.sheet_counts(), sheets_before)
        self.assertEqual(self.lab.receive_sheet(old_sheet.sheet.sheet_id), old_sheet)
        self.assertIsNotNone(self.lab.catalog.get_receipt(old_receipt))
        # the supplement must match the originally selected revision and coverage
        pending = self.lab.catalog.get_receipt(old_receipt)
        self.lab.open_station()
        supplement_shift = self.lab.freeze(
            'S', pending.measurement_id, pending.coverage.first, pending.coverage.last
        )
        supplement = self.lab.accept(self.lab.issue_dwell(supplement_shift.shift_id))
        self.lab.close_station()
        sheet = self.lab.publish_sheet([supplement, good_right], 2, 3)
        self.assertEqual(len(sheet.sheet.entries), 1)
        self.assertEqual(sheet.sheet.entries[0].dwell.count, 3)
        self.assertEqual(self.lab.receive_sheet(sheet.sheet.sheet_id), sheet)

    def test_segments_separate(self):
        revision = self.lab.record('S', 1, [4, 2, 4, 4, 2, 6])
        left = self.lab.receive_dwell_shift('S', revision, 1, 3)
        right = self.lab.receive_dwell_shift('S', revision, 4, 6)
        self.lab.close_station()
        published = self.lab.publish_sheet([left, right], 2, 2)
        self.assertEqual(len(published.sheet.entries), 1)
        entry = published.sheet.entries[0]
        self.assertEqual((entry.amplitude, entry.first_beat, entry.last_beat), (Fraction(2), 2, 3))
        # beat 1 carries the same high load but a different reading sits between,
        # so the dwell interval is only beats 3-4
        self.assertEqual((entry.dwell.first, entry.dwell.last, entry.dwell.count), (3, 4, 2))
        self.assertEqual(tuple(source.receipt_id for source in entry.sources), (left, right))

    def test_half_cycles_excluded(self):
        revision = self.lab.record('S', 1, [0, 6, 6, 6, 0])
        receipt = self.lab.receive_dwell_shift('S', revision, 1, 5)
        self.lab.close_station()
        report = self.lab.publish([receipt])
        self.assertEqual(account_view(report.report.account), {
            'ranges': [['6', 0, 2]], 'full_cycles': [],
        })
        self.assertEqual(self.lab.publish_sheet([receipt], 1, 1).sheet.entries, ())

    def test_settlement_order(self):
        revision = self.lab.record('S', 1, [0, 5, 2, 6, 0, 7])
        left = self.lab.receive_dwell_shift('S', revision, 1, 4)
        right = self.lab.receive_dwell_shift('S', revision, 5, 6)
        self.lab.close_station()
        published = self.lab.publish_sheet([left, right], 1, 1)
        self.assertEqual(
            [(str(entry.amplitude), entry.first_beat, entry.last_beat)
             for entry in published.sheet.entries],
            [('3', 2, 3), ('6', 4, 5)],
        )
        self.assertEqual(
            [(entry.dwell.first, entry.dwell.last, str(entry.dwell.load))
             for entry in published.sheet.entries],
            [(2, 2, '5'), (4, 4, '6')],
        )

    def test_threshold_adjustment_signs_another_sheet(self):
        _, left, right = self._cross_seam_selection()
        self.lab.close_station()
        strict = self.lab.publish_sheet([left, right], 4, 1)
        relaxed = self.lab.publish_sheet([left, right], 2, 3)
        self.assertEqual(strict.sheet.entries, ())
        self.assertEqual(len(relaxed.sheet.entries), 1)
        self.assertNotEqual(strict.sheet.sheet_id, relaxed.sheet.sheet_id)
        self.assertNotEqual(strict.signing.signing_id, relaxed.signing.signing_id)
        self.assertEqual(strict.sheet.parents, relaxed.sheet.parents)
        self.assertEqual(
            (strict.sheet.min_amplitude, relaxed.sheet.min_amplitude), (Fraction(4), Fraction(2))
        )
        self.lab.close_center()
        self.lab.open_center()
        self.assertEqual(self.lab.receive_sheet(strict.sheet.sheet_id), strict)
        self.assertEqual(self.lab.receive_sheet(relaxed.sheet.sheet_id), relaxed)

    def test_unknown_sheet(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 2, 6])
        receipt = self.lab.receive_dwell_shift('S', revision, 1, 5)
        self.lab.close_station()
        existing = self.lab.publish_sheet([receipt], 1, 1)
        before = self.lab.sheet_counts()
        self.assertIsNone(self.lab.receive_sheet(existing.sheet.sheet_id + 1000))
        self.assertEqual(self.lab.sheet_counts(), before)
        self.assertEqual(self.lab.receive_sheet(existing.sheet.sheet_id), existing)

    def test_sheet_rollback(self):
        _, left, right = self._cross_seam_selection()
        self.lab.close_station()
        before = self.lab.sheet_counts()
        attempted = []

        def interrupt(sheet):
            attempted.append(sheet.sheet_id)
            self.assertTrue(self.lab.center.in_transaction)
            self.assertEqual(self.lab.sheet_counts(), (before[0] + 1, before[1]))
            raise SheetInterrupted('interrupted after sheet write')

        with self.assertRaisesRegex(SheetInterrupted, 'after sheet write'):
            self.lab.publish_sheet([left, right], 2, 3, after_sheet_write=interrupt)
        self.assertEqual(len(attempted), 1)
        self.lab.close_center()
        self.lab.open_center()
        self.assertEqual(self.lab.sheet_counts(), before)
        self.assertIsNone(self.lab.receive_sheet(attempted[0]))
        retried = self.lab.publish_sheet([left, right], 2, 3)
        self.assertEqual(len(retried.sheet.entries), 1)
        self.assertEqual(self.lab.receive_sheet(retried.sheet.sheet_id), retried)

    def test_invalid_thresholds(self):
        _, left, right = self._cross_seam_selection()
        self.lab.close_station()
        before = (self.lab.center_counts(), self.lab.sheet_counts())
        for min_amplitude, min_dwell in [
            (-1, 1), ('abc', 1), (0.5, 1), (None, 1),
            (2, 0), (2, -1), (2, '3'), (2, True), (2, None),
        ]:
            with self.subTest(min_amplitude=min_amplitude, min_dwell=min_dwell):
                with self.assertRaises(ValueError):
                    self.lab.publish_sheet([left, right], min_amplitude, min_dwell)
                self.assertEqual((self.lab.center_counts(), self.lab.sheet_counts()), before)
        # a zero amplitude threshold lists every full cycle meeting the dwell threshold
        self.assertEqual(len(self.lab.publish_sheet([left, right], 0, 3).sheet.entries), 1)

    def test_invalid_selection(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 2, 6])
        first = self.lab.receive_dwell_shift('S', revision, 1, 2)
        second = self.lab.receive_dwell_shift('S', revision, 3, 4)
        gap = self.lab.receive_dwell_shift('S', revision, 4, 6)
        self.lab.close_station()
        before = self.lab.sheet_counts()
        for chosen in ([], [first, 99999], [second, first], [first, gap], [first, first]):
            with self.subTest(chosen=chosen):
                with self.assertRaises(ValueError):
                    self.lab.publish_sheet(chosen, 1, 1)
                self.assertEqual(self.lab.sheet_counts(), before)

    def test_single_piece(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 2, 6])
        receipt = self.lab.receive_dwell_shift('S', revision, 1, 5)
        self.lab.close_station()
        published = self.lab.publish_sheet([receipt], 2, 2)
        self.assertEqual(len(published.sheet.entries), 1)
        entry = published.sheet.entries[0]
        self.assertEqual((entry.amplitude, entry.first_beat, entry.last_beat), (Fraction(2), 2, 4))
        self.assertEqual((entry.dwell.first, entry.dwell.last, entry.dwell.count), (2, 3, 2))
        self.assertEqual(tuple(source.receipt_id for source in entry.sources), (receipt,))

    def test_exact_load(self):
        revision = self.lab.record('R', 1, [0, '4/3', '4/3', '2/3', 2])
        receipt = self.lab.receive_dwell_shift('R', revision, 1, 5)
        self.lab.close_station()
        published = self.lab.publish_sheet([receipt], '2/3', 2)
        entry = published.sheet.entries[0]
        self.assertEqual(entry.amplitude, Fraction(2, 3))
        self.assertEqual((entry.dwell.load, entry.dwell.count), (Fraction(4, 3), 2))
        self.lab.close_center()
        self.lab.open_center()
        self.assertEqual(self.lab.receive_sheet(published.sheet.sheet_id), published)


class DwellEvidenceTests(LabTestCase):
    def setUp(self):
        super().setUp()
        self.revision = self.lab.record('S', 1, [0, 4, 4, 2, 6])
        self.frozen = self.lab.freeze('S', self.revision, 1, 5)
        self.original = self.lab.issue_dwell(self.frozen.shift_id)

    def _craft(self, body_updates=None, **envelope_updates):
        envelope = json.loads(self.original)
        body = json.loads(envelope['body'])
        if body_updates:
            body.update(body_updates)
        body_text = canonical_json(body)
        envelope.update({
            'version': 2,
            'piece_id': piece_identity(body_text),
            'shift_id': body['shift_id'],
            'measurement_id': body['measurement_id'],
            'coverage': body['coverage'],
            'body': body_text,
        })
        envelope.update(envelope_updates)
        return canonical_json(envelope)

    def test_dwell_body_format(self):
        envelope = read_envelope(self.original)
        self.assertEqual(envelope.version, 2)
        body = decode_dwell_body(envelope.body)
        self.assertEqual(
            [(run.first, run.last, str(run.load)) for run in body.runs],
            [(1, 1, '0'), (2, 3, '4'), (4, 4, '2'), (5, 5, '6')],
        )
        self.assertEqual(
            [(point.beat, str(point.load)) for point in body.points],
            [(1, '0'), (2, '4'), (4, '2'), (5, '6')],
        )
        self.assertEqual((body.shift_id, body.measurement_id), (self.frozen.shift_id, self.revision))
        self.assertEqual(
            (body.coverage.specimen, body.coverage.first, body.coverage.last), ('S', 1, 5)
        )
        self.assertEqual(self.lab.issue_dwell(self.frozen.shift_id), self.original)
        self.assertEqual(self.lab.archive.get_dwell_by_shift(self.frozen.shift_id), self.original)
        self.assertEqual(self.lab.archive.get_dwell_by_piece(envelope.piece_id), self.original)
        self.lab.close_station()
        self.lab.open_station()
        self.assertEqual(self.lab.issue_dwell(self.frozen.shift_id), self.original)

    def test_dwell_unknown_shift(self):
        before = self.lab.station_counts()
        with self.assertRaisesRegex(ValueError, 'unknown frozen shift'):
            self.lab.issue_dwell('missing-shift')
        self.assertEqual(self.lab.station_counts(), before)
        self.assertIsNone(self.lab.archive.get_dwell_by_shift('missing-shift'))

    def test_dwell_intake_retry(self):
        receipt_id = self.lab.accept(self.original)
        self.assertEqual(self.lab.accept(self.original), receipt_id)
        self.assertEqual(self.lab.center_counts(), (1, 0, 0))
        stored = self.lab.catalog.get_receipt(receipt_id)
        self.assertEqual(stored.original, self.original)
        self.assertEqual(read_envelope(stored.original).version, 2)

    def test_invalid_dwell_runs(self):
        cases = {
            'monotone interior': [[1, 1, '0'], [2, 2, '2'], [3, 3, '4'], [4, 4, '2'], [5, 5, '6']],
            'truncated tail': [[1, 1, '0'], [2, 3, '4'], [4, 4, '2']],
            'adjacent equal loads': [[1, 1, '0'], [2, 2, '4'], [3, 3, '4'], [4, 4, '2'], [5, 5, '6']],
            'reversed run': [[1, 1, '0'], [3, 2, '4'], [4, 4, '2'], [5, 5, '6']],
            'overlapping runs': [[1, 1, '0'], [2, 3, '4'], [3, 4, '2'], [5, 5, '6']],
        }
        for name, runs in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.lab.accept(self._craft({'runs': runs}))
                self.assertEqual(self.lab.center_counts(), (0, 0, 0))

    def test_invalid_dwell_envelope(self):
        v1_body = json.loads(self.original)['body']
        for name, crafted in [
            ('unsupported version', self._craft(version=3)),
            ('identity mismatch', self._craft(piece_id='sha256:wrong')),
            ('coverage mismatch', self._craft(coverage={'specimen': 'S', 'first': 1, 'last': 6})),
            ('v1 body fields', self._craft({'points': [[1, '0'], [2, '4'], [4, '2'], [5, '6']],
                                            'runs': None})),
        ]:
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.lab.accept(crafted)
                self.assertEqual(self.lab.center_counts(), (0, 0, 0))


class RetestDemoTests(LabTestCase):
    """Business samples: a cross-shift cut landing inside an equal-value interval,
    a revision shortening that interval, and old pieces mixed into an application."""

    def test_sample_cross_seam_cut(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 2, 6])
        left = self.lab.receive_dwell_shift('S', revision, 1, 3)
        right = self.lab.receive_dwell_shift('S', revision, 4, 6)
        self.lab.close_station()
        published = self.lab.publish_sheet([left, right], 2, 3)
        expected = {
            'min_amplitude': '2', 'min_dwell': 3,
            'entries': [{
                'amplitude': '2', 'first': [2, '4'], 'last': [5, '2'],
                'dwell': [2, 4, '4', 3], 'source_receipts': [1, 2],
            }],
        }
        actual = sheet_view(published.sheet)
        self.assertEqual(actual, expected)
        self.lab.close_center()
        self.lab.open_center()
        received = self.lab.receive_sheet(published.sheet.sheet_id)
        self.assertEqual(received, published)
        downstream_expected = {'sheets': [1, 1], 'reopened_view': expected}
        downstream_actual = {
            'sheets': list(self.lab.sheet_counts()),
            'reopened_view': sheet_view(received.sheet),
        }
        self.assertEqual(downstream_actual, downstream_expected)
        scenario(
            'R1',
            {'loads_kn': [0, 4, 4, 4, 2, 6], 'cut_after_beat': 3,
             'min_amplitude_kn': '2', 'min_dwell_beats': 3},
            expected, actual, downstream_expected, downstream_actual,
            ['evidence/issuer.py', 'evidence/body.py', 'intake/accept.py',
             'report/dwell.py', 'report/retest.py'],
            'The 4 kN plateau spans beats 2-4 across the seam after beat 3, so the full '
            'cycle of amplitude 2 kN (beats 2 and 5) dwells 3 original beats on both pieces.',
        )

    def test_sample_revision_shortens_dwell(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 4, 2, 6])
        left = self.lab.receive_dwell_shift('S', revision, 1, 4)
        right = self.lab.receive_dwell_shift('S', revision, 5, 7)
        self.lab.close_station()
        old = self.lab.publish_sheet([left, right], 2, 4)
        old_expected = {
            'min_amplitude': '2', 'min_dwell': 4,
            'entries': [{
                'amplitude': '2', 'first': [2, '4'], 'last': [6, '2'],
                'dwell': [2, 5, '4', 4], 'source_receipts': [1, 2],
            }],
        }
        self.assertEqual(sheet_view(old.sheet), old_expected)
        self.lab.open_station()
        revised = self.lab.correct('S', revision, [(5, 3)])
        new_left = self.lab.receive_dwell_shift('S', revised, 1, 4)
        new_right = self.lab.receive_dwell_shift('S', revised, 5, 7)
        self.lab.close_station()
        strict = self.lab.publish_sheet([new_left, new_right], 2, 4)
        adjusted = self.lab.publish_sheet([new_left, new_right], 2, 3)
        adjusted_expected = {
            'min_amplitude': '2', 'min_dwell': 3,
            'entries': [{
                'amplitude': '2', 'first': [2, '4'], 'last': [6, '2'],
                'dwell': [2, 4, '4', 3], 'source_receipts': [3],
            }],
        }
        expected = [
            old_expected,
            {'min_amplitude': '2', 'min_dwell': 4, 'entries': []},
            adjusted_expected,
        ]
        actual = [sheet_view(sheet.sheet) for sheet in (old, strict, adjusted)]
        self.assertEqual(actual, expected)
        self.lab.close_center()
        self.lab.open_center()
        reopened = [self.lab.receive_sheet(sheet.sheet.sheet_id) for sheet in (old, strict, adjusted)]
        self.assertEqual(reopened, [old, strict, adjusted])
        downstream_expected = {'sheets': [3, 3], 'kept_old_sheet': True}
        downstream_actual = {
            'sheets': list(self.lab.sheet_counts()),
            'kept_old_sheet': sheet_view(reopened[0].sheet) == old_expected,
        }
        self.assertEqual(downstream_actual, downstream_expected)
        scenario(
            'R2',
            {'loads_kn': [0, 4, 4, 4, 4, 2, 6], 'cut_after_beat': 4,
             'correction': [[5, 3]], 'min_amplitude_kn': '2', 'min_dwell_beats': [4, 3]},
            expected, actual, downstream_expected, downstream_actual,
            ['source/correction.py', 'evidence/issuer.py', 'report/dwell.py', 'report/retest.py'],
            'Correcting beat 5 from 4 to 3 kN shortens the 4 kN dwell from beats 2-5 to '
            'beats 2-4, so only the left piece remains a source. The old sheet stays '
            'signed; the new application signs new sheets.',
        )

    def test_sample_mixed_old_piece(self):
        revision = self.lab.record('S', 1, [0, 4, 4, 4, 2, 6])
        good_left = self.lab.receive_dwell_shift('S', revision, 1, 3)
        good_right = self.lab.receive_dwell_shift('S', revision, 4, 6)
        old_shift = self.lab.freeze('S', revision, 1, 3)
        old_receipt = self.lab.accept(self.lab.issue(old_shift.shift_id))
        self.lab.close_station()
        old_sheet = self.lab.publish_sheet([good_left, good_right], 2, 3)
        before = (self.lab.center_counts(), self.lab.sheet_counts())
        with self.assertRaises(UnverifiableDwellError) as caught:
            self.lab.publish_sheet([old_receipt, good_right], 2, 3)
        pending = caught.exception.pending
        self.assertEqual(pending, (old_receipt,))
        kept = (self.lab.center_counts(), self.lab.sheet_counts())
        self.assertEqual(kept, before)
        # the supplement is bound to the originally selected revision and coverage
        receipt = self.lab.catalog.get_receipt(pending[0])
        self.lab.open_station()
        supplement_shift = self.lab.freeze(
            'S', receipt.measurement_id, receipt.coverage.first, receipt.coverage.last
        )
        supplement = self.lab.accept(self.lab.issue_dwell(supplement_shift.shift_id))
        self.lab.close_station()
        sheet = self.lab.publish_sheet([supplement, good_right], 2, 3)
        expected = {
            'min_amplitude': '2', 'min_dwell': 3,
            'entries': [{
                'amplitude': '2', 'first': [2, '4'], 'last': [5, '2'],
                'dwell': [2, 4, '4', 3], 'source_receipts': [4, 2],
            }],
        }
        actual = sheet_view(sheet.sheet)
        self.assertEqual(actual, expected)
        downstream_expected = {
            'pending_receipts': [3],
            'kept_counts': [[3, 0, 0], [1, 1]],
            'old_sheet_kept': True,
        }
        downstream_actual = {
            'pending_receipts': list(pending),
            'kept_counts': [list(kept[0]), list(kept[1])],
            'old_sheet_kept': self.lab.receive_sheet(old_sheet.sheet.sheet_id) == old_sheet,
        }
        self.assertEqual(downstream_actual, downstream_expected)
        scenario(
            'R3',
            {'loads_kn': [0, 4, 4, 4, 2, 6], 'cut_after_beat': 3,
             'mixed_receipt': 3, 'min_amplitude_kn': '2', 'min_dwell_beats': 3},
            expected, actual, downstream_expected, downstream_actual,
            ['intake/identity.py', 'report/retest.py', 'evidence/issuer.py'],
            'The V1 piece cannot verify dwell, so the application names receipt 3 as '
            'pending and writes nothing. A V2 supplement on the same revision and '
            'coverage lets the application sign the sheet.',
        )
