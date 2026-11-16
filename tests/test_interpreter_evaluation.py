"""Fixed reference-date regression for the synthetic comparison foundation."""
import unittest
from datetime import date
from tools import evaluate_interpreter


class EvaluateInterpreterTests(unittest.TestCase):
    def test_reference_date_is_fixed(self):
        self.assertEqual(evaluate_interpreter.REFERENCE_DATE, date(2026, 11, 23))



if __name__ == "__main__":
    unittest.main()
