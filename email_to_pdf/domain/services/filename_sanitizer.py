from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath

_WINDOWS_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)

_ILLEGAL_CHARS = re.compile(r'[/\\:*?"<>|]')
_TRAILING_DOTS_SPACES = re.compile(r"[\s.]+$")
_LEADING_DOTS_SPACES = re.compile(r"^[\s.]+")


class FileNameSanitizer:
    def sanitise(self, filename: str, used_names: set[str] | None = None) -> str:
        name = self._strip_path_separators(filename)
        name = _ILLEGAL_CHARS.sub("_", name)
        name = _TRAILING_DOTS_SPACES.sub("", name)
        name = _LEADING_DOTS_SPACES.sub("", name)
        name = name.strip()

        if not name:
            name = "unnamed"

        stem, ext = self._split_stem_ext(name)
        if stem.upper() in _WINDOWS_RESERVED:
            stem = "unnamed"
            name = f"{stem}{ext}"

        if used_names is not None:
            name = self._deduplicate(stem, ext, used_names)

        return name

    def _strip_path_separators(self, filename: str) -> str:
        slash_count = filename.count("/") + filename.count("\\")
        if slash_count == 1:
            # Single embedded separator: replace with underscore to preserve filename
            return filename.replace("/", "_").replace("\\", "_")
        elif slash_count > 1:
            # Multiple separators: looks like a path, take basename only
            try:
                name = PureWindowsPath(filename).name
            except Exception:
                name = filename
            try:
                name = PurePosixPath(name).name
            except Exception:
                pass
            return name
        return filename

    def _split_stem_ext(self, name: str) -> tuple[str, str]:
        dot_idx = name.rfind(".")
        if dot_idx <= 0:
            return name, ""
        return name[:dot_idx], name[dot_idx:]

    def _deduplicate(self, stem: str, ext: str, used_names: set[str]) -> str:
        candidate = f"{stem}{ext}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        counter = 1
        while True:
            candidate = f"{stem} ({counter}){ext}"
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate
            counter += 1
