"""Validated commitment records, independent of AI and user interfaces."""
import sqlite3
from datetime import date, timedelta
from pathlib import Path

AREAS = ("university", "work", "personal")
FIELDS = {"title", "area", "project", "due_date"}


def validate_fields(fields, *, partial=False):
    if not isinstance(fields, dict) or not fields or set(fields) - FIELDS:
        raise ValueError("Expected title, area, project and/or due_date fields only.")
    if not partial and not {"title", "area"} <= fields.keys():
        raise ValueError("A title and area are required.")
    clean = dict(fields)
    for name in ("title", "project"):
        if name in clean:
            value = clean[name]
            if name == "project" and value is None:
                continue
            if not isinstance(value, str) or not value.strip() or len(value) > 1000:
                raise ValueError(f"{name} must be a nonempty string of at most 1000 characters.")
            clean[name] = value.strip()
    if "area" in clean and clean["area"] not in AREAS:
        raise ValueError("Area must be university, work or personal.")
    if clean.get("due_date") is not None:
        value = clean["due_date"]
        try:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("due_date must be a real YYYY-MM-DD date or null.") from None
    return clean


class CommitmentStore:
    def __init__(self, path):
        path = Path(path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS commitments (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                area TEXT NOT NULL CHECK(area IN ('university', 'work', 'personal')),
                project TEXT,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'completed')),
                source TEXT NOT NULL
            )
        """)
        self.connection.commit()

    def close(self):
        self.connection.close()

    def list(self, area=None):
        if area is not None and area not in AREAS:
            raise ValueError("Unknown area.")
        query = "SELECT * FROM commitments"
        params = ()
        if area is not None:
            query += " WHERE area = ?"
            params = (area,)
        query += " ORDER BY status DESC, due_date IS NULL, due_date, id"
        return [dict(row) for row in self.connection.execute(query, params)]

    def get(self, task_id):
        if type(task_id) is not int or task_id <= 0:
            raise ValueError("Expected a positive integer commitment ID.")
        row = self.connection.execute("SELECT * FROM commitments WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"Commitment {task_id} does not exist.")
        return dict(row)

    def query(self, area=None, *, scope="current", start_date=None, end_date=None, today=None):
        """Filter in SQLite, keeping the unbounded internal list API unchanged."""
        if area is not None and area not in AREAS:
            raise ValueError("Unknown area.")
        if scope not in ("current", "all", "range"):
            raise ValueError("Unknown query scope.")
        if scope != "range" and (start_date is not None or end_date is not None):
            raise ValueError("Explicit dates require range scope.")
        clauses, params = [], []
        if area is not None:
            clauses.append("area = ?")
            params.append(area)
        if scope == "current":
            start_date = ((today or date.today()) - timedelta(days=7)).isoformat()
            clauses.append("(due_date >= ? OR (status = 'pending' AND (due_date < ? OR due_date IS NULL)))")
            params.extend([start_date, start_date])
        elif scope == "range":
            if start_date is None or end_date is None:
                raise ValueError("A range requires start_date and end_date.")
            validate_fields({"due_date": start_date}, partial=True)
            validate_fields({"due_date": end_date}, partial=True)
            if start_date > end_date:
                raise ValueError("Query start_date must not be after end_date.")
            clauses.append("due_date >= ? AND due_date <= ?")
            params.extend([start_date, end_date])
        sql = "SELECT * FROM commitments"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY status DESC, due_date IS NULL, due_date, id"
        rows = [dict(row) for row in self.connection.execute(sql, params)]
        return {"scope": scope, "area": area, "start_date": start_date, "end_date": end_date, "rows": rows}

    def create_many(self, items, source):
        if not isinstance(items, list) or not 1 <= len(items) <= 20:
            raise ValueError("Expected between 1 and 20 commitments.")
        clean = [validate_fields(item) for item in items]
        ids = []
        with self.connection:
            for item in clean:
                cursor = self.connection.execute(
                    "INSERT INTO commitments(title, area, project, due_date, source) VALUES (?, ?, ?, ?, ?)",
                    (item["title"], item["area"], item.get("project"), item.get("due_date"), source),
                )
                ids.append(cursor.lastrowid)
        return [self.get(task_id) for task_id in ids]

    def edit(self, task_id, fields):
        self.get(task_id)
        clean = validate_fields(fields, partial=True)
        assignments = ", ".join(f"{name} = ?" for name in clean)
        with self.connection:
            self.connection.execute(
                f"UPDATE commitments SET {assignments} WHERE id = ?", (*clean.values(), task_id)
            )
        return self.get(task_id)

    def complete(self, task_id):
        self.get(task_id)
        with self.connection:
            self.connection.execute("UPDATE commitments SET status = 'completed' WHERE id = ?", (task_id,))
        return self.get(task_id)
