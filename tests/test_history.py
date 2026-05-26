import os
import sqlite3
import tempfile
import time
import unittest

from pironman5.history import SQLiteHistory


class SQLiteHistoryTest(unittest.TestCase):
    def test_records_and_reads_metric_series(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "history.sqlite3")
            history = SQLiteHistory(db_path)
            history.initialize()

            history.record_metric("cpu_temperature", 42.5, timestamp=1000)
            history.record_metric("cpu_temperature", 43.0, timestamp=1010)
            history.record_metric("memory_percent", 50.0, timestamp=1010)

            series = history.read_series("cpu_temperature", start=999, end=1011)

            self.assertEqual(series, [(1000, 42.5), (1010, 43.0)])

    def test_retention_deletes_old_samples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "history.sqlite3")
            history = SQLiteHistory(db_path)
            history.initialize()

            now = int(time.time())
            old = now - (40 * 24 * 60 * 60)
            recent = now - (2 * 24 * 60 * 60)
            history.record_metric("cpu_temperature", 40.0, timestamp=old)
            history.record_metric("cpu_temperature", 45.0, timestamp=recent)

            history.apply_retention(retention_days=30, now=now)
            series = history.read_series("cpu_temperature", start=0, end=now)

            self.assertEqual(series, [(recent, 45.0)])

    def test_uses_wal_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "history.sqlite3")
            history = SQLiteHistory(db_path)
            history.initialize()

            with sqlite3.connect(db_path) as conn:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

            self.assertEqual(mode.lower(), "wal")
