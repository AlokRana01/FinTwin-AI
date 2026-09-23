"""Test removal of artificial response-length limits and verification of long response rendering."""
import pytest
from utils.chatbot import _format_chat_markdown, _build_system_prompt, _call_groq, _call_gemini_backend


def test_system_prompt_has_no_word_limit():
    prompt = _build_system_prompt(None)
    assert "under 500 words" not in prompt
    assert "usually under" not in prompt


def test_markdown_formatter_handles_very_long_response():
    # Construct a deliberately long response (3,000+ words, multi-section)
    paragraphs = []
    paragraphs.append("## Long-Term Financial Master Plan\n")
    for i in range(1, 301):
        paragraphs.append(f"{i}. Recommendation {i}: Allocate savings towards diversified mutual funds, PPF, and emergency reserve funds.")
    paragraphs.append("\n### Detailed Summary Table\n")
    paragraphs.append("| Category | Recommendation | Target Timeline |")
    paragraphs.append("| :--- | :--- | :--- |")
    for i in range(1, 51):
        paragraphs.append(f"| Goal {i} | SIP Investment {i} | Year {i % 10 + 1} |")

    full_response = "\n".join(paragraphs)
    assert len(full_response) > 15000, "Test input should be sufficiently long"

    formatted_html = _format_chat_markdown(full_response)
    # Check that all 300 numbered items and 50 table rows were converted without truncation
    assert formatted_html.count("<li") == 300
    assert formatted_html.count("<tr") == 51  # 1 header + 50 body rows
    assert "Goal 50" in formatted_html
    assert "Recommendation 300" in formatted_html


def test_api_payload_max_tokens_increased(monkeypatch):
    import requests

    groq_payload_captured = {}
    gemini_payload_captured = {}

    def mock_post(url, *args, **kwargs):
        class DummyResp:
            status_code = 200
            def json(self):
                return {
                    "choices": [{"message": {"content": "Sample long reply"}}],
                    "candidates": [{"content": {"parts": [{"text": "Sample long reply"}]}}],
                }

        json_body = kwargs.get("json", {})
        if "max_tokens" in json_body:
            groq_payload_captured.update(json_body)
        if "generationConfig" in json_body:
            gemini_payload_captured.update(json_body)
        return DummyResp()

    monkeypatch.setattr(requests, "post", mock_post)

    _call_groq(None, [{"role": "user", "text": "hello"}], "test_groq_key")
    assert groq_payload_captured.get("max_tokens") >= 4096, "Groq max_tokens should be >= 4096"

    _call_gemini_backend(None, [{"role": "user", "text": "hello"}], "test_gemini_key")
    assert gemini_payload_captured.get("generationConfig", {}).get("maxOutputTokens") >= 4096, "Gemini maxOutputTokens should be >= 4096"
