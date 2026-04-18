from __future__ import annotations

import re
from typing import Literal

from email_to_pdf.domain.errors import UnsupportedFormatError

_CFBF_MAGIC = b"\xd0\xcf\x11\xe0"
_RFC5322_HEADER = re.compile(
    rb"^[\x21-\x7e]+:[ \t]",
    re.MULTILINE,
)


class FormatDetector:
    def detect(self, data: bytes) -> Literal["eml", "msg"]:
        if data[:4] == _CFBF_MAGIC:
            return "msg"

        sample = data[:4096]
        if _RFC5322_HEADER.search(sample):
            return "eml"

        if b"\r\n" in data[:256] or b"\n" in data[:256]:
            first_line = data.split(b"\n", 1)[0]
            if b":" in first_line and len(first_line) < 998:
                return "eml"

        raise UnsupportedFormatError(
            f"Cannot determine email format from content (first 4 bytes: {data[:4]!r})"
        )
