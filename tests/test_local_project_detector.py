"""No real model requests: validate routing, bounded output and exact matches."""

import io
import json

import pytest

from pseudokrat.ki_office import ProjectError
from pseudokrat.pii.local_project_detector import LocalProjectDetector


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/v1",
        "http://8.8.8.8/v1",
        "file:///tmp/x",
        "http://user:password@127.0.0.1:1234/v1",
    ],
)
def test_external_or_credential_urls_are_rejected(endpoint):
    with pytest.raises(ProjectError):
        LocalProjectDetector(endpoint, "gpt-oss-120b")


def test_private_spark_requires_explicit_local_network_permission():
    with pytest.raises(ProjectError):
        LocalProjectDetector("http://192.168.1.50:8000/v1", "gpt-oss-120b")
    LocalProjectDetector("http://192.168.1.50:8000/v1", "gpt-oss-120b", allow_lan=True)


def test_only_exact_substrings_are_accepted(monkeypatch):
    detector = LocalProjectDetector("http://127.0.0.1:1234/v1", "gpt-oss-120b")
    body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "entities": [
                                {"text": "Geheimfirma", "type": "ORG"},
                                {"text": "Erfunden", "type": "PERSON"},
                                {"text": "1234", "type": "PERSON"},
                            ]
                        }
                    )
                }
            }
        ]
    }
    monkeypatch.setattr(detector, "_request", lambda _payload: body)
    spans = detector.analyze("Geheimfirma erhält 1234 EUR.")
    assert [s.text for s in spans] == ["Geheimfirma"]


def test_bad_model_response_fails_closed(monkeypatch):
    detector = LocalProjectDetector("http://127.0.0.1:1234/v1", "gpt-oss-120b")
    monkeypatch.setattr(detector, "_request", lambda _payload: {"choices": []})
    with pytest.raises(ProjectError):
        detector.analyze("Vertraulicher Text")


def test_http_payload_uses_selected_model_without_proxy_or_redirects(monkeypatch):
    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen.update(json.loads(request.data))
            assert request.full_url == "http://127.0.0.1:1234/v1/chat/completions"
            return io.BytesIO(
                json.dumps({"choices": [{"message": {"content": '{"entities":[]}'}}]}).encode()
            )

    monkeypatch.setattr("urllib.request.build_opener", lambda *handlers: Opener())
    detector = LocalProjectDetector("http://127.0.0.1:1234/v1", "gpt-oss-120b")
    assert detector.analyze("Normaler Text") == []
    assert seen["model"] == "gpt-oss-120b"
    assert seen["stream"] is False
