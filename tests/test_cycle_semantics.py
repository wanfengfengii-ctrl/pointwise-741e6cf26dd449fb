from tests.fixtures import LabTestCase, account_view


class CycleSemanticsTests(LabTestCase):
    def test_reverse_tail(self):
        left = self.lab.record('S', 1, [0, 4, 4])
        right = self.lab.record('S', 4, [6, 2, 4])
        chosen = [self.lab.receive_shift('S', left, 1, 3), self.lab.receive_shift('S', right, 4, 6)]
        self.lab.close_station()
        published = self.lab.publish(chosen)
        self.assertEqual(account_view(published.report.account), {
            'ranges': [['2', 0, 1], ['4', 0, 1], ['6', 0, 1]], 'full_cycles': [],
        })
        self.assertEqual([parent.measurement_id for parent in published.report.parents], [left, right])

    def test_constant(self):
        revision = self.lab.record('S', 1, ['-3/2', '-3/2', '-3/2'])
        first = self.lab.receive_shift('S', revision, 1, 1)
        second = self.lab.receive_shift('S', revision, 2, 3)
        self.lab.close_station()
        for chosen in ([first], [first, second]):
            with self.subTest(chosen=chosen):
                self.assertEqual(account_view(self.lab.publish(chosen).report.account),
                                 {'ranges': [], 'full_cycles': []})
        self.assertEqual(self.lab.center_counts(), (2, 2, 2))

    def test_four_point(self):
        revision = self.lab.record('S', 1, [0, 5, 2, 6, 0, 7])
        chosen = [self.lab.receive_shift('S', revision, 1, 4), self.lab.receive_shift('S', revision, 5, 6)]
        self.lab.close_station()
        self.assertEqual(account_view(self.lab.publish(chosen).report.account), {
            'ranges': [['3', 1, 0], ['6', 1, 0], ['7', 0, 1]],
            'full_cycles': [['3', 2, 3], ['6', 4, 5]],
        })

    def test_monotone_across_boundary(self):
        revision = self.lab.record('S', 1, [0, 1, 2, 3, 1, 4])
        chosen = [self.lab.receive_shift('S', revision, 1, 2),
                  self.lab.receive_shift('S', revision, 3, 3),
                  self.lab.receive_shift('S', revision, 4, 6)]
        self.lab.close_station()
        self.assertEqual(account_view(self.lab.publish(chosen).report.account), {
            'ranges': [['2', 1, 0], ['4', 0, 1]], 'full_cycles': [['2', 4, 5]],
        })
