
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
