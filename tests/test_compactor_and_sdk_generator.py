"""Tests for DbCompactor, CacheCompactor, and SdkDocGenerator."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from pipeline.db_compactor import (
    CacheCompactor,
    CacheCompactResult,
    DbCompactor,
    MaintenanceResult,
    PruneResult,
    run_local_maintenance,
)
from pipeline.sdk_doc_generator import (
    ClassDoc,
    FunctionDoc,
    ModuleDoc,
    SdkDocGenerator,
    build_offline_sdk_docs,
    extract_module_doc,
    render_html,
)


# ===========================================================================
# Task 11: Database Compactor & Cache Compactor
# ===========================================================================


class TestDbCompactor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "jobs.db"
        self.compactor = DbCompactor(self.db_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ensure_schema_creates_table(self):
        self.assertFalse(self.db_path.exists())
        self.compactor.ensure_schema()
        self.assertTrue(self.db_path.exists())
        
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "jobs")
        finally:
            conn.close()

    def test_insert_and_row_count(self):
        self.assertEqual(self.compactor.row_count(), 0)
        self.compactor.insert_job("j1", "queued")
        self.compactor.insert_job("j2", "running")
        self.compactor.insert_job("j3", "done")
        
        self.assertEqual(self.compactor.row_count(), 3)
        self.assertEqual(self.compactor.row_count("queued"), 1)
        self.assertEqual(self.compactor.row_count("running"), 1)
        self.assertEqual(self.compactor.row_count("done"), 1)

    def test_prune_older_than_days(self):
        # Insert jobs with synthetic timestamps
        # 40 days old done job -> should be deleted
        self.compactor.insert_job("j1", "done", age_days=40.0)
        # 10 days old done job -> should keep
        self.compactor.insert_job("j2", "done", age_days=10.0)
        # 40 days old running job -> should keep because running is protected
        self.compactor.insert_job("j3", "running", age_days=40.0)
        # 40 days old queued job -> should keep because queued is protected
        self.compactor.insert_job("j4", "queued", age_days=40.0)
        # 40 days old failed job -> should be deleted
        self.compactor.insert_job("j5", "failed", age_days=40.0)

        result = self.compactor.prune(older_than_days=30.0, run_vacuum=True)
        self.assertEqual(result.rows_deleted, 2)
        self.assertTrue(result.vacuumed)
        self.assertEqual(self.compactor.row_count(), 3)
        
        # Check remaining jobs
        self.assertEqual(self.compactor.row_count("done"), 1)
        self.assertEqual(self.compactor.row_count("running"), 1)
        self.assertEqual(self.compactor.row_count("queued"), 1)

    def test_prune_vacuum_off(self):
        self.compactor.insert_job("j1", "done", age_days=40.0)
        result = self.compactor.prune(older_than_days=30.0, run_vacuum=False)
        self.assertEqual(result.rows_deleted, 1)
        self.assertFalse(result.vacuumed)

    def test_prune_error_handling(self):
        # Point DbCompactor to a directory path which will cause SQLite errors
        bad_compactor = DbCompactor(Path(self._tmp.name))
        result = bad_compactor.prune()
        self.assertIsNotNone(result.error)

    def test_prune_result_properties(self):
        r = PruneResult(
            rows_deleted=5,
            size_before_bytes=2048,
            size_after_bytes=1024,
            vacuumed=True,
            duration_ms=12.5,
            error=None
        )
        self.assertEqual(r.bytes_reclaimed, 1024)
        d = r.to_dict()
        self.assertEqual(d["rows_deleted"], 5)
        self.assertEqual(d["bytes_reclaimed"], 1024)
        self.assertTrue(d["vacuumed"])


class TestCacheCompactor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._tmp.name) / "cache"
        self.cache_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _create_file(self, name: str, size: int, age_days: float) -> Path:
        f = self.cache_dir / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * size)
        
        # Set mtime
        mtime = time.time() - age_days * 86400
        os.utime(f, (mtime, mtime))
        return f

    def test_compact_stale_files_by_age(self):
        # 10 days old file (max age is 7 days)
        f1 = self._create_file("old.tmp", 100, age_days=10.0)
        # 2 days old file
        f2 = self._create_file("new.tmp", 200, age_days=2.0)

        compactor = CacheCompactor(self.cache_dir, max_age_days=7.0, max_size_bytes=1000)
        result = compactor.compact()
        
        self.assertEqual(result.files_removed, 1)
        self.assertEqual(result.bytes_removed, 100)
        self.assertFalse(f1.exists())
        self.assertTrue(f2.exists())

    def test_compact_by_size_quota(self):
        # Total size limit is 500 bytes.
        # Create 3 new files (all under 7 days) with total size 900 bytes.
        # mtimes: f1 is oldest, f2 is middle, f3 is newest.
        f1 = self._create_file("oldest.tmp", 300, age_days=3.0)
        f2 = self._create_file("middle.tmp", 300, age_days=2.0)
        f3 = self._create_file("newest.tmp", 300, age_days=1.0)

        compactor = CacheCompactor(self.cache_dir, max_age_days=7.0, max_size_bytes=500)
        result = compactor.compact()

        # It should delete oldest.tmp (300b) and middle.tmp (300b)
        # to bring total size down from 900b to 300b (which is <= 500b)
        self.assertEqual(result.files_removed, 2)
        self.assertEqual(result.bytes_removed, 600)
        self.assertFalse(f1.exists())
        self.assertFalse(f2.exists())
        self.assertTrue(f3.exists())

    def test_protected_suffixes(self):
        # Lock files should be skipped
        f1 = self._create_file("old.lock", 300, age_days=10.0)
        f2 = self._create_file("old.active", 300, age_days=10.0)
        f3 = self._create_file("old.tmp", 300, age_days=10.0)

        compactor = CacheCompactor(
            self.cache_dir,
            max_age_days=7.0,
            max_size_bytes=100,
            protected_suffixes=(".lock", ".active"),
        )
        result = compactor.compact()

        # Only old.tmp should be removed
        self.assertEqual(result.files_removed, 1)
        self.assertEqual(result.bytes_removed, 300)
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertFalse(f3.exists())

    def test_total_size(self):
        compactor = CacheCompactor(self.cache_dir)
        self.assertEqual(compactor.total_size(), 0)

        self._create_file("a.tmp", 100, 0)
        self._create_file("b.tmp", 150, 0)
        self.assertEqual(compactor.total_size(), 250)

    def test_nonexistent_cache_dir(self):
        compactor = CacheCompactor(Path(self._tmp.name) / "ghost")
        result = compactor.compact()
        self.assertEqual(result.files_removed, 0)
        self.assertEqual(compactor.total_size(), 0)

    def test_compact_result_to_dict(self):
        r = CacheCompactResult(files_removed=3, bytes_removed=500, duration_ms=5.2, error=None)
        d = r.to_dict()
        self.assertEqual(d["files_removed"], 3)
        self.assertEqual(d["bytes_removed"], 500)
        self.assertEqual(d["duration_ms"], 5.2)

    def test_run_local_maintenance_combines_db_and_cache(self):
        db_path = Path(self._tmp.name) / "jobs.db"
        db = DbCompactor(db_path)
        db.insert_job("old", "done", age_days=40.0)
        old_cache = self._create_file("old-cache.tmp", 123, age_days=10.0)

        result = run_local_maintenance(
            db_path,
            self.cache_dir,
            older_than_days=30.0,
            max_cache_age_days=7.0,
        )

        self.assertIsInstance(result, MaintenanceResult)
        self.assertEqual(result.db.rows_deleted, 1)
        self.assertEqual(result.cache.files_removed, 1)
        self.assertFalse(old_cache.exists())


# ===========================================================================
# Task 12: SdkDocGenerator
# ===========================================================================


class TestSdkDocGenerator(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pipeline_dir = Path(self._tmp.name) / "pipeline"
        self.output_dir = Path(self._tmp.name) / "docs" / "sdk"
        self.pipeline_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extract_module_doc_basic(self):
        source = '''"""Module docstring here."""
class MyPlugin(BasePlugin):
    """Class docstring."""
    def __init__(self, val):
        """Init."""
        self.val = val

    async def run(self, arg1, arg2):
        """Run method."""
        pass

def helper_func(x):
    """Helper."""
    return x
'''
        doc = extract_module_doc(source, name="my_module", path="my_module.py")
        
        self.assertEqual(doc.name, "my_module")
        self.assertEqual(doc.path, "my_module.py")
        self.assertEqual(doc.docstring, "Module docstring here.")
        
        # Verify Class
        self.assertEqual(len(doc.classes), 1)
        cls = doc.classes[0]
        self.assertEqual(cls.name, "MyPlugin")
        self.assertEqual(cls.bases, ["BasePlugin"])
        self.assertEqual(cls.docstring, "Class docstring.")
        
        # Verify Methods
        self.assertEqual(len(cls.methods), 2)
        m0 = cls.methods[0]
        self.assertEqual(m0.name, "__init__")
        self.assertEqual(m0.args, ["val"])
        self.assertFalse(m0.is_async)
        
        m1 = cls.methods[1]
        self.assertEqual(m1.name, "run")
        self.assertEqual(m1.args, ["arg1", "arg2"])
        self.assertTrue(m1.is_async)
        
        # Verify Functions
        self.assertEqual(len(doc.functions), 1)
        f = doc.functions[0]
        self.assertEqual(f.name, "helper_func")
        self.assertEqual(f.args, ["x"])
        self.assertFalse(f.is_async)

    def test_extract_module_doc_syntax_error(self):
        doc = extract_module_doc("class MyPlugin:", name="bad", path="bad.py")
        self.assertEqual(doc.docstring, "[parse error]")

    def test_render_html(self):
        modules = [
            ModuleDoc(
                name="test_mod",
                path="test_mod.py",
                docstring="Mod doc.",
                classes=[
                    ClassDoc(
                        name="TestClass",
                        docstring="Cls doc.",
                        bases=["Base"],
                        methods=[
                            FunctionDoc(name="test_method", docstring="Meth doc.", args=["a", "b"], is_async=True)
                        ]
                    )
                ],
                functions=[
                    FunctionDoc(name="test_func", docstring="Func doc.", args=["x"], is_async=False)
                ]
            )
        ]
        
        html_str = render_html(modules, title="Test SDK Title")
        
        self.assertIn("Test SDK Title", html_str)
        self.assertIn("test_mod", html_str)
        self.assertIn("TestClass", html_str)
        self.assertIn("test_method", html_str)
        self.assertIn("async", html_str)
        self.assertIn("test_func", html_str)

    def test_sdk_doc_generator_collect_and_build(self):
        # Create a dummy module file
        mod_file = self.pipeline_dir / "plugin_sdk.py"
        mod_file.write_text('''"""Sample plugin SDK."""
def register_plugin(plugin):
    """Registers a plugin."""
    pass
''', encoding="utf-8")

        gen = SdkDocGenerator(
            pipeline_dir=self.pipeline_dir,
            output_dir=self.output_dir,
            module_names=["plugin_sdk"]
        )
        
        # test collect
        modules = gen.collect()
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].name, "plugin_sdk")
        
        # test build
        out_path = gen.build("ref.html")
        self.assertTrue(out_path.exists())
        self.assertEqual(out_path, self.output_dir / "ref.html")
        
        # Verify contents of generated file
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("plugin_sdk", content)
        self.assertIn("Registers a plugin.", content)

        # test build_index
        idx = gen.build_index()
        self.assertEqual(idx["modules"][0]["name"], "plugin_sdk")
        self.assertEqual(idx["modules"][0]["functions"], ["register_plugin"])

    def test_build_offline_sdk_docs_default_project_layout(self):
        project = Path(self._tmp.name) / "project"
        pipeline = project / "pipeline"
        pipeline.mkdir(parents=True)
        (pipeline / "plugin_sdk.py").write_text(
            '"""Plugin API."""\ndef register_plugin(plugin):\n    """Register."""\n    return plugin\n',
            encoding="utf-8",
        )

        path = build_offline_sdk_docs(project)

        self.assertTrue(path.exists())
        self.assertEqual(path.name, "sdk_reference.html")
        self.assertIn("Plugin API", path.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
