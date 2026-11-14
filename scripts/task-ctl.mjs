#!/usr/bin/env node
// task-ctl.mjs — progress/ 台帳の frontmatter を一元管理する CLI。
//
// 設計原則:
// - 台帳ファイルの読み書きはこのツールだけが行う (単一書き手はランナー側だが、
//   形式の正規化はここに集約する)
// - パースできないファイルは黙って除外しない。scan では status:"corrupt" として
//   必ず結果に含める
// - 書き出しは常に UTF-8 (BOM なし) + LF + 正規キー順に正規化する
//
// 使い方:
//   node scripts/task-ctl.mjs scan <phaseDir>            # JSON 配列を stdout へ
//   node scripts/task-ctl.mjs get <taskFile>             # 1件を JSON で
//   node scripts/task-ctl.mjs normalize <phaseDir>       # 全ファイルを正規形に書き直す
//   node scripts/task-ctl.mjs heal <taskFile>            # git HEAD の frontmatter で修復
//   node scripts/task-ctl.mjs transition <taskFile> --to <status> [--bump-attempts] [--set k=v ...]
//   node scripts/task-ctl.mjs verdict <taskFile> --verdict <APPROVED|CHANGES_REQUESTED|BLOCKED>
//   node scripts/task-ctl.mjs set <taskFile> --set k=v [--set k=v ...]
//   node scripts/task-ctl.mjs set-report <taskFile> --section <REPORT|REVIEW|QA> --from <file>

import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

export const STATUS_VOCAB = ["todo", "doing", "review", "qa", "done", "blocked"];
export const VERDICT_VOCAB = ["NONE", "APPROVED", "CHANGES_REQUESTED", "BLOCKED"];
const KEY_ORDER = [
  "id", "phase", "status", "weight", "assignee", "model", "reviewer",
  "attempts", "review_round", "verdict", "verdict_for",
  "allowed_paths", "test_cmd", "updated",
];

// ---------- 読み取りと正規化 ----------

