from __future__ import annotations

import unittest

from agent_loop.cli import _objective


class CliTests(unittest.TestCase):
    def test_requires_one_objective_source(self) -> None:
        with self.assertRaises(ValueError):
            _objective(None, None)
        self.assertEqual(_objective(" ship it ", None), "ship it")


if __name__ == "__main__":
    unittest.main()
