"""Verify that repeated launches preserve an existing project database."""
from unittest import TestCase
from unittest.mock import MagicMock, patch
from threading import Event, Thread
from urllib.request import urlopen

from werkzeug.serving import make_server

import db_tools
import start


class BrowserStartupTest(TestCase):
    def test_browser_failure_prints_manual_url(self):
        for outcome in (False, start.webbrowser.Error("unavailable"), OSError("unavailable")):
            with self.subTest(outcome=outcome):
                options = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with patch.object(start.webbrowser, "open", **options), patch("builtins.print") as output:
                    start.open_browser(start.APP_URL)
                output.assert_called_once_with(f"Open {start.APP_URL} in your browser.", flush=True)

    def test_bind_failure_does_not_launch_browser_thread(self):
        with patch("werkzeug.serving.make_server", side_effect=OSError("port occupied")), patch.object(start, "Thread") as thread:
            with self.assertRaisesRegex(OSError, "port occupied"):
                start.serve_interface(MagicMock())
        thread.assert_not_called()

    def test_server_serves_http_and_opens_browser_once(self):
        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"launcher ready"]

        server = make_server("127.0.0.1", 0, app, threaded=True)
        url = f"http://127.0.0.1:{server.server_port}"
        browser_called = Event()

        def browser_open(*args, **kwargs):
            browser_called.set()
            return True

        with patch("werkzeug.serving.make_server", return_value=server), patch.object(start, "APP_URL", url), patch.object(start.webbrowser, "open", side_effect=browser_open) as browser:
            serving = Thread(target=start.serve_interface, args=(app,), daemon=True)
            serving.start()
            try:
                self.assertTrue(browser_called.wait(5), "Browser callback was not invoked")
                with urlopen(url, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), b"launcher ready")
                browser.assert_called_once_with(url, new=2)
            finally:
                server.shutdown()
                serving.join(timeout=5)
                server.server_close()
            self.assertFalse(serving.is_alive(), "Server did not stop")


class StartupDatabaseTest(TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        for name, value in (
            ("load_config", {"database": "test_project"}),
            ("connect", self.connection),
            ("validate_server", "8.4.0"),
            ("setup", None),
        ):
            mock_patch = patch.object(db_tools, name, return_value=value)
            setattr(self, name, mock_patch.start())
            self.addCleanup(mock_patch.stop)

    def test_absent_or_empty_database_is_initialized(self):
        self.cursor.fetchall.return_value = []
        start.prepare_database(db_tools)
        self.setup.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_complete_database_is_preserved_without_reseeding(self):
        self.cursor.fetchall.return_value = [
            *((table, "BASE TABLE") for table in db_tools.TABLES),
            ("reservation_details", "VIEW"), ("employee_details", "VIEW"),
        ]
        start.prepare_database(db_tools)
        self.setup.assert_not_called()
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.connection.close.assert_called_once_with()

    def test_partial_database_is_rejected_without_changes(self):
        self.cursor.fetchall.return_value = [("customer", "BASE TABLE")]
        with self.assertRaisesRegex(RuntimeError, "No data was changed"):
            start.prepare_database(db_tools)
        self.setup.assert_not_called()
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.connection.close.assert_called_once_with()
