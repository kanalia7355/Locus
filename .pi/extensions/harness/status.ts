// status.ts — ループの現在状態を人間向けに可視化する
//
// /harness-status コマンドと pi フッター表示のための整形を担う純粋モジュール。
// データ源は progress/ の frontmatter と state.json のみ (新しい記録は作らない)。

import * as fs from "node:fs";
import * as path from "node:path";
import { listMarkdownFiles, parseFrontmatter, readTextSmart } from "./poll";
import { activeCooldowns, type HarnessState } from "./state";

export interface TaskRow {
  phase: string;
  id: string;
  status: string;
  assignee: string;
  model: string;
  reviewer: string;
  attempts: string;
  updated: string;
}

/** progress/ 配下のタスクファイル (tasks/ の中だけ) を frontmatter から集める */
export function collectTasks(progressDir: string): TaskRow[] {
  const rows: TaskRow[] = [];
  let files: string[] = [];
  try {
    files = listMarkdownFiles(progressDir, progressDir);
  } catch {
    return rows;
  }
  for (const rel of files) {
    const norm = rel.replace(/\\/g, "/");
    if (!norm.includes("/tasks/")) continue;
    let fm: Record<string, string>;
    try {
      fm = parseFrontmatter(readTextSmart(path.join(progressDir, rel)));
    } catch {
      continue;
    }
    const parts = norm.split("/");
    rows.push({
      phase: fm.phase ?? parts[0] ?? "",
      id: fm.id ?? path.basename(rel, ".md"),
      status: fm.status ?? "(unknown)",
      assignee: fm.assignee ?? "",
      model: fm.model ?? "",
      reviewer: fm.reviewer ?? "",
      attempts: fm.attempts ?? "",
      updated: fm.updated ?? "",
    });
  }
  rows.sort((a, b) =>
    a.phase === b.phase ? a.id.localeCompare(b.id) : a.phase.localeCompare(b.phase),
  );
  return rows;
}

function hhmmss(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function hhmm(isoOrDate: string | Date): string {
  const d = typeof isoOrDate === "string" ? new Date(isoOrDate) : isoOrDate;
  if (Number.isNaN(d.getTime())) return "--:--";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function formatElapsed(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export interface StatusView {
  /** 実行中の作業 (例: "実装中 T-PH2-003 (agy/Gemini 3.8 Flash)")。無ければ null */
  activity: string | null;
  activitySince: Date | null;
  nextPollAt: Date | null;
}

/** /harness-status の表示テキストを組み立てる */
export function formatStatus(
  progressDir: string,
  state: HarnessState,
  view: StatusView,
  now: Date = new Date(),
): string {
  const lines: string[] = [];
  lines.push(`== harness status (${hhmmss(now)}) ==`);
  if (view.activity) {
    const elapsed = view.activitySince
      ? ` 経過 ${formatElapsed(now.getTime() - view.activitySince.getTime())}`
      : "";
    lines.push(`現在: ⏳ ${view.activity}${elapsed}`);
  } else {
    const next = view.nextPollAt
      ? ` · 次回ポーリング ${hhmm(view.nextPollAt)} (あと ${formatElapsed(Math.max(0, view.nextPollAt.getTime() - now.getTime()))})`
      : "";
    lines.push(`現在: 待機中${next}`);
  }
  if (state.lastPollAt) {
    lines.push(`最終ポーリング: ${hhmmss(new Date(state.lastPollAt))}`);
  }

  const tasks = collectTasks(progressDir);
  const byPhase = new Map<string, TaskRow[]>();
  for (const t of tasks) {
    const arr = byPhase.get(t.phase) ?? [];
    arr.push(t);
    byPhase.set(t.phase, arr);
  }
  for (const [phase, rows] of byPhase) {
    const remaining = rows.filter((r) => r.status !== "done").length;
    lines.push("");
    lines.push(`[${phase}] 残り ${remaining}/${rows.length}`);
    for (const r of rows) {
      const who = r.assignee || r.model ? `${r.assignee}/${r.model}` : "-";
      const att = r.attempts ? ` att ${r.attempts}/3` : "";
      const warn =
        r.status === "blocked"
          ? " ⚠"
          : r.status !== "done" && (r.attempts === "2" || r.attempts === "3")
            ? " ⚠"
            : "";
      lines.push(
        `  ${r.id.padEnd(12)} ${r.status.padEnd(7)} ${who}${att} 更新 ${hhmm(r.updated)}${warn}`,
      );
    }
  }

  const attention = tasks.filter(
    (r) =>
      r.status === "blocked" ||
      (r.status !== "done" && (r.attempts === "2" || r.attempts === "3")),
  );
  if (attention.length > 0) {
    lines.push("");
    lines.push("⚠ 要対応:");
    for (const r of attention) {
      lines.push(
        `  ${r.id} (${r.phase}): status=${r.status} attempts=${r.attempts || "?"}/3`,
      );
    }
  }

  const cds = activeCooldowns(state, now);
  if (cds.length > 0) {
    lines.push("");
    lines.push("cooldown:");
    for (const c of cds) {
      lines.push(`  ${c.scope}:${c.id} 〜 ${hhmm(c.until)} (${c.reason})`);
    }
  }

  if (state.cycleLog.length > 0) {
    lines.push("");
    lines.push("直近サイクル:");
    for (const e of state.cycleLog.slice(0, 5)) {
      lines.push(`  ${hhmmss(new Date(e.at))} ${e.note.split("\n")[0]}`);
    }
  }
  return lines.join("\n");
}
