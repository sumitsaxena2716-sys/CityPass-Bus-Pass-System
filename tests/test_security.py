
import sys
from pathlib import Path

# Make the project root importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as citypass


def test_post_without_csrf_token_is_rejected():
    citypass.app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
    )

    with citypass.app.test_client() as client:
        response = client.post(
            "/login",
            data={
                "email": "test@example.com",
                "password": "wrong-password",
            },
        )

        assert response.status_code == 400


def test_post_with_invalid_csrf_token_is_rejected():
    citypass.app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
    )

    with citypass.app.test_client() as client:
        with client.session_transaction() as session:
            session["csrf"] = "expected-token"

        response = client.post(
            "/login",
            data={
                "email": "test@example.com",
                "password": "wrong-password",
                "csrf_token": "incorrect-token",
            },
        )

        assert response.status_code == 400

def test_security_headers_are_present():
    with citypass.app.test_client() as client:
        response = client.get("/")

        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert response.headers.get("Permissions-Policy") == (
            "camera=(), microphone=(), geolocation=()"
        )

        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "object-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp


def test_session_cookie_security_configuration():
    assert citypass.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert citypass.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert citypass.app.config["PERMANENT_SESSION_LIFETIME"] == 3600