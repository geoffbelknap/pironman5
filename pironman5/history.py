import os
import sqlite3
import time


class SQLiteHistory:
    def __init__(self, db_path):
        self.db_path = db_path

    def connect(self):
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, mode=0o750, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def initialize(self):
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metric_samples (
                    metric TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    value REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metric_samples_metric_time
                ON metric_samples(metric, timestamp)
            """)
        os.chmod(self.db_path, 0o600)

    def record_metric(self, metric, value, timestamp=None):
        if timestamp is None:
            timestamp = int(time.time())
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO metric_samples(metric, timestamp, value) VALUES (?, ?, ?)",
                (metric, int(timestamp), float(value)),
            )

    def read_series(self, metric, start, end):
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, value
                FROM metric_samples
                WHERE metric = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (metric, int(start), int(end)),
            ).fetchall()
        return [(int(timestamp), float(value)) for timestamp, value in rows]

    def apply_retention(self, retention_days, now=None):
        if retention_days is None or int(retention_days) <= 0:
            return
        if now is None:
            now = int(time.time())
        cutoff = int(now) - (int(retention_days) * 24 * 60 * 60)
        with self.connect() as conn:
            conn.execute("DELETE FROM metric_samples WHERE timestamp < ?", (cutoff,))
