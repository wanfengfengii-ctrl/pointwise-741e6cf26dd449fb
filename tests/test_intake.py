import json

from evidence.envelope import read_envelope
from tests.fixtures import LabTestCase


class IntakeTests(LabTestCase):
    def setUp(self):
        super().setUp()
        self.revision = self.lab.record('S', 4, [4, 2, 6])
        self.frozen = self.lab.freeze('S', self.revision, 4, 6)
        self.original = self.lab.issue(self.frozen.shift_id)

    def test_retry(self):
        receipt_id = self.lab.accept(self.original)
        self.assertEqual(self.lab.accept(self.original), receipt_id)
        self.assertEqual(self.lab.center_counts(), (1, 0, 0))
        stored = self.lab.catalog.get_receipt(receipt_id)
        self.assertEqual(stored.original, self.original)
        self.assertEqual(stored.piece_id, read_envelope(self.original).piece_id)
        self.assertEqual((stored.shift_id, stored.measurement_id), (self.frozen.shift_id, self.revision))
        self.assertEqual((stored.coverage.specimen, stored.coverage.first, stored.coverage.last), ('S', 4, 6))

    def test_distinct_revision(self):
        old_id = self.lab.accept(self.original)
        self.assertEqual(self.lab.accept(self.original), old_id)
        revision = self.lab.correct('S', self.revision, [(4, 6), (6, 4)])
        frozen = self.lab.freeze('S', revision, 4, 6)
        new_original = self.lab.issue(frozen.shift_id)
        new_id = self.lab.accept(new_original)
        self.assertNotEqual(old_id, new_id)
        self.assertEqual(self.lab.catalog.get_receipt(old_id).original, self.original)
        self.assertEqual(self.lab.catalog.get_receipt(new_id).original, new_original)
        self.assertEqual(self.lab.center_counts(), (2, 0, 0))

    def test_mismatched_identity(self):
        for field, replacement in [
            ('piece_id', 'sha256:wrong'), ('shift_id', 'wrong-shift'),
            ('measurement_id', 'wrong-source'),
            ('coverage', {'specimen': 'S', 'first': 4, 'last': 7}),
        ]:
            with self.subTest(field=field):
                envelope = json.loads(self.original)
                envelope[field] = replacement
                with self.assertRaisesRegex(ValueError, 'does not match|do not match'):
                    self.lab.accept(json.dumps(envelope))
                self.assertEqual(self.lab.center_counts(), (0, 0, 0))

    def test_conflict_on_retry(self):
        receipt_id = self.lab.accept(self.original)
        envelope = json.loads(self.original)
        envelope['measurement_id'] = 'conflicting-revision'
        with self.assertRaisesRegex(ValueError, 'do not match'):
            self.lab.accept(json.dumps(envelope))
        self.assertEqual(self.lab.center_counts(), (1, 0, 0))
        self.assertEqual(self.lab.accept(self.original), receipt_id)
        self.assertEqual(self.lab.catalog.get_receipt(receipt_id).original, self.original)
