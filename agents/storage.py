"""Yangiliklar, qoralamalar va bot holatini saqlash."""
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, source TEXT, url TEXT, title TEXT, text TEXT,
  image TEXT, published TEXT, score REAL, status TEXT DEFAULT 'new', posted_at TEXT
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS comments (
  id TEXT PRIMARY KEY, chat_id TEXT, message_id INTEGER, author TEXT, text TEXT, post TEXT,
  status TEXT DEFAULT 'new', created TEXT, reply TEXT
);
"""
EXTRA_COLUMNS = {"media": "TEXT", "media_off": "INTEGER DEFAULT 0", "draft": "TEXT", "related": "TEXT", "qc": "TEXT", "msg_id": "INTEGER", "drafted_at": "TEXT",
                 "prev_draft": "TEXT", "prev_qc": "TEXT", "redo_mode": "TEXT", "posted_to": "TEXT"}

# status: new → skipped | drafted ⇄ redo → posted | rejected (🗑 Keraksiz)


def utcnow():
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path="data.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(items)")}
        for col, typ in EXTRA_COLUMNS.items():
            if col not in have:
                self.db.execute(f"ALTER TABLE items ADD COLUMN {col} {typ}")
        if "answered_at" not in {r["name"] for r in self.db.execute("PRAGMA table_info(comments)")}:
            self.db.execute("ALTER TABLE comments ADD COLUMN answered_at TEXT")
        self.db.commit()

    @staticmethod
    def make_id(url, text):
        return hashlib.sha1((url or text[:200]).encode()).hexdigest()

    # --- kv ---
    def get(self, k, default=None):
        r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default

    def put(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, str(v)))
        self.db.commit()

    # --- items ---
    def exists(self, item_id):
        return self.db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone() is not None

    def fill_media(self, item_id, media):
        if media and media != "[]":
            self.db.execute("UPDATE items SET media=? WHERE id=? AND (media IS NULL OR media='[]')", (media, item_id))
            self.db.commit()

    def add(self, item):
        cur = self.db.execute(
            "INSERT OR IGNORE INTO items (id, source, url, title, text, image, media, published, score)"
            " VALUES (:id, :source, :url, :title, :text, :image, :media, :published, :score)", {"media": "[]", **item})
        self.db.commit()
        return cur.rowcount == 1

    def item(self, item_id):
        r = self.db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return dict(r) if r else None

    def new_items(self, max_age_hours):
        since = (utcnow() - timedelta(hours=max_age_hours)).isoformat()
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM items WHERE status='new' AND published >= ? ORDER BY published DESC", (since,))]

    def by_status(self, status):
        return [dict(r) for r in self.db.execute("SELECT * FROM items WHERE status=?", (status,))]

    def unsent_drafts(self):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM items WHERE status='drafted' AND msg_id IS NULL ORDER BY drafted_at")]

    def recent_topics(self, hours=48, limit=40):
        """Oxirgi qoralama va postlar — takrorlanmaslik uchun."""
        since = (utcnow() - timedelta(hours=hours)).isoformat()
        return [(r["draft"] or r["text"])[:200].replace("\n", " ") for r in self.db.execute(
            "SELECT draft, text FROM items WHERE status IN ('drafted','redo','posted') AND drafted_at >= ?"
            " ORDER BY drafted_at DESC LIMIT ?", (since, limit))]

    def set(self, item_id, **fields):
        if fields.get("status") == "posted":
            fields["posted_at"] = utcnow().isoformat()
        if fields.get("status") == "drafted":
            fields["drafted_at"] = utcnow().isoformat()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE items SET {cols} WHERE id=?", (*fields.values(), item_id))
        self.db.commit()

    def mark_new_as(self, ids, status):
        self.db.executemany("UPDATE items SET status=? WHERE id=? AND status='new'", [(status, i) for i in ids])
        self.db.commit()

    # --- izohlar (kanal izoh guruhi) ---
    def add_comment(self, c):
        self.db.execute("INSERT OR IGNORE INTO comments (id, chat_id, message_id, author, text, post, created)"
                        " VALUES (:id, :chat_id, :message_id, :author, :text, :post, :created)", c)
        self.db.commit()

    def comments(self, status="new"):
        return [dict(r) for r in self.db.execute("SELECT * FROM comments WHERE status=? ORDER BY created", (status,))]

    def comment(self, cid):
        r = self.db.execute("SELECT * FROM comments WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None

    def comments_all(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM comments")]

    def set_comment(self, cid, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE comments SET {cols} WHERE id=?", (*fields.values(), cid))
        self.db.commit()

    def prune(self, days=14):
        self.db.execute("DELETE FROM items WHERE status IN ('new','skipped','rejected') AND published < ?",
                        ((utcnow() - timedelta(days=days)).isoformat(),))
        self.db.commit()
