"""Password strength rules shared by _provision, rotate, and recover."""

import re
from pathlib import Path

# Minimum and maximum password length (inclusive)
MIN_LENGTH = 14
MAX_LENGTH = 128

# Lockout configuration: after this many consecutive failures, lock for this many seconds.
# Rationale: 10 failures gives legitimate users margin; 15 minutes (900s) blocks rapid
# brute-force without permanently locking out an account if the attacker spaces failures.
LOCK_FAILURE_THRESHOLD = 10
LOCK_DURATION_SECONDS = 900

_WEAK_PASSWORDS_PATH = Path(__file__).resolve().parent / "data" / "weak_passwords.txt"


def check_password_strength(password: str, username: str = "") -> tuple[bool, str | None]:
    """Check password against all strength rules.

    Returns (ok, reason) where ok is True when the password passes all rules,
    and reason is None on success or a human-readable Japanese message string
    when a rule fails.  The reason message does not contain the password itself
    or any substring that reveals it.

    Rules (in priority order):
    1. Length between 14 and 128 (inclusive).
    2. At least 3 of the 4 character types (lowercase, uppercase, digits, symbols).
    3. Must not contain the username (case-insensitive).
    4. No 5-or-more repetition of the same character.
    5. No ASCII consecutive 5-character sequence (abcde, 12345, etc.).
    6. Must not fully match an entry in weak_passwords.txt (case-insensitive,
       trimmed whitespace).
    """
    # Rule 1: Length
    if not (MIN_LENGTH <= len(password) <= MAX_LENGTH):
        return False, "パスワードは14〜128文字で指定してください"

    # Rule 2: At least 3 of 4 character types
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    # Symbols: any character that is not alphanumeric
    has_symbol = any(not c.isalnum() for c in password)
    type_count = sum([has_lower, has_upper, has_digit, has_symbol])
    if type_count < 3:
        msg = "パスワードは小文字・大文字・数字・記号のいずれか3種類以上を含む必要があります"
        return False, msg

    # Rule 3: Must not contain the username (case-insensitive)
    if username:
        lowered = password.lower()
        if username.lower() in lowered:
            return False, "パスワードに利用者IDを含めることはできません"

    # Rule 4: No 5-or-more repetition of the same character
    if re.search(r"(.)\1{4,}", password):
        return False, "パスワードに同じ文字が5文字以上連続して含まれることはできません"

    # Rule 5: No ASCII consecutive 5-character sequence (abcde, 12345, etc.)
    # Check for any 5-character consecutive ASCII letter or digit sequence.
    # Use uppercasing to handle case-insensitivity in one pass.
    upper = password.upper()
    for i in range(len(upper) - 4):
        segment = upper[i : i + 5]
        if segment.isalpha() or segment.isdigit():
            # All 5 chars must be exactly +1 each step
            if all(ord(segment[j]) == ord(segment[j - 1]) + 1 for j in range(1, 5)):
                return False, "パスワードにASCIIの連続する5文字以上を含むことはできません"

    # Rule 6: Check against weak_passwords.txt (full match, case-insensitive, trimmed)
    try:
        with open(_WEAK_PASSWORDS_PATH, encoding="utf-8") as f:
            for line in f:
                entry = line.strip()
                if not entry:
                    continue
                if password.lower().strip() == entry.lower():
                    return False, "パスワードはよく使われるパスワードです"
    except FileNotFoundError:
        # If the file doesn't exist yet, skip this check
        pass

    return True, None


def load_weak_passwords() -> set[str]:
    """Load the weak password list from disk (case-folded, trimmed)."""
    words: set[str] = set()
    try:
        with open(_WEAK_PASSWORDS_PATH, encoding="utf-8") as f:
            for line in f:
                entry = line.strip()
                if entry:
                    words.add(entry.lower())
    except FileNotFoundError:
        pass
    return words


def is_weak_password(password: str, weak_set: set[str] | None = None) -> bool:
    """Return True if password fully matches (case-insensitive, trimmed) a weak entry."""
    if weak_set is None:
        weak_set = load_weak_passwords()
    p = password.lower().strip()
    return p in weak_set
