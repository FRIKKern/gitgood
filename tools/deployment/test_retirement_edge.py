import sys
import unittest
from unittest.mock import patch

from retirement_edge import guardian
from upgrade_journal import UpgradeRefused


@unittest.skipUnless(sys.platform != "linux", "Foreign-profile early refusal")
class UnsupportedRetirementEdgeTest(unittest.TestCase):
    def test_foreign_guardian_refuses_before_path_observation(self):
        with patch("retirement_edge.Path", side_effect=AssertionError("No path access permitted")):
            with self.assertRaises(UpgradeRefused):
                guardian("unobserved", "a" * 64)
