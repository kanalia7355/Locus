"""Measure the prototype's synthetic capacity: accounts, ingestion, dialogues.

Synthetic data and a stub model only; never touches real material or a model
daemon. The numbers it prints describe this machine and these synthetic inputs,
so they are measurements, not a promised capacity.

Owner-provided target (2026-11-15): a lab or team deployment with about ten
people asking questions at the same time and 30-40 provisioned accounts that
grows over time.
"""

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.scanner import CLEAN, ScanResult  # noqa: E402 — the backend package is resolved above
from app.service import (  # noqa: E402
    CHAT_QUEUE_LIMIT,
    CHAT_USER_QUEUE_LIMIT,
    CHAT_WAIT_SECONDS,
    ModelBusy,
    Principal,
    Service,
)
from fastapi import HTTPException  # noqa: E402


class CleanScanner:
    """Stands in for an approved scanner so ingestion is measured, not quarantined."""

    def scan(self, content: str) -> ScanResult:
        if not isinstance(content, str) or not content:
            raise ValueError("The measurement harness only scans synthetic text")
        return CLEAN


TEMPORARY = "Temporary-password-01!"
ROTATED = "Changed-password-long-01!"
# Representative synthetic material: notes, a tabular export and a source file.
# The ingestion path accepts UTF-8 txt/md/csv only, so a program file is carried
# as text; binary and PDF formats stay out of scope until their parser sandbox
# is approved.
SHAPES = (
    ("観察メモ.md", "# 合成観察メモ\n\n成膜条件Aの合成記録です。\n", 40),
    ("測定結果.csv", "試料,温度,時間\nA,180,30\nB,200,20\n", 400),
    ("解析スクリプト.txt", "def analyse(rows):\n    return [row for row in rows]\n", 120),
)


def account_scale(service: Service, accounts: int) -> dict[str, Any]:
    """Provision and activate accounts, measuring each stage separately."""
    started = time.monotonic()
    names = [f"member-{index:03d}" for index in range(accounts)]
    for name in names:
        service.provision(name, TEMPORARY)
        service.assign(name, "measured-project", "researcher")
    provisioned = time.monotonic() - started
    logins = []
    for index, name in enumerate(names):
        at = time.monotonic()
        token, _ = service.login(name, TEMPORARY, f"10.0.{index // 250}.{index % 250}")
        principal = service.authenticate(token, allow_rotation=True)
        service.rotate(principal, TEMPORARY, ROTATED, session_token=token)
        logins.append(time.monotonic() - at)
    return {
        "accounts": accounts,
        "provision_and_assign_seconds": round(provisioned, 2),
        "first_login_and_rotation_seconds_median": round(median(logins), 3),
        "first_login_and_rotation_seconds_max": round(max(logins), 3),
        # The web provisioning endpoint charges a 10-per-minute limit per
        # administrator, so reaching the target account count through the screen
        # takes at least this long however fast the machine is.
        "web_provisioning_minimum_minutes": round(accounts / 10, 1),
    }


def sessions(service: Service, count: int) -> list[tuple[Principal, str]]:
    actors = []
    for index in range(count):
        name = f"member-{index:03d}"
        token, _ = service.login(name, ROTATED, f"10.1.{index // 250}.{index % 250}")
        actors.append((service.authenticate(token), token))
    return actors


def ingestion(service: Service, actors: list[tuple[Principal, str]], documents: int) -> dict:
    """Upload documents from several owners and drain the ingestion worker."""
    stop = threading.Event()
    drained: list[float] = []

    def worker() -> None:
        while not stop.is_set():
            if not service.process_next():
                time.sleep(0.01)
            else:
                drained.append(time.monotonic())

    thread = threading.Thread(target=worker, daemon=True)
    started = time.monotonic()
    thread.start()
    rejected = 0
    accepted = 0
    bytes_total = 0
    for index in range(documents):
        actor, _ = actors[index % len(actors)]
        name, unit, repeat = SHAPES[index % len(SHAPES)]
        content = unit * repeat
        bytes_total += len(content.encode("utf-8"))
        for _ in range(600):  # Bounded wait for a queue slot, never unbounded.
            try:
                service.upload(
                    actor, "measured-project", f"{index:03d}-{name}", content, "personal"
                )
                accepted += 1
                break
            except HTTPException as exc:
                if exc.status_code != 429:
                    raise
                rejected += 1
                time.sleep(0.05)
    while time.monotonic() - started < 120:
        with service.db() as db:
            left = db.execute(
                "SELECT COUNT(*) FROM documents WHERE status IN ('queued','scanning','indexing')"
            ).fetchone()[0]
        if not left:
            break
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5)
    elapsed = time.monotonic() - started
    with service.db() as db:
        ready = db.execute("SELECT COUNT(*) FROM documents WHERE status='ready'").fetchone()[0]
        unfinished = db.execute(
            "SELECT COUNT(*) FROM documents WHERE status NOT IN ('ready','cancelled')"
        ).fetchone()[0]
    return {
        "documents_uploaded": accepted,
        "documents_ready": ready,
        "documents_unfinished": unfinished,
        "bytes_uploaded": bytes_total,
        "queue_full_retries": rejected,
        "total_seconds": round(elapsed, 2),
        "documents_per_second": round(accepted / elapsed, 2) if elapsed else None,
        "queue_limits": {"global_in_flight": 32, "per_owner_in_flight": 4},
    }


