class KstError(Exception):
    """Base exception class for all Kst related errors."""


class InvalidRepositoryError(KstError):
    """Raised when a repository is not valid."""


class GitRepositoryError(KstError):
    """Raised when a git command fails."""


class ApiClientError(KstError):
    """Base exception class for all ApiClient related errors."""


class InvalidRepositoryMemberError(KstError):
    """Raised when a repository member is invalid."""


# --- Script Exceptions ---
class InvalidScriptError(InvalidRepositoryMemberError):
    """Raised when a script or its info file is invalid."""


class MissingScriptError(InvalidRepositoryMemberError):
    """Raised when a script is missing."""


class DuplicateScriptError(InvalidRepositoryMemberError):
    """Raised when a script is duplicated."""


# --- Profile Exceptions ---
class InvalidProfileError(InvalidRepositoryMemberError):
    """Raised when a profile or its info file is invalid."""


class MissingProfileError(InvalidRepositoryMemberError):
    """Raised when a profile is missing."""


class DuplicateProfileError(InvalidRepositoryMemberError):
    """Raised when a profile is duplicated."""


# --- Info Exceptions ---
class InvalidInfoFileError(InvalidRepositoryMemberError):
    """Raised when an info file is invalid."""


class MissingInfoFileError(InvalidRepositoryMemberError):
    """Raised when an info file is missing."""


class DuplicateInfoFileError(InvalidRepositoryMemberError):
    """Raised when an info file is duplicated."""
