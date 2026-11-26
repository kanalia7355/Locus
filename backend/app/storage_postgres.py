"""PostgreSQL storage engine, SQL dialect translation, and DSN validation (T-PH7-212)."""

from __future__ import annotations

import ipaddress
import os
import re
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.storage import StorageError, StorageIntegrityError

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)

_PRIVATE_HOSTNAME_SUFFIXES = (".internal", ".local", ".lan", ".corp", ".intranet")

_SERIALIZATION_FAILURE_SQLSTATE = "40001"

_PRIMARY_KEY_CONFLICT_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": ("id",),
    "sessions": ("token_hash",),
    "recovery_codes": ("user_id",),
    "projects": ("id",),
    "project_owners": ("project_id",),
    "memberships": ("user_id", "project_id"),
    "roles": ("id",),
    "membership_roles": ("user_id", "project_id", "role"),
    "delegation_families": ("id",),
    "delegation_grants": ("id",),
    "delegation_events": ("id",),
    "conversations": ("id",),
    "documents": ("id",),
    "chunks": ("id",),
    "storage_sources": ("id",),
    "source_objects": ("source_id", "object_id"),
    "document_source_bindings": ("document_id", "source_id", "object_id"),
    "document_origins": ("document_id",),
    "messages": ("id",),
    "generated_answers": ("message_id",),
    "chat_jobs": ("id",),
    "audit": ("id",),
    "audit_chain": ("audit_id",),
    "audit_chain_head": ("id",),
    "login_events": ("id",),
    "login_throttle": ("user_id",),
    "runner_instances": ("id",),
    "workspace_policies": ("id", "version"),
    "workspaces": ("id",),
    "agent_adapters": ("id",),
    "provider_contract_verifications": ("id",),
    "adapter_capabilities": ("id",),
    "workspace_adapter_bindings": (
        "workspace_id",
        "runner_instance_id",
        "adapter_id",
        "policy_id",
        "policy_version",
    ),
    "adapter_health": ("runner_instance_id", "adapter_id"),
    "adapter_credentials": ("runner_instance_id", "adapter_id"),
    "job_authorization_receipts": ("id",),
    "runner_artifacts": ("id",),
}

_AUDIT_SHA256_SQL_FUNCTIONS = """
CREATE OR REPLACE FUNCTION locus_audit_canon_at(v DOUBLE PRECISION)
RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    txt TEXT;
BEGIN
    txt := trim(to_char(v, 'FM99999999999999990.99999999999999999'));
    IF strpos(txt, '.') > 0 THEN
        txt := rtrim(rtrim(txt, '0'), '.');
    END IF;
    IF txt = '' OR txt = '-' THEN
        txt := '0';
    END IF;
    RETURN txt;
END;
$$;

CREATE OR REPLACE FUNCTION audit_sha256(
    prev_hash TEXT,
    audit_id TEXT,
    at_val DOUBLE PRECISION,
    actor_id TEXT,
    operation TEXT,
    target_id TEXT,
    outcome TEXT
) RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    at_txt TEXT;
    f TEXT;
    parts TEXT[];
    payload BYTEA;
BEGIN
    at_txt := locus_audit_canon_at(at_val);
    parts := ARRAY[
        octet_length(prev_hash)::text || ':' || prev_hash,
        octet_length(audit_id)::text || ':' || audit_id,
        octet_length(at_txt)::text || ':' || at_txt,
        octet_length(actor_id)::text || ':' || actor_id,
        octet_length(operation)::text || ':' || operation,
        octet_length(target_id)::text || ':' || target_id,
        octet_length(outcome)::text || ':' || outcome
    ];
    payload := decode(
        array_to_string(
            ARRAY(SELECT encode(convert_to(elem, 'UTF8'), 'hex') FROM unnest(parts) AS elem),
            '00'
        ),
        'hex'
    );
    RETURN encode(sha256(payload), 'hex');
END;
$$;
""".strip()


def _is_private_or_loopback_host(host: str) -> bool:
    cleaned = host.strip()
    if not cleaned:
        return False
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    lower = cleaned.lower()
    if lower == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(cleaned)
    except ValueError:
        if "." not in lower:
            return True
        return lower.endswith(_PRIVATE_HOSTNAME_SUFFIXES)
    if addr.is_unspecified or addr.is_multicast:
        return False
    return any(addr in net for net in _PRIVATE_NETWORKS)


