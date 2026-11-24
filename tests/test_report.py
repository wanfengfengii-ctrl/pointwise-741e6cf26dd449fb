from tests.fixtures import LabTestCase, account_view, scenario


class PublicationInterrupted(Exception):
    pass


class ReportTests(LabTestCase):
    def test_cross_shift_plateau(self):
        loads = [0, 4, 4, 4, 2, 6]
        revision = self.lab.record('S', 1, loads)
        cuts = (3, 2)
        receipt_pairs = [
            (self.lab.receive_shift('S', revision, 1, cut),
             self.lab.receive_shift('S', revision, cut + 1, 6))
            for cut in cuts
        ]
        self.lab.close_station()
        expected = {'ranges': [['2', 1, 0], ['6', 0, 1]], 'full_cycles': [['2', 2, 5]]}
        accounts = []
        observed = []
        for cut, receipts in zip(cuts, receipt_pairs):
            with self.subTest(cut=cut):
                published = self.lab.publish(receipts)
                actual = account_view(published.report.account)
                self.assertEqual(actual, expected, 'FATIGUE_SEAM_MISMATCH: whole-record account')
                self.assertEqual(tuple(parent.receipt_id for parent in published.report.parents), receipts)
                received = self.lab.receive_report(published.report.report_id)
                self.assertEqual(received, published)
                accounts.append(actual)
                observed.append({
                    'parents': [[entry.coverage.first, entry.coverage.last] for entry in received.originals],
                    'signed_and_retrievable': received.signing_receipt.report_id == received.report.report_id,
                })
        downstream = [{'parents': [[1, cut], [cut + 1, 6]], 'signed_and_retrievable': True} for cut in cuts]
        self.assertEqual(observed, downstream)
        scenario(
            'T5', {'loads_kn': loads, 'last_beats_of_first_shift': list(cuts)},
            [expected, expected], accounts, downstream, observed,
            ['evidence/body.py', 'intake/selection.py', 'report/assemble.py',
             'report/cycles.py', 'report/publication.py'],
            'The 4 kN plateau starts at beat 2. The four turning beats are 1, 2, 5 and 6, with differences 4, 2, 4.',
        )

    def test_invalid_selection(self):
        revision = self.lab.record('S', 1, [0, 2, 4, 2, 6])
        first = self.lab.receive_shift('S', revision, 1, 2)
        second = self.lab.receive_shift('S', revision, 3, 4)
        gap = self.lab.receive_shift('S', revision, 4, 5)
        overlap = self.lab.receive_shift('S', revision, 2, 3)
        other_revision = self.lab.record('OTHER', 3, [4, 2])
        other = self.lab.receive_shift('OTHER', other_revision, 3, 4)
        self.lab.close_station()
        before = self.lab.center_counts()
        for name, chosen in [('other specimen', [first, other]), ('reverse', [second, first]),
                             ('gap', [first, gap]), ('overlap', [first, overlap]),
                             ('repeat', [first, first])]:
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.lab.publish(chosen)
                self.assertEqual(self.lab.center_counts(), before)
        self.assertEqual(len(self.lab.publish([first, second]).originals), 2)
        self.assertEqual(self.lab.center_counts(), (before[0], 1, 1))

    def test_unknown_or_empty(self):
        revision = self.lab.record('S', 1, [0, 2])
        receipt = self.lab.receive_shift('S', revision, 1, 2)
        self.lab.close_station()
        for chosen in ([], [receipt, 99999]):
            with self.subTest(receipts=chosen):
                with self.assertRaises(ValueError):
                    self.lab.publish(chosen)
                self.assertEqual(self.lab.center_counts(), (1, 0, 0))

    def test_publish_rollback(self):
        revision = self.lab.record('S', 1, [0, 4, 2, 6])
        receipts = [self.lab.receive_shift('S', revision, 1, 2),
                    self.lab.receive_shift('S', revision, 3, 4)]
        self.lab.close_station()
        earlier = self.lab.publish(receipts)
        before = self.lab.center_counts()
        attempted = []

        def interrupt(report):
            attempted.append(report.report_id)
            self.assertTrue(self.lab.center.in_transaction)
            self.assertEqual(self.lab.center_counts(), (before[0], before[1] + 1, before[2]))
            raise PublicationInterrupted('interrupted after report write')

        with self.assertRaisesRegex(PublicationInterrupted, 'after report write'):
            self.lab.publish(receipts, after_report_write=interrupt)
        self.assertEqual(len(attempted), 1)
        self.lab.close_center()
        self.lab.open_center()
        self.assertEqual(self.lab.center_counts(), before)
        self.assertIsNone(self.lab.receive_report(attempted[0]))
        self.assertEqual(self.lab.receive_report(earlier.report.report_id), earlier)
        retried = self.lab.publish(receipts)
        self.assertEqual(account_view(retried.report.account), {
            'ranges': [['2', 1, 0], ['6', 0, 1]], 'full_cycles': [['2', 2, 3]],
        })
        self.assertEqual(self.lab.receive_report(retried.report.report_id), retried)
        self.assertEqual(self.lab.center_counts(), (before[0], before[1] + 1, before[2] + 1))
