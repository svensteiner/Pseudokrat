"""Tests für den Secret-Recognizer (API-Keys, Tokens)."""

from __future__ import annotations

import pytest

from pseudokrat.recognizers.secret import SecretRecognizer


@pytest.fixture
def recognizer() -> SecretRecognizer:
    return SecretRecognizer()


@pytest.mark.parametrize(
    "secret",
    [
        "sk-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "sk-ant-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    ],
)
def test_openai_anthropic_keys(recognizer: SecretRecognizer, secret: str) -> None:
    text = f"API_KEY={secret}"
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].category == "SECRET"
    assert spans[0].text == secret


def test_aws_access_key(recognizer: SecretRecognizer) -> None:
    text = "AWS_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE."
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text == "AKIAIOSFODNN7EXAMPLE"


def test_github_token_classic(recognizer: SecretRecognizer) -> None:
    token = "ghp_" + "a" * 36
    text = f"Token: {token}"
    spans = recognizer.analyze(text)
    assert len(spans) == 1
    assert spans[0].text == token


def test_github_pat_new_format(recognizer: SecretRecognizer) -> None:
    token = "github_pat_" + "x" * 30
    spans = recognizer.analyze(f"export TOK={token}")
    assert len(spans) == 1
    assert spans[0].text == token


def test_slack_token(recognizer: SecretRecognizer) -> None:
    token = "xoxb-1234567890-AbCdEfGhIjKlMnOp"
    spans = recognizer.analyze(f"Slack: {token}")
    assert len(spans) == 1


def test_google_api_key(recognizer: SecretRecognizer) -> None:
    key = "AIza" + "B" * 35
    spans = recognizer.analyze(f"google={key}")
    assert len(spans) == 1


def test_jwt(recognizer: SecretRecognizer) -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
        "abcdefghijklmnop"
    )
    spans = recognizer.analyze(f"Authorization: Bearer {jwt}")
    assert any(s.text == jwt for s in spans)


def test_bearer_token(recognizer: SecretRecognizer) -> None:
    spans = recognizer.analyze("Authorization: Bearer abcDEF1234567890ABCDEF==")
    assert len(spans) == 1
    assert spans[0].text == "abcDEF1234567890ABCDEF=="


def test_does_not_match_random_word(recognizer: SecretRecognizer) -> None:
    text = "Das ist normale Beschreibung ohne Secrets."
    assert recognizer.analyze(text) == []


def test_no_double_match(recognizer: SecretRecognizer) -> None:
    # JWT enthält intern keine sk- oder AKIA-Präfixe → keine Überlappung
    key = "sk-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    spans = recognizer.analyze(f"x={key} und y={key}")
    assert len(spans) == 2
