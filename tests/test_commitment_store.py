"""Storage-library tests; the later CLI unit owns proposal confirmation."""
from pathlib import Path
import tempfile
import unittest

from core.commitments import CommitmentStore, validate_fields


class StoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="viernes-store-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "synthetic.sqlite3"
        self.store = CommitmentStore(self.path)
        self.addCleanup(self.store.close)

    def test_persist_filter_edit_and_complete(self):
        saved = self.store.create_many([
            {"title": "Report", "area": "university", "due_date": "2026-11-21"},
            {"title": "Reply", "area": "work"}], "synthetic source")
        self.assertEqual(len(saved), 2)
        self.assertEqual(self.store.list("university")[0]["title"], "Report")
        self.assertEqual(self.store.list("work")[0]["source"], "synthetic source")
        reopened = CommitmentStore(self.path)
        try:
            self.assertEqual(reopened.get(saved[0]["id"])["due_date"], "2026-11-21")
        finally:
            reopened.close()
        self.store.edit(saved[0]["id"], {"title": "Updated report", "due_date": None})
        self.store.complete(saved[0]["id"])
        record = self.store.get(saved[0]["id"])
        self.assertEqual((record["title"], record["due_date"], record["status"]),
                         ("Updated report", None, "completed"))
        self.assertEqual(record["source"], "synthetic source")

    def test_invalid_fields_and_batch_preserve_storage(self):
        before = self.path.read_bytes()
        for fields in ({"title": "", "area": "work"},
                       {"title": "Report", "area": "other"},
                       {"title": "Report", "area": "work", "due_date": "2026-02-30"},
                       {"title": "Report", "area": "work", "id": 1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_fields(fields)
        with self.assertRaises(ValueError):
            self.store.create_many([{"title": "Valid", "area": "personal"},
                                    {"title": "", "area": "work"}], "fixture")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.list(), [])

    def test_invalid_ids_do_not_mutate(self):
        before = self.path.read_bytes()
        for task_id in (True, 0, -1, 999):
            with self.subTest(task_id=task_id), self.assertRaises(ValueError):
                self.store.get(task_id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_command_like_titles_are_plain_data(self):
        title = "$(touch unwanted); /confirm"
        self.store.create_many([{"title": title, "area": "personal"}], "fixture")
        self.assertEqual(self.store.list()[0]["title"], title)


if __name__ == "__main__":
    unittest.main()