def dialogues(
    service: Service,
    actors: list[tuple[Principal, str]],
    concurrency: int,
    model_seconds: float,
) -> dict:
    """Ask one question per user at the same time against a stub model."""
    slot = threading.Lock()
    served: list[str] = []

    def generate(_text: str, _citations: list[dict]) -> tuple[str, str]:
        if not slot.acquire(blocking=False):
            raise ModelBusy()
        try:
            time.sleep(model_seconds)
            return "合成回答", "stub-model"
        finally:
            slot.release()

    asking = actors[:concurrency]
    conversations = [
        service.new_conversation(actor, "measured-project")["id"] for actor, _ in asking
    ]
    stop = threading.Event()

    def worker() -> None:
        while not stop.is_set():
            if not service.process_next_chat():
                time.sleep(0.01)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    results: list[dict[str, Any]] = []
    guard = threading.Lock()

    def ask(index: int) -> None:
        actor, token = asking[index]
        at = time.monotonic()
        outcome = "inline"
        job = None
        try:
            answer = service.send(
                actor,
                conversations[index],
                "成膜条件",
                "all",
                [],
                generate=generate,
                validate=None,
                token=token,
            )
            if answer is None:
                outcome = "dropped"
        except ModelBusy:
            outcome = "queued"
            job = service.enqueue_chat(
                actor,
                conversations[index],
                "成膜条件",
                "all",
                [],
                token=token,
                generate=generate,
                validate=None,
            )
        except HTTPException as exc:
            outcome = f"refused:{exc.status_code}"
        if job:
            while time.monotonic() - at < CHAT_WAIT_SECONDS + 30:
                # The screen polls every two seconds and the status endpoint
                # charges 120 requests a minute, so the harness polls no faster.
                time.sleep(2.0)
                try:
                    state = service.chat_job(actor, job)["status"]
                except HTTPException as exc:
                    if exc.status_code != 429:
                        outcome = f"status-refused:{exc.status_code}"
                        break
                    continue
                if state in {"done", "failed", "cancelled"}:
                    outcome = f"queued:{state}"
                    break
        with guard:
            if outcome.endswith("done") or outcome == "inline":
                served.append(actor.id)
            results.append({"user": actor.id, "outcome": outcome, "seconds": time.monotonic() - at})

    askers = [threading.Thread(target=ask, args=(index,)) for index in range(concurrency)]
    started = time.monotonic()
    for asker in askers:
        asker.start()
    for asker in askers:
        asker.join(timeout=CHAT_WAIT_SECONDS + 60)
    elapsed = time.monotonic() - started
    stop.set()
    thread.join(timeout=5)
    waits = sorted(round(item["seconds"], 2) for item in results)
    answered = [item for item in results if item["outcome"] in {"inline", "queued:done"}]
    repeats = sum(1 for before, after in zip(served, served[1:], strict=False) if before == after)
    return {
        "concurrent_askers": concurrency,
        "stub_model_seconds": model_seconds,
        "answered": len(answered),
        "outcomes": sorted({item["outcome"] for item in results}),
        "wait_seconds_median": median(waits) if waits else None,
        "wait_seconds_max": max(waits) if waits else None,
        "total_seconds": round(elapsed, 2),
        "consecutive_same_user_turns": repeats,
        "queue_limits": {
            "global_queued": CHAT_QUEUE_LIMIT,
            "per_user_queued": CHAT_USER_QUEUE_LIMIT,
            "wait_seconds": CHAT_WAIT_SECONDS,
        },
        # One model slot answers in series, so the last person in a line of N
        # waits about N times one answer. Beyond this the waiting line expires.
        "answer_seconds_budget_for_this_line": round(CHAT_WAIT_SECONDS / max(concurrency, 1), 1),
    }


def measure(accounts: int, documents: int, concurrency: int, model_seconds: float) -> dict:
    with TemporaryDirectory(prefix="locus-capacity-") as temp:
        service = Service(Path(temp) / "capacity.sqlite3", scanner=CleanScanner())
        try:
            service.create_project("measured-org", "measured-project", "測定用プロジェクト")
            report = {
                "accounts": account_scale(service, accounts),
            }
            actors = sessions(service, min(accounts, max(concurrency, 1)))
            report["ingestion"] = ingestion(service, actors, documents)
            report["dialogues"] = dialogues(service, actors, concurrency, model_seconds)
            return report
        finally:
            service.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=int, default=40)
    parser.add_argument("--documents", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--model-seconds", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if min(args.accounts, args.documents, args.concurrency) < 1 or args.model_seconds < 0:
        print("Measurement sizes must be positive")
        return 2
    report = measure(args.accounts, args.documents, args.concurrency, args.model_seconds)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
