"""Tests for `src.gateway.strip_json_fences` (Gemini markdown-fence stripper)."""

from __future__ import annotations

from src.gateway import strip_json_fences


def test_strips_json_fences() -> None:
    text = '```json\n{"a": 1}\n```'
    assert strip_json_fences(text) == '{"a": 1}'


def test_strips_plain_fences() -> None:
    text = '```\n{"a": 1}\n```'
    assert strip_json_fences(text) == '{"a": 1}'


def test_returns_bare_json_unchanged() -> None:
    assert strip_json_fences('{"a": 1}') == '{"a": 1}'


def test_returns_empty_for_blank_input() -> None:
    assert strip_json_fences("") == ""
    assert strip_json_fences("   ") == ""


def test_unclosed_fence_returns_remainder() -> None:
    text = '```json\n{"a": 1}'
    # No closing fence; returns everything after the opening tag line.
    assert strip_json_fences(text) == '{"a": 1}'


def test_idempotent_when_no_fence() -> None:
    text = 'just some text'
    assert strip_json_fences(text) == text


def test_handles_array_with_fence() -> None:
    text = '```json\n[1, 2, 3]\n```'
    assert strip_json_fences(text) == '[1, 2, 3]'


def test_strips_leading_whitespace() -> None:
    text = '   ```json\n{"a": 1}\n```   '
    assert strip_json_fences(text) == '{"a": 1}'
