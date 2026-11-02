import unittest

from audit_pole_matched_braid import validate_matched


def phases(angles, retained=1.):
    return {p: {'combined': {'sine_offset_deg': angle}, 'retained_amplitude_fraction': retained}
            for p, angle in zip('ABC', angles)}


class PoleMatchedAuditTest(unittest.TestCase):
    def test_accepts_wrapped_balanced_sequence(self):
        validate_matched(phases([70, -50, -170]))
        validate_matched(phases([-110, 130, 10]))

    def test_rejects_legacy_sixty_degree_axes(self):
        with self.assertRaisesRegex(ValueError, '120-degree'):
            validate_matched(phases([70, 10, -50]))

    def test_rejects_nonfinite_results(self):
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            validate_matched(phases([float('nan'), -50, -170]))

    def test_rejects_opposing_pairs_and_reversed_sequence(self):
        with self.assertRaisesRegex(ValueError, 'constructively'):
            validate_matched(phases([70, -50, -170], .167))
        with self.assertRaisesRegex(ValueError, '120-degree'):
            validate_matched(phases([70, -170, -50]))


if __name__ == '__main__':
    unittest.main()