export function readSmart(file) {
  const buf = fs.readFileSync(file);
  let text;
  if (buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xfe) {
    text = buf.toString("utf16le");
  } else if (buf.length >= 2 && buf[0] === 0xfe && buf[1] === 0xff) {
    const usable = Math.max(0, buf.length - 2 - ((buf.length - 2) % 2));
    const swapped = Buffer.alloc(usable);
    for (let i = 2; i + 1 < buf.length; i += 2) {
      swapped[i - 2] = buf[i + 1];
      swapped[i - 1] = buf[i];
    }
    text = swapped.toString("utf16le");
  } else {
    text = buf.toString("utf-8");
  }
  return text.replace(/^﻿/, "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

// frontmatter を寛容にパースする。壊れている場合は { corrupt: true, error } を返す
export function parseTaskText(text) {
  const lines = text.split("\n");
  let start = -1;
  for (let i = 0; i < Math.min(lines.length, 5); i++) {
    if (/^---\s*$/.test(lines[i])) { start = i; break; }
  }
  if (start === -1) return { corrupt: true, error: "no_frontmatter_fence" };
  let end = -1;
  for (let i = start + 1; i < lines.length; i++) {
    if (/^---\s*$/.test(lines[i]) || /^\.\.\.\s*$/.test(lines[i])) { end = i; break; }
  }
  if (end === -1) return { corrupt: true, error: "frontmatter_not_closed" };

  const fields = {};
  const extraOrder = [];
  const warnings = [];
  for (const rawLine of lines.slice(start + 1, end)) {
    if (/^\s*$/.test(rawLine) || /^\s*#/.test(rawLine)) continue;
    const m = rawLine.match(/^\s*([A-Za-z0-9_-]+)\s*:\s*(.*)$/);
    if (!m) return { corrupt: true, error: `unparseable_line: ${rawLine.slice(0, 60)}` };
    const key = m[1].toLowerCase();
    let value = m[2].trim();
    const quoted = /^(['"`])(.*)\1$/.exec(value);
    if (quoted) value = quoted[2];
    else value = value.replace(/\s+#.*$/, "").trim();
    if (key in fields) warnings.push(`duplicate_key:${key}`);
    if (!KEY_ORDER.includes(key) && !extraOrder.includes(key)) extraOrder.push(key);
    fields[key] = value;
  }

  if (fields.status !== undefined) {
    const s = String(fields.status).toLowerCase();
    if (!STATUS_VOCAB.includes(s)) {
      return { corrupt: true, error: `invalid_status: ${fields.status}` };
    }
    fields.status = s;
  } else {
    return { corrupt: true, error: "missing_status" };
  }
  if (fields.verdict !== undefined) {
    const v = String(fields.verdict).toUpperCase();
    fields.verdict = VERDICT_VOCAB.includes(v) ? v : "NONE";
  }
  const body = lines.slice(end + 1).join("\n");
  return { fields, extraOrder, warnings, body };
}

function formatScalar(v) {
  const s = String(v);
  if (/(?:^\s|\s$|\s#|^['"`])/.test(s)) {
    return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  return s;
}

export function serializeTask(fields, extraOrder, body) {
  const out = ["---"];
  const written = new Set();
  for (const key of KEY_ORDER) {
    if (fields[key] !== undefined) { out.push(`${key}: ${formatScalar(fields[key])}`); written.add(key); }
  }
  for (const key of extraOrder ?? []) {
    if (fields[key] !== undefined && !written.has(key)) {
      out.push(`${key}: ${formatScalar(fields[key])}`);
      written.add(key);
    }
  }
  // set で新規追加されたキー (qa_verdict, unblocks 等) は extraOrder に無いため、
  // ここで拾わないと保存時に黙って落ちる
  for (const key of Object.keys(fields)) {
    if (fields[key] !== undefined && !written.has(key)) {
      out.push(`${key}: ${formatScalar(fields[key])}`);
      written.add(key);
    }
  }
  out.push("---");
  const bodyText = (body ?? "").replace(/^\n+/, "");
  return out.join("\n") + "\n\n" + bodyText.replace(/\s*$/, "") + "\n";
}

export function isoNow() {
  const d = new Date();
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const hh = String(Math.floor(Math.abs(off) / 60)).padStart(2, "0");
  const mm = String(Math.abs(off) % 60).padStart(2, "0");
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}${sign}${hh}:${mm}`;
}

export function loadTask(file) {
  const text = readSmart(file);
  const parsed = parseTaskText(text);
  if (parsed.corrupt) return { file, status: "corrupt", error: parsed.error };
  const f = parsed.fields;
  if (f.attempts !== undefined && f.attempts !== "" && !/^\d+$/.test(f.attempts.trim())) {
    return { file, status: "corrupt", error: `invalid_attempts: ${f.attempts}` };
  }
  if (f.review_round !== undefined && f.review_round !== "" && !/^\d+$/.test(f.review_round.trim())) {
    return { file, status: "corrupt", error: `invalid_review_round: ${f.review_round}` };
  }
  return {
    file,
    ...f,
    attempts: f.attempts !== undefined && f.attempts !== "" ? Number.parseInt(f.attempts, 10) : 0,
    review_round: f.review_round !== undefined && f.review_round !== "" ? Number.parseInt(f.review_round, 10) : 0,
    verdict: f.verdict ?? "NONE",
    verdict_for: f.verdict_for ?? "-",
    warnings: parsed.warnings,
    _parsed: parsed,
  };
}

export function saveTask(file, task) {
  const parsed = task._parsed;
  const fields = { ...parsed.fields };
  // KEY_ORDER 外のキー (qa_verdict, unblocks 等) も保存対象にする。
  // ここで KEY_ORDER だけを写すと、set で足したカスタムキーが黙って落ちる
  for (const key of Object.keys(task)) {
    if (key === "file" || key === "warnings" || key === "_parsed") continue;
    const v = task[key];
    if (v === undefined || v === null || typeof v === "object") continue;
    fields[key] = String(v);
  }
  fields.updated = isoNow();
  fs.writeFileSync(file, serializeTask(fields, parsed.extraOrder, parsed.body), "utf-8");
}

// ---------- コマンド ----------

function cmdScan(phaseDir) {
  const tasksDir = path.join(phaseDir, "tasks");
  const out = [];
  if (fs.existsSync(tasksDir)) {
    for (const name of fs.readdirSync(tasksDir).sort()) {
      if (!name.endsWith(".md")) continue;
      const file = path.join(tasksDir, name);
      const t = loadTask(file);
      if (t.status === "corrupt") {
        out.push({ file, id: name.replace(/\.md$/, ""), status: "corrupt", error: t.error });
      } else {
        const { _parsed, ...rest } = t;
        out.push(rest);
      }
    }
  }
  console.log(JSON.stringify(out, null, 1));
}

function cmdNormalize(phaseDir) {
  const tasksDir = path.join(phaseDir, "tasks");
  const changed = [];
  if (!fs.existsSync(tasksDir)) return;
  for (const name of fs.readdirSync(tasksDir).sort()) {
    if (!name.endsWith(".md")) continue;
    const file = path.join(tasksDir, name);
    const before = fs.readFileSync(file);
    const t = loadTask(file);
    if (t.status === "corrupt") {
      console.log(`corrupt (skipped): ${file} (${t.error})`);
      continue;
    }
    saveTask(file, t);
    const after = fs.readFileSync(file);
    if (!before.equals(after)) changed.push(file);
  }
  console.log(`normalized: ${changed.length} file(s) changed`);
  for (const f of changed) console.log(`  ${f}`);
}

function cmdHeal(file) {
  const dir = path.dirname(file);
  const top = execFileSync("git", ["-C", dir, "rev-parse", "--show-toplevel"], { encoding: "utf-8" }).trim();
  const rel = path.relative(top, file).split(path.sep).join("/");
  let headText;
  try {
    headText = execFileSync("git", ["-C", top, "show", `HEAD:${rel}`], { encoding: "utf-8" });
  } catch {
    console.error(`heal failed: no HEAD version for ${rel}`);
    process.exit(1);
  }
  const head = parseTaskText(headText.replace(/\r\n/g, "\n").replace(/\r/g, "\n"));
  if (head.corrupt) {
    console.error("heal failed: HEAD frontmatter is also corrupt");
    process.exit(1);
  }
  const current = readSmart(file);
  const bodyStart = current.search(/^#\s/m);
  const body = bodyStart >= 0 ? current.slice(bodyStart) : head.body;
  const fields = { ...head.fields };
  fs.writeFileSync(file, serializeTask(fields, head.extraOrder, body), "utf-8");
  console.log(`healed: ${file}`);
}

function parseSetArgs(args) {
  const sets = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--set" && args[i + 1]) {
      const eq = args[i + 1].indexOf("=");
      if (eq > 0) sets.push([args[i + 1].slice(0, eq).toLowerCase(), args[i + 1].slice(eq + 1)]);
      i++;
    }
  }
  return sets;
}

function cmdTransition(file, args) {
  const toIdx = args.indexOf("--to");
  const to = toIdx >= 0 ? args[toIdx + 1] : null;
  if (!to || !STATUS_VOCAB.includes(to)) {
    console.error(`transition: --to must be one of ${STATUS_VOCAB.join("|")}`);
    process.exit(1);
  }
  const bump = args.includes("--bump-attempts");
  const t = loadTask(file);
  if (t.status === "corrupt") {
    console.error(`transition: task is corrupt (${t.error})`);
    process.exit(1);
  }
  const prev = t.status;
  if (to === "doing") {
    if (bump) {
      t.attempts = (t.attempts || 0) + 1;
      t.review_round = 0;
    } else if (prev === "todo" && !(t.attempts > 0)) {
      t.attempts = 1;
    }
    t.verdict = "NONE";
    t.verdict_for = "-";
  } else if (to === "review") {
    t.review_round = (t.review_round || 0) + 1;
    t.verdict = "NONE";
    t.verdict_for = "-";
  }
  t.status = to;
  for (const [k, v] of parseSetArgs(args)) t[k] = v;
  saveTask(file, t);
  console.log(`transition: ${prev} -> ${to} (attempts=${t.attempts}, review_round=${t.review_round})`);
}

function cmdVerdict(file, args) {
  const idx = args.indexOf("--verdict");
  const v = idx >= 0 ? String(args[idx + 1]).toUpperCase() : null;
  if (!v || !VERDICT_VOCAB.includes(v) || v === "NONE") {
    console.error("verdict: --verdict must be APPROVED|CHANGES_REQUESTED|BLOCKED");
    process.exit(1);
  }
  const t = loadTask(file);
  if (t.status === "corrupt") {
    console.error(`verdict: task is corrupt (${t.error})`);
    process.exit(1);
  }
  t.verdict = v;
  t.verdict_for = `${t.attempts}.${t.review_round}`;
  saveTask(file, t);
  console.log(`verdict: ${v} for ${t.verdict_for}`);
}

function cmdSet(file, args) {
  const t = loadTask(file);
  if (t.status === "corrupt") {
    console.error(`set: task is corrupt (${t.error})`);
    process.exit(1);
  }
  for (const [k, v] of parseSetArgs(args)) t[k] = v;
  saveTask(file, t);
  console.log("set: ok");
}

function cmdSetReport(file, args) {
  const sIdx = args.indexOf("--section");
  const fIdx = args.indexOf("--from");
  const section = sIdx >= 0 ? String(args[sIdx + 1]).toUpperCase() : null;
  const from = fIdx >= 0 ? args[fIdx + 1] : null;
  if (!section || !from) {
    console.error("set-report: --section and --from are required");
    process.exit(1);
  }
  const t = loadTask(file);
  if (t.status === "corrupt") {
    console.error(`set-report: task is corrupt (${t.error})`);
    process.exit(1);
  }
  const content = readSmart(from).replace(/\s*$/, "");
  const body = t._parsed.body;
  const escaped = section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const headingRe = new RegExp(`^##\\s+${escaped}(?:\\s+\\([^)]*\\))?\\s*$`, "m");
  const m = headingRe.exec(body);
  if (m) {
    const afterStart = m.index + m[0].length;
    const rest = body.slice(afterStart);
    // 節の終端は「次の予約節見出し」まで。QA レポート等が本文中に書く
    // `## 照合結果` のような小見出しで節が切れると、旧レポートの断片が残り続けるため
    const nextHeading = rest.search(/^##\s+(TASK DEFINITION|REPORT|TEST|REVIEW|QA|QA Result|QA Return|Planner Note|目的|実装内容|受入条件|備考|autoloop run|🚨)\b/m);
    const tail = nextHeading >= 0 ? rest.slice(nextHeading) : "";
    t._parsed.body = body.slice(0, m.index) + m[0] + "\n\n" + content + "\n\n" + tail.replace(/^\n+/, "");
  } else {
    t._parsed.body = body.replace(/\s*$/, "") + `\n\n## ${section}\n\n${content}\n`;
  }
  saveTask(file, t);
  console.log(`set-report: ${section} updated`);
}

function main() {
  const [cmd, ...args] = process.argv.slice(2);
  switch (cmd) {
    case "scan": cmdScan(args[0]); break;
    case "get": {
      const t = loadTask(args[0]);
      const { _parsed, ...rest } = t;
      console.log(JSON.stringify(rest, null, 1));
      break;
    }
    case "normalize": cmdNormalize(args[0]); break;
    case "heal": cmdHeal(args[0]); break;
    case "transition": cmdTransition(args[0], args.slice(1)); break;
    case "verdict": cmdVerdict(args[0], args.slice(1)); break;
    case "set": cmdSet(args[0], args.slice(1)); break;
    case "set-report": cmdSetReport(args[0], args.slice(1)); break;
    default:
      console.error("usage: task-ctl <scan|get|normalize|heal|transition|verdict|set|set-report> ...");
      process.exit(1);
  }
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("task-ctl.mjs")) {
  main();
}
