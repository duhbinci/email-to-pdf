from __future__ import annotations

import re


class ContentTypeCleaner:
    _BOUNDARY_MISSING = re.compile(r'boundary\s*=\s*["\']?\s*["\']?(?:;|$)', re.IGNORECASE)
    _BOUNDARY_RE = re.compile(r'boundary\s*=\s*["\']?([^;"\']+)["\']?', re.IGNORECASE)
    _CHARSET_RE = re.compile(r'charset\s*=\s*["\']?([^;"\']+)["\']?', re.IGNORECASE)

    def repair(self, content_type: str, raw_body: bytes | None = None) -> str:
        if not content_type:
            return "text/plain; charset=utf-8"

        content_type = content_type.strip()

        if ";" not in content_type:
            base = content_type.split("/")
            if len(base) == 2 and "multipart" in content_type.lower():
                boundary = self._infer_boundary(raw_body)
                if boundary:
                    content_type = f'{content_type}; boundary="{boundary}"'
            return content_type

        charset_match = self._CHARSET_RE.search(content_type)
        if charset_match:
            charset = charset_match.group(1).strip().strip('"').strip("'")
            if charset:
                content_type = self._CHARSET_RE.sub(f'charset="{charset}"', content_type)

        return content_type

    def _infer_boundary(self, raw_body: bytes | None) -> str | None:
        if not raw_body:
            return None
        for line in raw_body[:2048].split(b"\n"):
            stripped = line.strip()
            if stripped.startswith(b"--") and len(stripped) > 2:
                boundary = stripped[2:].rstrip(b"-").decode("ascii", errors="replace").strip()
                if boundary:
                    return boundary
        return None

    def clean_charset(self, charset: str | None) -> str:
        if not charset:
            return "utf-8"
        charset = charset.strip().strip('"').strip("'").lower()
        aliases = {
            "utf8": "utf-8",
            "latin1": "latin-1",
            "latin-1": "latin-1",
            "iso-8859-1": "latin-1",
            "windows-1252": "cp1252",
            "us-ascii": "ascii",
        }
        return aliases.get(charset, charset)
