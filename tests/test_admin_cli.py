
import os
import tempfile
import unittest

_fd, _db_path = tempfile.mkstemp(prefix="citypass-admin-cli-", suffix=".db")
os.close(_fd)

os.environ["CITYPASS_DATABASE"] = _db_path
os.environ["FLASK_SECRET_KEY"] = "test-only-secret-key-not-for-production"

import app as cityapp
from werkzeug.security import check_password_hash


class AdminCliTests(unittest.TestCase):
    def setUp(self):
        cityapp.app.config.update(
            TESTING=True,
            SECRET_KEY="test-only-secret-key",
        )
        with cityapp.app.app_context():
            cityapp.init_db()
            conn = cityapp.db()
            conn.execute("DELETE FROM passes")
            conn.execute("DELETE FROM users")
            conn.commit()

    def run_command(self, name, email, password, confirmation=None):
        runner = cityapp.app.test_cli_runner()
        confirmation = confirmation if confirmation is not None else password
        return runner.invoke(
            cityapp.create_admin,
            input=f"{name}\n{email}\n{password}\n{confirmation}\n",
        )

    def test_create_admin_successfully_hashes_password(self):
        result = self.run_command(
            "First Admin", "first-admin@example.com", "strong-password-123"
        )
        self.assertEqual(result.exit_code, 0, result.output)

        with cityapp.app.app_context():
            row = cityapp.db().execute(
                "SELECT name, role, password_hash FROM users WHERE email=?",
                ("first-admin@example.com",),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "First Admin")
        self.assertEqual(row["role"], "admin")
        self.assertTrue(
            check_password_hash(row["password_hash"], "strong-password-123")
        )

    def test_create_admin_rejects_invalid_email(self):
        result = self.run_command(
            "First Admin", "invalid-email", "strong-password-123"
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("valid name/email", result.output)

    def test_create_admin_rejects_short_password(self):
        result = self.run_command("First Admin", "first-admin@example.com", "short")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("at least 10 characters", result.output)

    def test_create_admin_rejects_empty_name(self):
        result = self.run_command(
            "   ", "first-admin@example.com", "strong-password-123"
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("valid name/email", result.output)

    def test_create_admin_rejects_duplicate_email(self):
        first = self.run_command(
            "First Admin", "first-admin@example.com", "strong-password-123"
        )
        self.assertEqual(first.exit_code, 0, first.output)

        second = self.run_command(
            "Second Admin", "first-admin@example.com", "another-password-123"
        )
        self.assertNotEqual(second.exit_code, 0)
        self.assertIn("email already exists", second.output)

        with cityapp.app.app_context():
            count = cityapp.db().execute(
                "SELECT COUNT(*) FROM users WHERE email=?",
                ("first-admin@example.com",),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_create_admin_rejects_mismatched_password_confirmation(self):
        result = self.run_command(
            "First Admin",
            "first-admin@example.com",
            "strong-password-123",
            confirmation="different-password-123",
        )
        self.assertNotEqual(result.exit_code, 0)

        with cityapp.app.app_context():
            row = cityapp.db().execute(
                "SELECT id FROM users WHERE email=?",
                ("first-admin@example.com",),
            ).fetchone()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main(verbosity=2)
