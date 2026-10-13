"""Yangiliklar va chiqarilgan postlarni saqlash (takrorlanmaslik uchun)."""
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, source TEXT, url TEXT, title TEXT, text TEXT,
  image TEXT, published TEXT, score REAL, status TEXT DEFAULT 'new', posted_at TEXT
);
"""


def utcnow():
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path="data.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    @staticmethod
    def make_id(url, text):
        return hashlib.sha1((url or text[:200]).encode()).hexdigest()

    def exists(self, item_id):
        return self.db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone() is not None

    def add(self, item):
        cur = self.db.execute(
            "INSERT OR IGNORE INTO items (id, source, url, title, text, image, published, score)"
            " VALUES (:id, :source, :url, :title, :text, :image, :published, :score)", item)
        self.db.commit()
        return cur.rowcount == 1

    def candidates(self, max_age_hours, limit=25):
        """Eng yangi, hali ishlatilmagan yangiliklar; kalit so'z mosligi ustuvor."""
        since = (utcnow() - timedelta(hours=max_age_hours)).isoformat()
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM items WHERE status='new' AND published >= ?"
            " ORDER BY (score > 0) DESC, published DESC LIMIT ?", (since, limit))]

    def recent_posted(self, limit=30):
        return [(r["title"] or r["text"])[:200] for r in self.db.execute(
            "SELECT title, text FROM items WHERE status='posted' ORDER BY posted_at DESC LIMIT ?", (limit,))]

    def posted_since(self, since):
        return [r["posted_at"] for r in self.db.execute(
            "SELECT posted_at FROM items WHERE status='posted' AND posted_at >= ? ORDER BY posted_at",
            (since.isoformat(),))]

    def set_status(self, item_id, status):
        self.db.execute("UPDATE items SET status=?, posted_at=? WHERE id=?",
                        (status, utcnow().isoformat() if status == "posted" else None, item_id))
        self.db.commit()

    def prune(self, days=14):
        self.db.execute("DELETE FROM items WHERE status!='posted' AND published < ?",
                        ((utcnow() - timedelta(days=days)).isoformat(),))
        self.db.commit()
