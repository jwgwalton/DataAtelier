"""Tests for text extractors."""

import pytest
from dataatelier import extractors


def test_robust_decode_utf8():
    """Test UTF-8 decoding."""
    data = "Hello, World!".encode('utf-8')
    result = extractors.robust_decode(data)
    assert result == "Hello, World!"


def test_robust_decode_latin1():
    """Test Latin-1 decoding."""
    data = "Café".encode('latin-1')
    result = extractors.robust_decode(data)
    assert "Caf" in result


def test_extract_text_preview_plaintext():
    """Test plain text extraction."""
    content = b"This is a test file with some content."
    result = extractors.extract_text_preview(content, "text/plain", 1024)
    assert "test file" in result


def test_extract_text_preview_json():
    """Test JSON extraction."""
    content = b'{"key": "value", "number": 123}'
    result = extractors.extract_text_preview(content, "application/json", 1024)
    assert "key" in result
    assert "value" in result


def test_extract_text_preview_xml():
    """Test XML extraction."""
    content = b'<root><item>test</item></root>'
    result = extractors.extract_text_preview(content, "application/xml", 1024)
    assert "root" in result
    assert "item" in result


def test_extract_text_preview_binary():
    """Test binary file handling."""
    content = b'\x00\x01\x02\x03\x04\x05'
    result = extractors.extract_text_preview(content, "application/octet-stream", 1024)
    assert "Binary" in result or "bytes" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