def validate_database_url(url: str) -> str:
    """Validate ``LOCUS_DATABASE_URL`` without ever echoing credentials in errors."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("LOCUS_DATABASE_URL must not be empty")
    raw = url.strip()
    if any(ord(ch) < 32 or ch.isspace() for ch in raw):
        raise ValueError("LOCUS_DATABASE_URL contains invalid control or whitespace characters")
    scheme_sep = raw.find("://")
    if scheme_sep <= 0:
        scheme_prefix = raw.partition(":")[0].lower()
        if scheme_prefix in {"sqlite", "sqlite3"}:
            raise ValueError(
                "LOCUS_DATABASE_URL scheme 'sqlite' is not supported; use postgresql://"
            )
        raise ValueError("LOCUS_DATABASE_URL must be a postgresql:// or postgres:// URL")

    try:
        parsed = urlparse(raw)
    except ValueError:
        raise ValueError("LOCUS_DATABASE_URL could not be parsed") from None

    scheme = parsed.scheme.lower()
    if scheme not in {"postgresql", "postgres"}:
        safe_scheme = re.sub(r"[^a-z0-9+.-]", "", scheme)[:32] or "unknown"
        raise ValueError(
            f"LOCUS_DATABASE_URL scheme '{safe_scheme}' is not supported; "
            "expected 'postgresql' or 'postgres'"
        )

    query = parse_qs(parsed.query, keep_blank_values=True)
    host = parsed.hostname
    query_hosts = query.get("host", [])

    if host is None and query_hosts:
        candidate_hosts = query_hosts
    elif host is not None:
        candidate_hosts = [host, *query_hosts]
    else:
        raise ValueError("LOCUS_DATABASE_URL must specify a database host")

    for candidate in candidate_hosts:
        for item in candidate.split(","):
            target = item.strip()
            if not target:
                raise ValueError("LOCUS_DATABASE_URL contains an empty host entry")
            if target.startswith("/"):
                # Unix domain socket path on the local host.
                continue
            if not _is_private_or_loopback_host(target):
                raise ValueError(
                    "LOCUS_DATABASE_URL host is outside loopback and private LAN ranges"
                )

    try:
        port = parsed.port
    except ValueError:
        raise ValueError("LOCUS_DATABASE_URL port is invalid") from None
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("LOCUS_DATABASE_URL port is out of range")

    dbname = parsed.path.lstrip("/")
    if not dbname and not query.get("dbname"):
        raise ValueError("LOCUS_DATABASE_URL must specify a database name")

    return raw


def redact_database_url(url: str) -> str:
    """Return a log-safe representation of *url* with any password removed."""
    if not isinstance(url, str) or not url.strip():
        return "<empty>"
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return "<invalid-database-url>"
    scheme = re.sub(r"[^a-z0-9+.-]", "", parsed.scheme.lower())[:32] or "unknown"
    host = parsed.hostname or "local-socket"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""
    dbname = parsed.path.lstrip("/") or "<unspecified>"
    return f"{scheme}://{host}{port}/{dbname}"


def _scan_sql_segments(sql: str) -> list[tuple[bool, str]]:
    """Split *sql* into ``(is_code, text)`` segments preserving literals/comments."""
    segments: list[tuple[bool, str]] = []
    n = len(sql)
    i = 0
    code_start = 0

    def flush_code(end: int) -> None:
        if end > code_start:
            segments.append((True, sql[code_start:end]))

    while i < n:
        ch = sql[i]
        if ch == "'":
            flush_code(i)
            lit_start = i
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            segments.append((False, sql[lit_start:i]))
            code_start = i
        elif ch == '"':
            flush_code(i)
            ident_start = i
            i += 1
            while i < n:
                if sql[i] == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            segments.append((False, sql[ident_start:i]))
            code_start = i
        elif ch == "-" and i + 1 < n and sql[i + 1] == "-":
            flush_code(i)
            cmt_start = i
            newline = sql.find("\n", i + 2)
            i = n if newline == -1 else newline + 1
            segments.append((False, sql[cmt_start:i]))
            code_start = i
        elif ch == "/" and i + 1 < n and sql[i + 1] == "*":
            flush_code(i)
            cmt_start = i
            end_cmt = sql.find("*/", i + 2)
            i = n if end_cmt == -1 else end_cmt + 2
            segments.append((False, sql[cmt_start:i]))
            code_start = i
        elif ch == "$":
            tag_match = re.match(r"\$[A-Za-z0-9_]*\$", sql[i:])
            if tag_match:
                tag = tag_match.group(0)
                end_tag = sql.find(tag, i + len(tag))
                if end_tag != -1:
                    flush_code(i)
                    lit_end = end_tag + len(tag)
                    segments.append((False, sql[i:lit_end]))
                    i = lit_end
                    code_start = i
                    continue
            i += 1
        else:
            i += 1

    flush_code(n)
    return segments


def translate_placeholders(sql: str) -> str:
    """Replace SQLite ``?`` placeholders with ``%s`` outside literals and comments."""
    out: list[str] = []
    for is_code, chunk in _scan_sql_segments(sql):
        if is_code:
            # Escape bare percent signs in code (none in normal SQL, defensive) and map ? -> %s.
            out.append(chunk.replace("?", "%s"))
        else:
            out.append(chunk)
    return "".join(out)


def translate_column_types(sql: str) -> str:
    """Translate SQLite column type names to PostgreSQL equivalents in DDL.

    ``INTEGER`` and ``TEXT`` stay ``INTEGER`` and ``TEXT``; ``REAL`` becomes
    ``DOUBLE PRECISION`` so Unix-epoch float timestamps round-trip unchanged.
    """
    out: list[str] = []
    for is_code, chunk in _scan_sql_segments(sql):
        if is_code:
            out.append(re.sub(r"\bREAL\b", "DOUBLE PRECISION", chunk, flags=re.IGNORECASE))
        else:
            out.append(chunk)
    return "".join(out)


def split_sql_statements(script: str) -> list[str]:
    """Split a SQL script on top-level semicolons, handling both BEGIN..END and CASE..END."""
    statements: list[str] = []
    current: list[str] = []
    block_depth = 0
    case_depth = 0

    for is_code, chunk in _scan_sql_segments(script):
        if not is_code:
            current.append(chunk)
            continue

        pos = 0
        for match in re.finditer(r"\bBEGIN\b|\bCASE\b|\bEND\b|;", chunk, flags=re.IGNORECASE):
            token = match.group(0)
            upper = token.upper()
            if upper == "CASE":
                case_depth += 1
                current.append(chunk[pos : match.end()])
                pos = match.end()
            elif upper == "BEGIN":
                after = chunk[match.end() :]
                tx_begin = re.match(
                    r"^\s*(?:;|TRANSACTION\b|IMMEDIATE\b|DEFERRED\b|EXCLUSIVE\b|ISOLATION\b)",
                    after,
                    flags=re.IGNORECASE,
                )
                if not tx_begin:
                    block_depth += 1
                current.append(chunk[pos : match.end()])
                pos = match.end()
            elif upper == "END":
                if case_depth > 0:
                    case_depth -= 1
                elif block_depth > 0:
                    block_depth -= 1
                current.append(chunk[pos : match.end()])
                pos = match.end()
            else:
                if block_depth == 0 and case_depth == 0:
                    current.append(chunk[pos : match.start()])
                    stmt = "".join(current).strip()
                    if stmt:
                        statements.append(stmt)
                    current = []
                    pos = match.end()
                else:
                    current.append(chunk[pos : match.end()])
                    pos = match.end()
        if pos < len(chunk):
            current.append(chunk[pos:])

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _rewrite_insert_or_ignore(stmt: str) -> str:
    match = re.match(
        r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\b(.*)$",
        stmt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return stmt
    indent, table, rest = match.groups()
    cleaned_rest = rest.rstrip().removesuffix(";").rstrip()
    return f"{indent}INSERT INTO {table}{cleaned_rest} ON CONFLICT DO NOTHING"


def _split_top_level_csv(text: str) -> list[str]:
    items: list[str] = []
    cur: list[str] = []
    depth = 0
    for is_code, chunk in _scan_sql_segments(text):
        if not is_code:
            cur.append(chunk)
            continue
        for ch in chunk:
            if ch == "(":
                depth += 1
                cur.append(ch)
            elif ch == ")":
                depth = max(0, depth - 1)
                cur.append(ch)
            elif ch == "," and depth == 0:
                items.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
    if cur:
        items.append("".join(cur).strip())
    return [item for item in items if item]


def _rewrite_insert_or_replace(stmt: str) -> str:
    match = re.match(
        r"^(\s*)INSERT\s+OR\s+REPLACE\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*"
        r"(?:\(([^)]+)\))?\s*(VALUES\s*\(.*|SELECT\s+.*)$",
        stmt.rstrip().removesuffix(";"),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return stmt
    indent, table, raw_cols, tail = match.groups()
    table_lower = table.lower()
    pk_cols = _PRIMARY_KEY_CONFLICT_COLUMNS.get(table_lower)
    if not raw_cols or not pk_cols:
        # Without explicit column list (e.g. SELECT * self-replace in policy tests),
        # plain INSERT preserves primary-key conflict / BEFORE INSERT trigger behaviour.
        col_part = f" ({raw_cols})" if raw_cols else ""
        return f"{indent}INSERT INTO {table}{col_part} {tail}"

    cols = [c.strip() for c in _split_top_level_csv(raw_cols)]
    non_pk = [c for c in cols if c.lower() not in {k.lower() for k in pk_cols}]
    conflict_target = ", ".join(pk_cols)
    if not non_pk:
        return (
            f"{indent}INSERT INTO {table} ({', '.join(cols)}) {tail} "
            f"ON CONFLICT ({conflict_target}) DO NOTHING"
        )
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk)
    return (
        f"{indent}INSERT INTO {table} ({', '.join(cols)}) {tail} "
        f"ON CONFLICT ({conflict_target}) DO UPDATE SET {updates}"
    )


def _rewrite_sqlite_functions_in_trigger_stmt(stmt: str) -> str:
    # SELECT RAISE(ABORT, 'msg') -> RAISE EXCEPTION 'msg'
    raise_match = re.match(
        r"^\s*SELECT\s+RAISE\s*\(\s*(?:ABORT|FAIL|ROLLBACK)\s*,\s*('(?:''|[^'])*')\s*\)\s*$",
        stmt,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if raise_match:
        msg_literal = raise_match.group(1)
        # Escape % inside PL/pgSQL RAISE format string.
        escaped_msg = msg_literal[1:-1].replace("%", "%%")
        return f"RAISE EXCEPTION '{escaped_msg}'"

    converted = re.sub(
        r"lower\s*\(\s*hex\s*\(\s*randomblob\s*\(\s*16\s*\)\s*\)\s*\)",
        "md5(random()::text || clock_timestamp()::text)",
        stmt,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        r"\(\s*julianday\s*\(\s*'now'\s*\)\s*-\s*2440587\.5\s*\)\s*\*\s*86400\.0",
        "EXTRACT(EPOCH FROM clock_timestamp())::double precision",
        converted,
        flags=re.IGNORECASE,
    )
    return converted


def translate_trigger(sql: str) -> str:
    """Translate a SQLite ``CREATE TRIGGER ... BEGIN ... END`` statement to PostgreSQL."""
    cleaned = sql.strip().removesuffix(";").strip()
    header_match = re.match(
        r"^CREATE\s+TRIGGER\s+(IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+"
        r"(BEFORE|AFTER)\s+"
        r"(INSERT|DELETE|UPDATE(?:\s+OF\s+[A-Za-z0-9_,\s]+)?)\s+"
        r"ON\s+([A-Za-z_][A-Za-z0-9_]*)"
        r"(?:\s+FOR\s+EACH\s+ROW)?"
        r"(?:\s+WHEN\s+(.+?))?"
        r"\s+BEGIN\s+(.*)\s+END$",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not header_match:
        raise ValueError(f"Unsupported trigger syntax: {sql[:80]}")

    _if_not_exists, name, timing, event, table, when_expr, body = header_match.groups()
    timing_upper = timing.upper()
    event_clean = " ".join(event.split())
    event_upper_kind = event_clean.split()[0].upper()
    fn_name = f"locus_trg_fn_{name.lower()}"

    inner_stmts = split_sql_statements(body)
    pg_stmts: list[str] = []
    for inner in inner_stmts:
        s = _rewrite_sqlite_functions_in_trigger_stmt(inner)
        s = _rewrite_insert_or_ignore(s)
        s = _rewrite_insert_or_replace(s)
        s = translate_placeholders(s)
        pg_stmts.append(f"    {s.rstrip().removesuffix(';')};")

    return_target = "OLD" if (timing_upper == "BEFORE" and event_upper_kind == "DELETE") else "NEW"
    if timing_upper == "AFTER":
        return_stmt = "    RETURN NULL;"
    else:
        return_stmt = f"    RETURN {return_target};"

    when_clause = ""
    if when_expr:
        normalized_when = when_expr.strip()
        if normalized_when.startswith("(") and normalized_when.endswith(")"):
            when_clause = f" WHEN {normalized_when}"
        else:
            when_clause = f" WHEN ({normalized_when})"

    fn_body = "\n".join([*pg_stmts, return_stmt])
    return (
        f"CREATE OR REPLACE FUNCTION {fn_name}() RETURNS TRIGGER LANGUAGE plpgsql AS $$\n"
        f"BEGIN\n"
        f"{fn_body}\n"
        f"END;\n"
        f"$$;\n"
        f"DROP TRIGGER IF EXISTS {name} ON {table};\n"
        f"CREATE TRIGGER {name} {timing_upper} {event_clean} ON {table} "
        f"FOR EACH ROW{when_clause} EXECUTE FUNCTION {fn_name}();"
    )


def translate_sql(sql: str) -> str:
    """Translate a single SQLite statement used by ``Service`` into PostgreSQL dialect."""
    stripped = sql.strip()
    if not stripped:
        return ""

    # PRAGMA foreign_keys = ON/OFF -> PostgreSQL enforces FK constraints natively.
    if re.match(r"^PRAGMA\s+foreign_keys\s*=\s*(?:ON|OFF|1|0)\s*;?$", stripped, re.IGNORECASE):
        return "SELECT 1"

    # PRAGMA table_info(table) / PRAGMA table_xinfo(table)
    pragma_info = re.match(
        r"^PRAGMA\s+table_x?info\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;?$",
        stripped,
        flags=re.IGNORECASE,
    )
    if pragma_info:
        table_name = pragma_info.group(1).lower()
        return (
            "SELECT ordinal_position - 1 AS cid, column_name AS name, data_type AS type, "  # noqa: S608
            "CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull, "
            "column_default AS dflt_value, 0 AS pk "
            "FROM information_schema.columns "
            f"WHERE table_schema = current_schema() AND table_name = '{table_name}' "
            "ORDER BY ordinal_position"
        )

    # BEGIN IMMEDIATE -> BEGIN ISOLATION LEVEL SERIALIZABLE
    if re.match(r"^BEGIN\s+IMMEDIATE(?:\s+TRANSACTION)?\s*;?$", stripped, flags=re.IGNORECASE):
        return "BEGIN ISOLATION LEVEL SERIALIZABLE"

    # CREATE TRIGGER ... BEGIN ... END
    if re.match(r"^CREATE\s+TRIGGER\b", stripped, flags=re.IGNORECASE):
        return translate_trigger(stripped)

    # CREATE TABLE / ALTER TABLE -> column types
    if re.match(r"^(?:CREATE\s+TABLE|ALTER\s+TABLE)\b", stripped, flags=re.IGNORECASE):
        return translate_placeholders(translate_column_types(stripped.removesuffix(";").strip()))

    # DML / SELECT
    stmt = stripped.removesuffix(";").strip()
    stmt = _rewrite_insert_or_ignore(stmt)
    stmt = _rewrite_insert_or_replace(stmt)

    # SQLite implicit rowid tie-breaker in conversations preview query -> ctid in PostgreSQL
    out_segments: list[str] = []
    for is_code, chunk in _scan_sql_segments(stmt):
        if is_code:
            chunk = re.sub(r"\bm\.rowid\b", "m.ctid", chunk)
        out_segments.append(chunk)
    stmt = "".join(out_segments)

    return translate_placeholders(stmt)


def translate_schema_script(script: str) -> list[str]:
    """Translate a multi-statement SQLite DDL/DML script into ordered PostgreSQL statements."""
    statements = split_sql_statements(script)
    translated: list[str] = []
    uses_audit_sha256 = any(
        re.search(r"\baudit_sha256\s*\(", stmt, flags=re.IGNORECASE) for stmt in statements
    )
    if uses_audit_sha256:
        for fn_stmt in split_sql_statements(_AUDIT_SHA256_SQL_FUNCTIONS):
            translated.append(fn_stmt)

    seen_triggers: set[tuple[str, str]] = set()
    for stmt in statements:
        trg_match = re.match(
            r"^CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+"
            r"(?:BEFORE|AFTER)\s+(?:INSERT|DELETE|UPDATE(?:\s+OF\s+[A-Za-z0-9_,\s]+)?)\s+"
            r"ON\s+([A-Za-z_][A-Za-z0-9_]*)",
            stmt.strip(),
            flags=re.IGNORECASE,
        )
        if trg_match:
            key = (trg_match.group(1).lower(), trg_match.group(2).lower())
            if key in seen_triggers:
                # SQLite's CREATE TRIGGER IF NOT EXISTS ignores subsequent duplicate definitions.
                continue
            seen_triggers.add(key)

        pg_sql = translate_sql(stmt)
        if not pg_sql:
            continue
        for sub in split_sql_statements(pg_sql):
            if sub:
                translated.append(sub)
    return translated


class MappingRow(Mapping[str, Any]):
    """Hybrid mapping + positional row matching ``sqlite3.Row`` access patterns."""

    __slots__ = ("_columns", "_values", "_index")

    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._index = {col: idx for idx, col in enumerate(self._columns)}

    def __getitem__(self, key: str | int | slice) -> Any:
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self) -> Any:
        return self._columns


def normalize_postgres_error(exc: BaseException) -> StorageError:
    """Normalize a driver exception (including ``serialization_failure``) into ``StorageError``."""
    if isinstance(exc, StorageError):
        return exc

    sqlstate = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    cls_mro_names = {c.__name__ for c in type(exc).__mro__}

    if sqlstate == _SERIALIZATION_FAILURE_SQLSTATE or "SerializationFailure" in cls_mro_names:
        return StorageError(f"serialization_failure: {exc}")

    if "IntegrityError" in cls_mro_names or (
        isinstance(sqlstate, str) and sqlstate.startswith("23")
    ):
        return StorageIntegrityError(str(exc))

    return StorageError(str(exc))


class _PostgresCursor:
    """Cursor wrapper producing ``MappingRow`` results and normalized ``StorageError``s."""

    def __init__(self, raw_cursor: Any) -> None:
        self._cursor = raw_cursor
        desc = getattr(raw_cursor, "description", None)
        self._columns: tuple[str, ...] = (
            tuple(col.name if hasattr(col, "name") else col[0] for col in desc) if desc else ()
        )

    def _wrap_row(self, row: Any) -> Any:
        if row is None or isinstance(row, MappingRow):
            return row
        if isinstance(row, Mapping):
            cols = tuple(row.keys())
            return MappingRow(cols, tuple(row[c] for c in cols))
        return MappingRow(self._columns, row)

    def fetchone(self) -> Any:
        try:
            return self._wrap_row(self._cursor.fetchone())
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    def fetchall(self) -> list[Any]:
        try:
            return [self._wrap_row(r) for r in self._cursor.fetchall()]
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    def fetchmany(self, size: int | None = None) -> list[Any]:
        try:
            rows = self._cursor.fetchmany() if size is None else self._cursor.fetchmany(size)
            return [self._wrap_row(r) for r in rows]
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    @property
    def rowcount(self) -> int:
        return int(getattr(self._cursor, "rowcount", -1))

    @property
    def lastrowid(self) -> int | None:
        return None

    @property
    def description(self) -> Any:
        return getattr(self._cursor, "description", None)

    def __iter__(self) -> Iterator[Any]:
        yield from self.fetchall()


class _PostgresConnection:
    """``StorageConnection`` adapter translating SQLite SQL on the fly for PostgreSQL."""

    def __init__(self, raw_conn: Any) -> None:
        self._conn = raw_conn
        self.row_factory: Any = MappingRow
        self._in_tx = False

    @property
    def in_transaction(self) -> bool:
        info = getattr(self._conn, "info", None)
        status = getattr(info, "transaction_status", None)
        if status is not None:
            # psycopg pq.TransactionStatus: IDLE == 0
            return int(status) != 0
        return self._in_tx

    def execute(self, sql: str, params: Any = ()) -> _PostgresCursor:
        translated = translate_sql(sql)
        upper = translated.strip().upper()
        try:
            cur = self._conn.cursor()
            if params:
                cur.execute(translated, tuple(params))
            else:
                cur.execute(translated)
            if upper.startswith("BEGIN"):
                self._in_tx = True
            elif upper.startswith(("COMMIT", "ROLLBACK")):
                self._in_tx = False
            return _PostgresCursor(cur)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    def executemany(self, sql: str, seq_of_params: Any) -> _PostgresCursor:
        translated = translate_sql(sql)
        try:
            cur = self._conn.cursor()
            cur.executemany(translated, [tuple(p) for p in seq_of_params])
            return _PostgresCursor(cur)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    def executescript(self, sql: str) -> _PostgresCursor:
        last_cur: Any = None
        try:
            for stmt in translate_schema_script(sql):
                cur = self._conn.cursor()
                cur.execute(stmt)
                last_cur = cur
            if last_cur is None:
                last_cur = self._conn.cursor()
                last_cur.execute("SELECT 1")
            return _PostgresCursor(last_cur)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    def commit(self) -> None:
        try:
            self._conn.commit()
            self._in_tx = False
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    def rollback(self) -> None:
        try:
            self._conn.rollback()
            self._in_tx = False
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc

    def close(self) -> None:
        try:
            self._conn.close()
            self._in_tx = False
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise normalize_postgres_error(exc) from exc


class PostgresEngine:
    """``StorageEngine`` backed by PostgreSQL with lazy ``psycopg`` import in ``connect()``."""

    backend_name = "postgresql"

    def __init__(self, dsn: str, *, connect_immediately: bool = False) -> None:
        self._dsn = validate_database_url(dsn)
        self._redacted_dsn = redact_database_url(self._dsn)
        self._lock = threading.RLock()
        self._conn: _PostgresConnection | None = None
        if connect_immediately:
            self.connect()

    @property
    def redacted_dsn(self) -> str:
        return self._redacted_dsn

    def connect(self) -> _PostgresConnection:
        """Lazily import ``psycopg`` and open the autocommit base connection."""
        with self._lock:
            if self._conn is not None:
                return self._conn
            try:
                import psycopg  # type: ignore[import-not-found]
            except ImportError as exc:
                raise StorageError(
                    "PostgreSQL driver 'psycopg' is not installed in this environment"
                ) from exc
            try:
                raw = psycopg.connect(self._dsn, autocommit=True)
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                # Never include raw DSN (which may carry a password) in error details.
                raise StorageError(
                    f"Failed to connect to PostgreSQL ({self._redacted_dsn})"
                ) from None
            self._conn = _PostgresConnection(raw)
            return self._conn

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    @property
    def conn(self) -> _PostgresConnection:
        return self.connect()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Begin a ``SERIALIZABLE`` transaction; never auto-retry ``serialization_failure``."""
        with self._lock:
            conn = self.connect()
            conn.execute("BEGIN ISOLATION LEVEL SERIALIZABLE")
            try:
                yield
            except BaseException:
                if conn.in_transaction:
                    conn.rollback()
                raise
            else:
                if conn.in_transaction:
                    conn.commit()

    @contextmanager
    def connection(self) -> Iterator[_PostgresConnection]:
        yield self.connect()

    def apply_schema(self, script: str) -> None:
        with self._lock:
            conn = self.connect()
            conn.executescript(script)

    def ensure_column(self, table: str, column: str, definition: str) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", column
        ):
            raise ValueError("Invalid table or column identifier")
        with self._lock:
            if column not in self.columns(table):
                pg_def = translate_column_types(definition)
                self.connect().execute(f"ALTER TABLE {table} ADD COLUMN {column} {pg_def}")

    def columns(self, table: str) -> set[str]:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Invalid table identifier")
        with self._lock:
            rows = (
                self.connect()
                .execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = ?",
                    (table.lower(),),
                )
                .fetchall()
            )
        return {str(row["column_name"]) for row in rows}

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


def configured_database_url(environ: Mapping[str, str] | None = None) -> str | None:
    """Return validated ``LOCUS_DATABASE_URL`` if present in *environ*, else ``None``."""
    env = os.environ if environ is None else environ
    if "LOCUS_DATABASE_URL" not in env:
        return None
    raw = env["LOCUS_DATABASE_URL"]
    return validate_database_url(raw)
