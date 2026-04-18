from __future__ import annotations


class EmailToPdfError(Exception):
    def __init__(
        self,
        message: str,
        *,
        job_id: str | None = None,
        stage: str = "unknown",
        retryable: bool = False,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.job_id = job_id
        self.stage = stage
        self.retryable = retryable
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause


class InputError(EmailToPdfError):
    pass


class UnsupportedFormatError(InputError):
    def __init__(
        self,
        message: str = "Unsupported email format",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="format_detection", retryable=False, cause=cause)


class InputReadError(InputError):
    def __init__(
        self,
        message: str = "Failed to read input",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="input_read", retryable=False, cause=cause)


class ParseError(EmailToPdfError):
    pass


class EmlParseError(ParseError):
    def __init__(
        self,
        message: str = "Failed to parse EML",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="eml_parse", retryable=False, cause=cause)


class MsgParseError(ParseError):
    def __init__(
        self,
        message: str = "Failed to parse MSG",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="msg_parse", retryable=False, cause=cause)


class NormalisationError(EmailToPdfError):
    def __init__(
        self,
        message: str = "Normalisation failed",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="normalisation", retryable=False, cause=cause)


class SanitisationError(NormalisationError):
    def __init__(
        self,
        message: str = "HTML sanitisation failed",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, cause=cause)
        self.stage = "sanitisation"


class RenderError(EmailToPdfError):
    pass


class RenderTimeoutError(RenderError):
    def __init__(
        self,
        message: str = "Render timed out",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="render", retryable=False, cause=cause)


class BrowserCrashError(RenderError):
    def __init__(
        self,
        message: str = "Browser crashed",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="render", retryable=True, cause=cause)


class StorageError(EmailToPdfError):
    pass


class WritePermissionError(StorageError):
    def __init__(
        self,
        message: str = "Storage write permission denied",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="storage", retryable=True, cause=cause)


class PathTraversalError(StorageError):
    def __init__(
        self,
        message: str = "Path traversal detected",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="storage", retryable=False, cause=cause)


class ConfigurationError(EmailToPdfError):
    def __init__(
        self,
        message: str = "Configuration error",
        *,
        job_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, job_id=job_id, stage="configuration", retryable=False, cause=cause)
