from __future__ import annotations

import pytest

from email_to_pdf.domain.services.filename_sanitizer import FileNameSanitizer


@pytest.fixture
def sanitizer() -> FileNameSanitizer:
    return FileNameSanitizer()


class TestWindowsReservedNames:
    def test_con_is_sanitised(self, sanitizer: FileNameSanitizer) -> None:
        assert sanitizer.sanitise("CON") != "CON"

    def test_prn_is_sanitised(self, sanitizer: FileNameSanitizer) -> None:
        assert sanitizer.sanitise("PRN") != "PRN"

    def test_aux_is_sanitised(self, sanitizer: FileNameSanitizer) -> None:
        assert sanitizer.sanitise("AUX") != "AUX"

    def test_nul_is_sanitised(self, sanitizer: FileNameSanitizer) -> None:
        assert sanitizer.sanitise("NUL") != "NUL"

    @pytest.mark.parametrize("name", [f"COM{i}" for i in range(1, 10)])
    def test_com_devices_are_sanitised(
        self, sanitizer: FileNameSanitizer, name: str
    ) -> None:
        result = sanitizer.sanitise(name)
        assert result.upper() != name.upper()

    @pytest.mark.parametrize("name", [f"LPT{i}" for i in range(1, 10)])
    def test_lpt_devices_are_sanitised(
        self, sanitizer: FileNameSanitizer, name: str
    ) -> None:
        result = sanitizer.sanitise(name)
        assert result.upper() != name.upper()

    def test_reserved_name_with_extension_is_sanitised(
        self, sanitizer: FileNameSanitizer
    ) -> None:
        result = sanitizer.sanitise("CON.txt")
        assert "CON" not in result.upper().split(".")[0]

    def test_non_reserved_name_is_unchanged(self, sanitizer: FileNameSanitizer) -> None:
        assert sanitizer.sanitise("report.pdf") == "report.pdf"


class TestIllegalCharacters:
    @pytest.mark.parametrize("char", ["/", "\\", ":", "*", "?", '"', "<", ">", "|"])
    def test_illegal_char_replaced_with_underscore(
        self, sanitizer: FileNameSanitizer, char: str
    ) -> None:
        result = sanitizer.sanitise(f"file{char}name.txt")
        assert char not in result
        assert "_" in result

    def test_multiple_illegal_chars(self, sanitizer: FileNameSanitizer) -> None:
        result = sanitizer.sanitise("file:name?here.txt")
        assert ":" not in result
        assert "?" not in result

    def test_legal_chars_preserved(self, sanitizer: FileNameSanitizer) -> None:
        result = sanitizer.sanitise("my-file_name (1).txt")
        assert result == "my-file_name (1).txt"


class TestPathSeparators:
    def test_forward_slash_stripped(self, sanitizer: FileNameSanitizer) -> None:
        result = sanitizer.sanitise("path/to/file.txt")
        assert "/" not in result
        assert result == "file.txt"

    def test_backslash_stripped(self, sanitizer: FileNameSanitizer) -> None:
        result = sanitizer.sanitise("path\\to\\file.txt")
        assert "\\" not in result
        assert result == "file.txt"

    def test_absolute_path_stripped(self, sanitizer: FileNameSanitizer) -> None:
        result = sanitizer.sanitise("/etc/passwd")
        assert "/" not in result
        assert "passwd" in result

    def test_dotdot_path_stripped(self, sanitizer: FileNameSanitizer) -> None:
        result = sanitizer.sanitise("../../../etc/passwd")
        assert "/" not in result
        assert "passwd" in result


class TestDeduplication:
    def test_duplicate_suffix_appended(self, sanitizer: FileNameSanitizer) -> None:
        used: set[str] = {"file.txt"}
        result = sanitizer.sanitise("file.txt", used_names=used)
        assert result == "file (1).txt"

    def test_second_duplicate_gets_2(self, sanitizer: FileNameSanitizer) -> None:
        used: set[str] = {"file.txt", "file (1).txt"}
        result = sanitizer.sanitise("file.txt", used_names=used)
        assert result == "file (2).txt"

    def test_non_duplicate_unchanged(self, sanitizer: FileNameSanitizer) -> None:
        used: set[str] = {"other.txt"}
        result = sanitizer.sanitise("file.txt", used_names=used)
        assert result == "file.txt"

    def test_used_names_updated_after_sanitise(
        self, sanitizer: FileNameSanitizer
    ) -> None:
        used: set[str] = set()
        sanitizer.sanitise("file.txt", used_names=used)
        assert "file.txt" in used

    def test_sequential_deduplication(self, sanitizer: FileNameSanitizer) -> None:
        used: set[str] = set()
        names = [sanitizer.sanitise("report.pdf", used_names=used) for _ in range(3)]
        assert names[0] == "report.pdf"
        assert names[1] == "report (1).pdf"
        assert names[2] == "report (2).pdf"


class TestEmptyName:
    def test_empty_string_becomes_unnamed(self, sanitizer: FileNameSanitizer) -> None:
        assert sanitizer.sanitise("") == "unnamed"

    def test_whitespace_only_becomes_unnamed(
        self, sanitizer: FileNameSanitizer
    ) -> None:
        assert sanitizer.sanitise("   ") == "unnamed"

    def test_dots_only_becomes_unnamed(self, sanitizer: FileNameSanitizer) -> None:
        assert sanitizer.sanitise("...") == "unnamed"
