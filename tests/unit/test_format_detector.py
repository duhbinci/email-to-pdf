from __future__ import annotations

import pytest

from email_to_pdf.adapters.parsers.format_detector import FormatDetector
from email_to_pdf.domain.errors import UnsupportedFormatError


@pytest.fixture
def detector() -> FormatDetector:
    return FormatDetector()


class TestMsgDetection:
    def test_cfbf_magic_bytes_detected_as_msg(self, detector: FormatDetector) -> None:
        data = b"\xd0\xcf\x11\xe0" + b"\x00" * 512
        assert detector.detect(data) == "msg"

    def test_cfbf_magic_with_real_content(self, detector: FormatDetector) -> None:
        data = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512
        assert detector.detect(data) == "msg"

    def test_partial_magic_not_detected_as_msg(self, detector: FormatDetector) -> None:
        data = b"\xd0\xcf\x11" + b"From: test@example.com\r\nSubject: Test\r\n\r\nbody"
        result = detector.detect(data)
        assert result == "eml"


class TestEmlDetection:
    def test_simple_eml_detected(self, detector: FormatDetector) -> None:
        data = b"From: sender@example.com\r\nTo: recipient@example.com\r\nSubject: Hello\r\n\r\nBody"
        assert detector.detect(data) == "eml"

    def test_eml_with_mime_headers(self, detector: FormatDetector) -> None:
        data = (
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: text/plain\r\n"
            b"Subject: Test\r\n"
            b"\r\n"
            b"Hello world"
        )
        assert detector.detect(data) == "eml"

    def test_eml_with_lf_line_endings(self, detector: FormatDetector) -> None:
        data = b"From: sender@example.com\nTo: recipient@example.com\nSubject: Test\n\nBody"
        assert detector.detect(data) == "eml"

    def test_eml_with_message_id(self, detector: FormatDetector) -> None:
        data = b"Message-ID: <abc123@example.com>\r\nFrom: a@b.com\r\n\r\nbody"
        assert detector.detect(data) == "eml"


class TestUnsupportedFormat:
    def test_random_bytes_raise_error(self, detector: FormatDetector) -> None:
        data = b"\x00\x01\x02\x03\x04\x05" * 100
        with pytest.raises(UnsupportedFormatError):
            detector.detect(data)

    def test_empty_bytes_raise_error(self, detector: FormatDetector) -> None:
        with pytest.raises(UnsupportedFormatError):
            detector.detect(b"")

    def test_binary_data_raise_error(self, detector: FormatDetector) -> None:
        data = bytes(range(256)) * 10
        with pytest.raises(UnsupportedFormatError):
            detector.detect(data)

    def test_jpeg_bytes_raise_error(self, detector: FormatDetector) -> None:
        data = b"\xff\xd8\xff\xe0" + b"\x00" * 512
        with pytest.raises(UnsupportedFormatError):
            detector.detect(data)

    def test_png_bytes_raise_error(self, detector: FormatDetector) -> None:
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 512
        with pytest.raises(UnsupportedFormatError):
            detector.detect(data)
