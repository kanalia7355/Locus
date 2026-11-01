"""Private supervisor spool: durable nonce reservation and no uncertain replay.

The owner must supply an existing ACL-verified private namespace. This component
does not create accounts, confer trust on callers or expose an IPC endpoint.
All payloads are BLOBs: no packet-selected disk paths or external file opens.
"""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loop_engine.audit_packet import (
    CHUNK_LIMIT,
    FINDINGS_LIMIT,
    PACKET_LIMIT,
    binding,
    canonical,
    decode,
    digest,
    hash_value,
    validate_packet,
)
from loop_engine.schemas import validate
from loop_engine.security import SafetyError, reject_secrets, reparse

# Reserve ample room within32MiB for rollback pages and recovery overhead.
# Retained findings/tombstones/journal share this hard database page limit.
DATABASE_LIMIT = 12 * 1024 * 1024


class AuditSpool:
    def __init__(self, directory: Path) -> None:
        directory = directory.absolute()
        if not directory.is_dir() or any(reparse(p) for p in (directory, *directory.parents)):
            raise SafetyError("Private non-reparse audit namespace required")
        self.path = directory / "audit-spool-v1.sqlite3"
        if reparse(self.path):
            raise SafetyError("Reparse audit database rejected")
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS packets (
                nonce TEXT PRIMARY KEY, binding BLOB NOT NULL, packet_hash TEXT NOT NULL,
                size INTEGER NOT NULL, state TEXT NOT NULL, next_chunk INTEGER NOT NULL,
                payload BLOB NOT NULL, findings BLOB, findings_hash TEXT,
                created REAL NOT NULL, settled REAL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS transitions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, nonce TEXT NOT NULL,
                binding_hash TEXT NOT NULL, event TEXT NOT NULL, ordinal INTEGER,
                result_hash TEXT, created REAL NOT NULL)""")
            for operation in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS transitions_no_{operation.lower()} "
                    f"BEFORE {operation} ON transitions BEGIN "
                    "SELECT RAISE(ABORT, 'immutable audit transition'); END"
                )

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=2, isolation_level="IMMEDIATE")
        try:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA secure_delete=ON")
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            maximum = DATABASE_LIMIT // page_size
            if db.execute(f"PRAGMA max_page_count={maximum}").fetchone()[0] > maximum:
                raise SafetyError("Retained audit history filled the spool; preserve and hold")
            with db:
                yield db
        except sqlite3.DatabaseError:
            raise SafetyError("Audit storage unavailable/full; preserve and reconcile") from None
        finally:
            db.close()

    @staticmethod
    def _record(
        db: sqlite3.Connection,
        nonce: str,
        event: str,
        ordinal: int | None = None,
        result_hash: str | None = None,
    ) -> None:
        saved = db.execute("SELECT binding FROM packets WHERE nonce=?", (nonce,)).fetchone()
        if saved is None or event not in {
            "reserve",
            "chunk",
            "held",
            "running",
            "finished",
            "settled",
        }:
            raise SafetyError("Audit transition identity unavailable")
        db.execute(
            "INSERT INTO transitions(nonce,binding_hash,event,ordinal,result_hash,created) "
            "VALUES (?,?,?,?,?,?)",
            (nonce, digest(saved[0]), event, ordinal, result_hash, time.time()),
        )

    def reserve(self, expected: dict[str, Any], packet_hash: str, size: int) -> None:
        expected = binding(expected)
        hash_value(packet_hash)
        if type(size) is not int or not 0 < size <= PACKET_LIMIT:
            raise SafetyError("Audit packet size exceeded")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM packets WHERE nonce=?", (expected["nonce"],)).fetchone():
                raise SafetyError("Consumed audit nonce; reconciliation required")
            pending, occupied = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(size),0) FROM packets WHERE state!='settled'"
            ).fetchone()
            if pending >= 8 or occupied + size > 32 * 1024 * 1024:
                raise SafetyError("Audit spool full; unresolved packets retained")
            db.execute(
                "INSERT INTO packets VALUES (?,?,?,?,?,0,?,NULL,NULL,?,NULL)",
                (
                    expected["nonce"],
                    canonical(expected),
                    packet_hash,
                    size,
                    "receiving",
                    b"",
                    time.time(),
                ),
            )
            self._record(db, expected["nonce"], "reserve")

    def append(self, nonce: str, index: int, chunk: bytes) -> None:
        hash_value(nonce)
        error = False
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state,next_chunk,size,payload FROM packets WHERE nonce=?", (nonce,)
            ).fetchone()
            if row is None:
                raise SafetyError("Unreserved audit nonce")
            state, next_chunk, size, payload = row
            if state != "receiving":
                raise SafetyError("Audit transfer requires reconciliation")
            remaining = size - len(payload)
            if (
                type(index) is not int
                or index != next_chunk
                or index >= 64
                or not isinstance(chunk, bytes)
                or len(chunk) != min(CHUNK_LIMIT, remaining)
                or not chunk
            ):
                db.execute("UPDATE packets SET state='held' WHERE nonce=?", (nonce,))
                self._record(db, nonce, "held")
                error = True
            else:
                db.execute(
                    "UPDATE packets SET payload=?,next_chunk=next_chunk+1 WHERE nonce=?",
                    (payload + chunk, nonce),
                )
                self._record(db, nonce, "chunk", index)
        if error:
            raise SafetyError("Audit chunk rejected; nonce held")

    def claim(self, expected: dict[str, Any]) -> bytes:
        """Reserve execution BEFORE returning immutable validated input.

        Crash/cancellation/model failure leaves running/held, never re-executed.
        """
        expected = binding(expected)
        failure = False
        payload: bytes = b""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT binding,packet_hash,size,state,payload FROM packets WHERE nonce=?",
                (expected["nonce"],),
            ).fetchone()
            if row is None or row[3] != "receiving":
                raise SafetyError("Audit execution already reserved or unavailable")
            saved, packet_hash, size, _, payload = row
            try:
                if (
                    saved != canonical(expected)
                    or len(payload) != size
                    or digest(payload) != packet_hash
                ):
                    raise SafetyError("Audit transfer incomplete or changed")
                validate_packet(payload, expected)
            except (ValueError, TypeError, UnicodeError, RecursionError):
                failure = True
            db.execute(
                "UPDATE packets SET state=? WHERE nonce=?",
                ("held" if failure else "running", expected["nonce"]),
            )
            self._record(db, expected["nonce"], "held" if failure else "running")
        if failure:
            raise SafetyError("Audit packet rejected; nonce held")
        return payload

    def finish(self, expected: dict[str, Any], findings: dict[str, Any]) -> str:
        expected = binding(expected)
        raw = canonical(findings)
        decode(raw, FINDINGS_LIMIT)
        try:
            validate("review", findings)
        except ValueError:
            raise SafetyError("Audit findings schema rejected") from None
        reject_secrets(findings)
        if findings["task_id"] != expected["task_id"]:
            raise SafetyError("Audit findings task mismatch")
        result_hash = digest(raw)
        with self._db() as db:
            changed = db.execute(
                "UPDATE packets SET state='finished',findings=?,findings_hash=? "
                "WHERE nonce=? AND binding=? AND state='running'",
                (raw, result_hash, expected["nonce"], canonical(expected)),
            ).rowcount
            if changed != 1:
                raise SafetyError("Audit findings cannot overwrite an existing outcome")
            self._record(db, expected["nonce"], "finished", result_hash=result_hash)
        return result_hash

    def result(self, expected: dict[str, Any]) -> dict[str, Any]:
        expected = binding(expected)
        with self._db() as db:
            row = db.execute(
                "SELECT findings,findings_hash FROM packets WHERE nonce=? AND binding=? "
                "AND state IN ('finished','settled')",
                (expected["nonce"], canonical(expected)),
            ).fetchone()
        if row is None or digest(row[0]) != row[1]:
            raise SafetyError("Bound audit findings unavailable")
        return decode(row[0], FINDINGS_LIMIT)

    def acknowledge(self, expected: dict[str, Any], findings_hash: str) -> None:
        """Exact Review-side ACK; remove only our settled source BLOB, keep tombstone.

        Authentication and freshness revalidation belong to the calling supervisor.
        """
        expected = binding(expected)
        hash_value(findings_hash)
        with self._db() as db:
            changed = db.execute(
                "UPDATE packets SET state='settled',payload=?,settled=? WHERE nonce=? "
                "AND binding=? AND findings_hash=? AND state='finished'",
                (b"", time.time(), expected["nonce"], canonical(expected), findings_hash),
            ).rowcount
            if changed != 1:
                raise SafetyError("Audit acknowledgement mismatch or replay")
            self._record(db, expected["nonce"], "settled", result_hash=findings_hash)
