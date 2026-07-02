from __future__ import annotations

from app.services.ai_provider import normalize_openai_base_url


def test_normalize_openai_base_url_adds_v1_for_root_gateway():
    assert normalize_openai_base_url("http://ai.zedbox.cn:8080") == "http://ai.zedbox.cn:8080/v1"


def test_normalize_openai_base_url_preserves_v1_base():
    assert normalize_openai_base_url("http://ai.zedbox.cn:8080/v1") == "http://ai.zedbox.cn:8080/v1"


def test_normalize_openai_base_url_strips_chat_completions_path():
    assert normalize_openai_base_url("http://ai.zedbox.cn:8080/v1/chat/completions") == "http://ai.zedbox.cn:8080/v1"
