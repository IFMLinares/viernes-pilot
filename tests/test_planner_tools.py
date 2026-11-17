"""Trusted clock and pure date tools, independent of model inference/config."""
from datetime import datetime, timezone
import unittest

from core.planner_tools import CARACAS, Tool, ToolError, ToolRegistry, default_registry, reference_time


class DateToolTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 23, 30, tzinfo=CARACAS)
        self.registry = default_registry()

    def resolve(self, *references):
        return self.registry.execute("resolve_date", {"references": list(references)}, self.now)

    def test_caracas_clock_converts_utc_before_selecting_year(self):
        instant = datetime(2027, 1, 1, 2, 0, tzinfo=timezone.utc)
        local = reference_time(clock=lambda: instant)
        self.assertEqual(local.isoformat(), "2026-12-31T22:00:00-04:00")
        self.assertEqual(self.registry.execute("resolve_date", {"references": [
            {"kind": "calendar", "month": 1, "day": 2}]}, local)["date"], "2026-01-02")

    def test_yearless_date_uses_current_year_even_when_past(self):
        self.assertEqual(self.resolve({"kind": "calendar", "month": 9, "day": 19})["date"], "2026-09-19")
        self.assertEqual(self.resolve({"kind": "calendar", "month": 9, "day": 19, "year": 2027})["date"], "2027-09-19")

    def test_relative_days_and_next_weekday_use_calendar_arithmetic(self):
        self.assertEqual(self.resolve({"kind": "relative_days", "days": 3})["date"], "2026-11-17")
        self.now = datetime(2026, 12, 30, 23, tzinfo=CARACAS)
        self.assertEqual(self.resolve({"kind": "relative_days", "days": 3})["date"], "2027-01-02")
        self.now = datetime(2026, 11, 19, 12, tzinfo=CARACAS)
        self.assertEqual(self.resolve({"kind": "weekday", "weekday": 4})["date"], "2026-11-26")

    def test_conflicting_references_are_not_silently_overwritten(self):
        result = self.resolve({"kind": "weekday", "weekday": 4}, {"kind": "calendar", "month": 9, "day": 19})
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["dates"], ["2026-11-19", "2026-09-19"])
        self.assertEqual(self.resolve({"kind": "weekday", "weekday": 4},
                                      {"kind": "calendar", "month": 11, "day": 19})["status"], "resolved")

    def test_invalid_calendar_date_does_not_roll_to_another_year(self):
        self.assertEqual(self.resolve({"kind": "calendar", "month": 2, "day": 29})["status"], "invalid")
        self.assertEqual(self.resolve({"kind": "calendar", "month": 2, "day": 29, "year": 2028})["date"], "2028-02-29")

    def test_registry_is_allowlisted_and_validates_arguments(self):
        for name, arguments in (("shell", {}), ("resolve_date", {}),
                                ("resolve_date", {"references": [{"kind": "relative_days", "days": True}]}),
                                ("resolve_date", {"references": [{"kind": "weekday", "weekday": 8}]}),
                                ("resolve_date", {"references": [{"kind": "calendar", "month": 11}]}),
                                ("resolve_date", {"references": [], "timezone": "UTC"})):
            with self.subTest(name=name, arguments=arguments), self.assertRaises(ToolError):
                self.registry.execute(name, arguments, self.now)
        definitions = self.registry.definitions()
        self.assertEqual([item["name"] for item in definitions], ["resolve_date"])
        definitions[0]["name"] = "shell"
        self.assertEqual(self.registry.definitions()[0]["name"], "resolve_date")

    def test_registry_extensions_are_explicit_and_duplicate_names_fail(self):
        tool = Tool("calendar_label", "Read-only date label", {"type": "object"},
                    lambda arguments, instant: {"date": instant.date().isoformat()})
        registry = ToolRegistry([tool])
        self.assertEqual(registry.execute("calendar_label", {}, self.now), {"date": "2026-11-14"})
        with self.assertRaises(ToolError):
            ToolRegistry([tool, tool])
        with self.assertRaises(ToolError):
            reference_time(clock=lambda: datetime(2026, 11, 14))
