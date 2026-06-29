from __future__ import annotations

from types import SimpleNamespace

from app.api.strategy import _format_ai_test_response, _normalize_openai_base_url
from app.services.stock_analyzer import _normalize_ai_base_url


def test_normalize_openai_base_url_adds_v1_for_root_gateway():
    assert _normalize_openai_base_url("http://ai.zedbox.cn:8080") == "http://ai.zedbox.cn:8080/v1"


def test_normalize_openai_base_url_preserves_v1_base():
    assert _normalize_openai_base_url("http://ai.zedbox.cn:8080/v1") == "http://ai.zedbox.cn:8080/v1"


def test_normalize_openai_base_url_strips_chat_completions_path():
    assert _normalize_openai_base_url("http://ai.zedbox.cn:8080/v1/chat/completions") == "http://ai.zedbox.cn:8080/v1"


def test_stock_analyzer_uses_same_openai_base_url_normalization():
    assert _normalize_ai_base_url("http://ai.zedbox.cn:8080") == "http://ai.zedbox.cn:8080/v1"


def test_format_ai_test_response_handles_object_response():
    resp = SimpleNamespace(
        model="gpt-test",
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1),
    )

    assert _format_ai_test_response(resp) == {
        "ok": True,
        "model": "gpt-test",
        "usage": {"prompt": 3, "completion": 1},
    }


def test_format_ai_test_response_handles_dict_response():
    resp = {
        "model": "gpt-dict",
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }

    assert _format_ai_test_response(resp) == {
        "ok": True,
        "model": "gpt-dict",
        "usage": {"prompt": 5, "completion": 2},
    }


def test_format_ai_test_response_rejects_string_response_without_attribute_error():
    result = _format_ai_test_response("upstream returned plain text")

    assert result["ok"] is False
    assert "非标准响应" in result["error"]
    assert "object has no attribute" not in result["error"]
