#!/usr/bin/env node
// autoloop.mjs — 自律開発ループの薄型ランナー (直列・イベント駆動)。
//
// 原則:
// - 状態遷移の書き手はランナーだけ。ワーカーはコードとレポートだけを書く
// - 完了判定はプロセス終了 + git status で行い、Markdown 本文のパースで制御しない
// - 読めないタスクファイル (corrupt) は黙って飛ばさず、修復を試み、無理なら
//   PROGRESS.md にアラートを書いて停止する
//
// 使い方:
//   node scripts/autoloop.mjs <phase-slug> [--max-cycles 50] [--max-hours 6] [--once]
//     [--no-plan] [--plan-rounds 6] [--max-phases 3]
//     [--no-merge] [--ci-workflows "Prototype quality"]
//
// 駆動できるタスクが尽きたら、プランナー (Luna) が台帳を審査する:
// blocked の再評価・解除、残作業のタスク分解、フェーズ完了判定と次フェーズの起票。
// プランナーが編集できるのは progress/ 配下 (台帳) のみで、コードには触れない。
// フェーズ完了時は統合ゲートを通す: 現在のブランチの CI green を確認してから
// main へマージし、次フェーズの台帳を main 上で起票して loop/<次フェーズ> ブランチを切る。
// CI が green でなければマージせず、理由を台帳に残して停止する。
//
// 環境変数: CODEX_BIN / AGY_BIN / OPENCODE_BIN (テスト用に実行系を差し替え可能)、
//           AUTOLOOP_LUNA_MODEL (既定 gpt-6-luna)

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const SCRIPTS_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO = process.cwd();
const phaseSlug = process.argv[2];
if (!phaseSlug || phaseSlug.startsWith("--")) {
  console.error("usage: autoloop.mjs <phase-slug> [--max-cycles N] [--max-hours H] [--once]");
  process.exit(2);
}
const opt = (name, def) => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
};
const MAX_CYCLES = Number.parseInt(opt("max-cycles", "50"), 10);
const MAX_HOURS = Number.parseFloat(opt("max-hours", "6"));
const ONCE = process.argv.includes("--once");
const LUNA_MODEL = process.env.AUTOLOOP_LUNA_MODEL || "gpt-6-luna";
const PLAN_ENABLED = !process.argv.includes("--no-plan");
const MAX_PLAN_ROUNDS = Number.parseInt(opt("plan-rounds", "6"), 10);
const MAX_PHASES = Number.parseInt(opt("max-phases", "3"), 10);
const MERGE_ENABLED = !process.argv.includes("--no-merge");
const CI_WORKFLOWS = opt("ci-workflows", ""); // カンマ区切り。空 = そのブランチで走った全ワークフロー
const CI_POLL_MS = Number.parseInt(process.env.AUTOLOOP_CI_POLL_MS || "60000", 10);
const CI_TIMEOUT_MS = Number.parseInt(process.env.AUTOLOOP_CI_TIMEOUT_MS || String(20 * 60000), 10);

// フェーズはプランナーの次フェーズ起票で切り替わるため可変にする
let curPhase = phaseSlug;
let progressDir = path.join(REPO, "progress", curPhase);
let progressRel = `progress/${curPhase}`;
let PROGRESS_FILE = path.join(progressDir, "PROGRESS.md");
function setPhase(slug) {
  curPhase = slug;
  progressDir = path.join(REPO, "progress", slug);
  progressRel = `progress/${slug}`;
  PROGRESS_FILE = path.join(progressDir, "PROGRESS.md");
}
const harnessDir = path.join(REPO, ".pi", "harness");
const stateFile = path.join(harnessDir, "state.json");
const STOP_FILE = path.join(harnessDir, "STOP");
for (const d of ["tmp", "verdicts", "dispatch", "logs"]) {
  fs.mkdirSync(path.join(harnessDir, d), { recursive: true });
}

const startedAt = Date.now();
const runLog = [];
function note(msg) {
  const line = `[autoloop ${new Date().toISOString()}] ${msg}`;
  console.log(line);
  runLog.push(msg);
}

// ---------- 状態 (cooldown 等) ----------
function loadState() {
  try {
    const s = JSON.parse(fs.readFileSync(stateFile, "utf-8"));
    if (!s.autoloop) s.autoloop = {};
    if (!Array.isArray(s.autoloop.cooldowns)) s.autoloop.cooldowns = [];
    if (typeof s.autoloop.freeCursor !== "number") s.autoloop.freeCursor = 0;
    if (typeof s.autoloop.pushFailures !== "number") s.autoloop.pushFailures = 0;
    if (!s.autoloop.planner || typeof s.autoloop.planner !== "object") {
      s.autoloop.planner = { rounds: {}, phases: [], invalid: 0, noProgress: 0 };
    }
    if (!s.autoloop.planner.rounds || typeof s.autoloop.planner.rounds !== "object") s.autoloop.planner.rounds = {};
    if (!Array.isArray(s.autoloop.planner.phases)) s.autoloop.planner.phases = [];
    return s;
  } catch {
    return { autoloop: { cooldowns: [], freeCursor: 0, pushFailures: 0, planner: { rounds: {}, phases: [], invalid: 0, noProgress: 0 } } };
  }
}
const state = loadState();
function saveState() {
  fs.mkdirSync(harnessDir, { recursive: true });
  fs.writeFileSync(stateFile, JSON.stringify(state, null, 1), "utf-8");
}
function setCooldown(key, untilMs, reason) {
  state.autoloop.cooldowns = state.autoloop.cooldowns.filter((c) => c.key !== key);
  state.autoloop.cooldowns.push({ key, until: new Date(untilMs).toISOString(), reason });
  saveState();
  note(`cooldown: ${key} until ${new Date(untilMs).toISOString()} (${reason})`);
}
function coolingUntil(key) {
  const now = Date.now();
  const c = state.autoloop.cooldowns.find((x) => x.key === key && Date.parse(x.until) > now);
  return c ? Date.parse(c.until) : 0;
}

// ---------- 外部コマンド ----------
function sh(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, {
    cwd: REPO,
    encoding: "utf-8",
    timeout: opts.timeout ?? 120000,
    input: opts.input,
    shell: opts.shell ?? false,
    env: { ...process.env, CI: "true" },
  });
  return { code: r.status ?? -1, out: `${r.stdout ?? ""}${r.stderr ?? ""}`, error: r.error };
}
function taskCtl(args) {
  const r = sh(process.execPath, [path.join(SCRIPTS_DIR, "task-ctl.mjs"), ...args], { timeout: 60000 });
  return r;
}
function scanTasks() {
  const r = taskCtl(["scan", progressDir]);
  if (r.code !== 0) throw new Error(`task-ctl scan failed: ${r.out}`);
  return JSON.parse(r.out);
}
function git(args, opts = {}) {
  return sh("git", args, opts);
}
function gitStatusPaths() {
  const r = git(["-c", "core.quotePath=false", "status", "--porcelain", "-uall"]);
  if (r.code !== 0) return [];
  return r.out.split("\n").filter(Boolean).flatMap((line) => {
    const raw = line.slice(3);
    const parts = raw.includes(" -> ") ? raw.split(" -> ") : [raw];
    return parts.map((p) => p.replace(/^"|"$/g, "").split(path.sep).join("/"));
  });
}
function gitHead() {
  const r = git(["rev-parse", "HEAD"]);
  return r.code === 0 ? r.out.trim() : "";
}
function gitPush() {
  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"]).out.trim();
  const r = git(["push", "-u", "origin", branch], { timeout: 180000 });
  if (r.code === 0) {
    state.autoloop.pushFailures = 0;
    saveState();
    note(`pushed to origin/${branch}`);
    return true;
  }
  state.autoloop.pushFailures += 1;
  saveState();
  note(`push failed (${state.autoloop.pushFailures}/3): ${r.out.trim().slice(-200)}`);
  return false;
}

// ---------- パス分類 ----------
// loop_engine/ は pi 時代に「現行コントローラ保護」で禁止だったが、実態は廃止済みエンジンで、
// その CI チェック (Loop engine checks) がマージゲートを構成するため対象外にすると直せない。
// 触ってはいけないのは計画文書と旧ハーネス拡張だけに絞る
const FORBIDDEN = [".pi/extensions/", "docs/planning/", "docs/plans/", ".loop/"];
function allowedMatch(p, allowed) {
  return (allowed ?? []).some((a) => p === a || (a.endsWith("/") && p.startsWith(a)));
}
const parseAllowed = (t) => (t.allowed_paths ?? "").split(",").map((s) => s.trim()).filter(Boolean);
// 同一ツリーに複数タスクの未コミット変更が同居する前提 (MVP は worktree なし)。
// 他タスクの allowed_paths に属する変更は「所属が判明している」ので unmapped にしない
let ALL_ALLOWED = [];
function refreshAllAllowed(tasks) {
  ALL_ALLOWED = tasks.flatMap((t) => parseAllowed(t));
}
function classify(task, changedPaths) {
  const allowed = parseAllowed(task);
  const taskRel = `${progressRel}/tasks/${task.id}.md`;
  const buckets = { allowed: [], forbidden: [], unmapped: [], ledger: [] };
  for (const p of changedPaths) {
    if (FORBIDDEN.some((f) => p.startsWith(f))) buckets.forbidden.push(p);
    else if (p === taskRel || p === `${progressRel}/PROGRESS.md` || p.startsWith(`${progressRel}/`)) buckets.ledger.push(p);
    else if (allowedMatch(p, allowed)) buckets.allowed.push(p);
    else if (p.startsWith(".pi/harness/")) { /* infra: 無視 */ }
    else if (allowedMatch(p, ALL_ALLOWED)) { /* 他タスクの変更: このタスクでは触らない */ }
    else buckets.unmapped.push(p);
  }
  return buckets;
}

// ---------- モデル選択 (Free-First) ----------
const TIER_A = ["glm-5.3-flash-free", "deepseek-v4.1-flash-free", "mimo-v2.6-flash-free", "minimax-m3.1-flash-free", "big-pickle"];
const FREE_POOL = [...TIER_A, "nemotron-3.5-lightning-free"];
const oc = (slug) => ({ runner: "opencode", model: `opencode/${slug}`, family: "opencode", key: `model:opencode/${slug}` });
const agy = (display, effort = "Medium") => ({
  runner: "agy", model: display, effort, family: display.startsWith("Gemini") ? "gemini" : display.startsWith("Claude") ? "claude" : "gptoss",
  key: display.startsWith("Gemini") ? "pool:agy:gemini" : "pool:agy:claude-gpt",
});
function freePoolRotated(slugs) {
  const start = state.autoloop.freeCursor % slugs.length;
  const rotated = [...slugs.slice(start), ...slugs.slice(0, start)];
  state.autoloop.freeCursor = (start + 1) % slugs.length;
  saveState();
  return rotated.map(oc);
}
function familyOf(task) {
  const m = task.model ?? "";
  if (m.startsWith("opencode/") || m === "opencode") return "opencode";
  if (m.includes("Gemini")) return "gemini";
  if (m.includes("Claude")) return "claude";
  if (m.includes("GPT")) return "gptoss";
  return "";
}
function implementerCandidates(task) {
  const w = task.weight ?? "medium";
  if (w === "light") return [...freePoolRotated(FREE_POOL), agy("Gemini 3.8 Flash"), agy("GPT-OSS 120B")];
  if (w === "heavy") return [agy("Gemini 4 Argon", "High"), agy("Claude Opus 5.5", "High"), agy("Claude Sonnet 5.5", "High")];
  if ((task.attempts ?? 1) >= 2) return [agy("Gemini 4 Argon"), agy("Claude Sonnet 5.5"), ...freePoolRotated(TIER_A)];
  return [...freePoolRotated(TIER_A), agy("Gemini 4 Argon"), agy("Claude Sonnet 5.5")];
}
function reviewerCandidates(task) {
  const w = task.weight ?? "medium";
  const implFam = familyOf(task);
  let list;
  if (w === "light") list = [...freePoolRotated(FREE_POOL), agy("GPT-OSS 120B"), agy("Gemini 3.8 Flash")];
  else if (w === "heavy") list = [agy("Claude Opus 5.5", "High"), agy("Claude Sonnet 5.5", "High"), agy("Gemini 4 Argon", "High")];
  else list = [agy("Claude Sonnet 5.5"), agy("Gemini 3.8 Flash"), ...freePoolRotated(TIER_A)];
  const diff = list.filter((c) => c.family !== implFam);
  const same = list.filter((c) => c.family === implFam);
  return [...diff, ...same];
}
function available(candidates) {
  return candidates.filter((c) => coolingUntil(c.key) === 0);
}
function earliestCooling(candidates) {
  let min = Infinity;
  for (const c of candidates) {
    const u = coolingUntil(c.key);
    if (u > 0 && u < min) min = u;
  }
  return min === Infinity ? 0 : min;
}

// ---------- タイムアウト ----------
const TIMEOUTS = {
  implement: { light: 15, medium: 30, heavy: 45 },
  review: { light: 10, medium: 15, heavy: 20 },
};
const timeoutMsFor = (stage, weight) => (TIMEOUTS[stage][weight ?? "medium"] ?? 30) * 60000;

// ---------- プロンプト生成 ----------
function fillTemplate(name, vars) {
  let text = fs.readFileSync(path.join(SCRIPTS_DIR, "prompts", name), "utf-8");
  for (const [k, v] of Object.entries(vars)) text = text.split(`{{${k}}}`).join(v ?? "");
  return text;
}
function buildDispatch(stage, task, cand) {
  const taskText = fs.readFileSync(task.file, "utf-8");
  const allowed = (task.allowed_paths ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  const changed = gitStatusPaths();
  const buckets = classify(task, changed);
  const wip = buckets.allowed.length > 0
    ? `\n\n## WIP (前任者の未完了変更)\n許可パス内に未コミットの変更があります: ${buckets.allowed.join(", ")}\nまず git diff で確認し、残りを仕上げてください。`
    : "";
  const vars = {
    ID: task.id,
    TASK_CONTENT: taskText,
    WORKDIR: REPO,
    ALLOWED_PATHS: allowed.join(", ") || "(未設定)",
    TEST_CMD: task.test_cmd || "(タスク定義の scoped test を実行すること)",
    MODEL: cand ? `${cand.runner}/${cand.model}` : "",
    REPORT_FILE: path.join(harnessDir, "tmp", `${task.id}-${stage === "review" ? "review" : "report"}.md`),
    VERDICT_FILE: path.join(harnessDir, "verdicts", `${task.id}.txt`),
    WIP_NOTE: wip,
  };
  const name = stage === "review" ? "reviewer.md" : "implementer.md";
  const out = path.join(harnessDir, "dispatch", `${task.id}-${stage}.md`);
  fs.writeFileSync(out, fillTemplate(name, vars), "utf-8");
  return { promptFile: out, reportFile: vars.REPORT_FILE, verdictFile: vars.VERDICT_FILE };
}

function runWorker(stage, task, cand) {
  const { promptFile, reportFile, verdictFile } = buildDispatch(stage, task, cand);
  if (fs.existsSync(reportFile)) fs.unlinkSync(reportFile);
  const log = path.join(harnessDir, "logs", `${task.id}.log`);
  const args = [
    path.join(SCRIPTS_DIR, "run-worker.mjs"),
    "--runner", cand.runner, "--model", cand.model,
    "--stage", stage, "--prompt-file", promptFile,
    "--workdir", REPO, "--log", log,
    "--timeout-ms", String(timeoutMsFor(stage, task.weight)),
  ];
  if (cand.effort) args.push("--effort", cand.effort);
  if (stage === "review") args.push("--verdict-file", verdictFile);
  note(`dispatch ${stage}: ${task.id} -> ${cand.runner}/${cand.model}`);
  const r = sh(process.execPath, args, { timeout: timeoutMsFor(stage, task.weight) + 120000 });
  const lastLine = r.out.trim().split("\n").filter(Boolean).pop() ?? "{}";
  let result;
  try { result = JSON.parse(lastLine); } catch { result = { outcome: "error", code: r.code }; }
  return { ...result, reportFile, verdictFile };
}

function quotaCooldown(cand, logTail) {
  if (cand.runner === "agy") {
    const m = /Resets in\s+(?:(\d+)h)?\s*(?:(\d+)m)?/i.exec(logTail ?? "");
    const ms = m ? ((Number(m[1] ?? 0) * 60 + Number(m[2] ?? 0)) * 60000 || 5 * 3600000) : 5 * 3600000;
    setCooldown(cand.key, Date.now() + ms, "quota_exhausted");
  } else {
    setCooldown(cand.key, Date.now() + 20 * 60000, "rate_limit_429");
  }
}
function logTail(taskId, n = 4000) {
  const f = path.join(harnessDir, "logs", `${taskId}.log`);
  if (!fs.existsSync(f)) return "";
  const text = fs.readFileSync(f, "utf-8");
  return text.slice(-n);
}

// ---------- ステージ処理 ----------
function appendNote(task, section, text) {
  const tmp = path.join(harnessDir, "tmp", `${task.id}-note.md`);
  fs.writeFileSync(tmp, text, "utf-8");
  // set-report は節を置換するため、既存内容に追記する形で合成する
  const current = fs.readFileSync(task.file, "utf-8");
  const re = new RegExp(`##\\s+${section}\\b[^\\n]*\\n([\\s\\S]*?)(?=\\n##\\s+(?:TASK DEFINITION|REPORT|TEST|REVIEW|QA|QA Result|QA Return|Planner Note|目的|実装内容|受入条件|備考|autoloop run|🚨)|$)`);
  const m = re.exec(current);
  const merged = (m ? m[1].trim() + "\n\n" : "") + text;
  fs.writeFileSync(tmp, merged, "utf-8");
  taskCtl(["set-report", task.file, "--section", section, "--from", tmp]);
}

function handleImplement(task) {
  if (task.status === "todo") {
    taskCtl(["transition", task.file, "--to", "doing"]);
    task = scanTasks().find((t) => t.id === task.id) ?? task;
  }
  const candidates = implementerCandidates(task);
  const usable = available(candidates);
  if (usable.length === 0) return { worked: false, coolingUntil: earliestCooling(candidates) };
  for (const cand of usable.slice(0, 4)) {
    taskCtl(["set", task.file, "--set", `assignee=${cand.runner}`, "--set", `model=${cand.model}`]);
    const res = runWorker("implement", task, cand);
    if (res.outcome === "quota") { quotaCooldown(cand, logTail(task.id)); continue; }
    if (res.outcome === "timeout") {
      const changed = classify(task, gitStatusPaths());
      if (changed.allowed.length === 0) {
        setCooldown(cand.key, Date.now() + 60 * 60000, "timeout_stalled");
        continue;
      }
      appendNote(task, "REPORT", `- **[Runner Note]** ${cand.runner}/${cand.model} timed out with WIP in: ${changed.allowed.join(", ")}. Next worker: inspect git diff and finish.`);
      if ((task.attempts ?? 1) >= 3) taskCtl(["transition", task.file, "--to", "blocked"]);
      else taskCtl(["transition", task.file, "--to", "doing", "--bump-attempts"]);
      return { worked: true };
    }
    if (res.outcome === "error") { setCooldown(cand.key, Date.now() + 10 * 60000, "worker_error"); continue; }
    // ok
    if (fs.existsSync(res.reportFile)) taskCtl(["set-report", task.file, "--section", "REPORT", "--from", res.reportFile]);
    taskCtl(["transition", task.file, "--to", "review"]);
    note(`${task.id}: implement done by ${cand.runner}/${cand.model} -> review`);
    return { worked: true };
  }
  return { worked: false, coolingUntil: earliestCooling(candidates) };
}

function handleReview(task) {
  const token = `${task.attempts}.${task.review_round}`;
  if (task.verdict && task.verdict !== "NONE" && task.verdict_for === token) {
    if (task.verdict === "APPROVED") {
      taskCtl(["transition", task.file, "--to", "qa"]);
      note(`${task.id}: verdict APPROVED (${token}) -> qa`);
    } else if (task.verdict === "BLOCKED") {
      taskCtl(["transition", task.file, "--to", "blocked"]);
      note(`${task.id}: verdict BLOCKED (${token}) -> blocked`);
    } else {
      // CHANGES_REQUESTED
      if ((task.review_round ?? 0) >= 2) {
        if ((task.attempts ?? 1) >= 3) taskCtl(["transition", task.file, "--to", "blocked"]);
        else taskCtl(["transition", task.file, "--to", "doing", "--bump-attempts"]);
      } else {
        taskCtl(["transition", task.file, "--to", "doing"]);
      }
      note(`${task.id}: verdict CHANGES_REQUESTED (${token}) -> doing`);
    }
    return { worked: true };
  }
  // レビュアーを呼ぶ前にテストのプリチェック
  if (task.test_cmd) {
    const r = sh(task.test_cmd, [], { shell: true, timeout: 600000 });
    if (r.code !== 0) {
      appendNote(task, "REPORT", `- **[Runner Pre-check]** scoped tests FAILED before review:\n\n\`\`\`\n${r.out.trim().slice(-1500)}\n\`\`\``);
      taskCtl(["transition", task.file, "--to", "doing"]);
      note(`${task.id}: pre-check tests failed -> doing (review not spent)`);
      return { worked: true };
    }
  }
  const candidates = reviewerCandidates(task);
  const usable = available(candidates);
  if (usable.length === 0) return { worked: false, coolingUntil: earliestCooling(candidates) };
  let dispatches = 0;
  for (const cand of usable.slice(0, 4)) {
    if (dispatches >= 2) break;
    taskCtl(["set", task.file, "--set", `reviewer=${cand.runner}/${cand.model}`]);
    const res = runWorker("review", task, cand);
    dispatches++;
    if (res.outcome === "quota") { quotaCooldown(cand, logTail(task.id)); continue; }
    if (res.outcome === "timeout" || res.outcome === "error") {
      setCooldown(cand.key, Date.now() + 30 * 60000, `review_${res.outcome}`);
      continue;
    }
    if (res.verdict) {
      if (fs.existsSync(res.reportFile)) taskCtl(["set-report", task.file, "--section", "REVIEW", "--from", res.reportFile]);
      taskCtl(["verdict", task.file, "--verdict", res.verdict]);
      note(`${task.id}: review verdict ${res.verdict} by ${cand.runner}/${cand.model}`);
      return { worked: true };
    }
    note(`${task.id}: reviewer ${cand.runner}/${cand.model} returned no verdict; re-dispatching`);
    setCooldown(cand.key, Date.now() + 30 * 60000, "no_verdict");
  }
  return { worked: dispatches > 0, noVerdict: true };
}

function handleQA(task) {
  const taskText = fs.readFileSync(task.file, "utf-8");
  const qaFile = path.join(harnessDir, "tmp", `${task.id}-qa.md`);
  if (fs.existsSync(qaFile)) fs.unlinkSync(qaFile);
  const allowed = (task.allowed_paths ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  const prompt = fillTemplate("qa.md", {
    ID: task.id, TASK_CONTENT: taskText,
    ALLOWED_PATHS: allowed.join(", ") || "(未設定)", QA_FILE: qaFile,
  });
  const binParts = (process.env.CODEX_BIN || "codex").split(/\s+/);
  const r = sh(binParts[0], [...binParts.slice(1), "exec", "--model", LUNA_MODEL, "--sandbox", "workspace-write", "-"], {
    input: prompt,
    shell: process.platform === "win32" && !process.env.CODEX_BIN,
    timeout: 600000,
  });
  if (!fs.existsSync(qaFile)) {
    note(`${task.id}: QA produced no result file (codex code=${r.code})`);
    return { worked: false, qaError: true };
  }
  const qaText = fs.readFileSync(qaFile, "utf-8");
  taskCtl(["set-report", task.file, "--section", "QA", "--from", qaFile]);
  const matches = [...qaText.matchAll(/QA-VERDICT:\s*(PASS|FAIL)/g)];
  const verdict = matches.length > 0 ? matches[matches.length - 1][1] : null;
  if (verdict) {
    // 現在の QA 判定は frontmatter を正本として刻印する。本文の QA 節には過去分の
    // 断片が残り得て、出現順序も時系列を保証しないため、プランナーはこちらを見る
    taskCtl(["set", task.file, "--set", `qa_verdict=${verdict}`, "--set", `qa_at=${new Date().toISOString()}`]);
  }
  if (verdict === "PASS") {
    return commitFlow(task);
  }
  if (verdict === "FAIL") {
    if ((task.attempts ?? 1) >= 3) taskCtl(["transition", task.file, "--to", "blocked"]);
    else taskCtl(["transition", task.file, "--to", "doing", "--bump-attempts"]);
    note(`${task.id}: QA FAIL -> ${((task.attempts ?? 1) >= 3) ? "blocked" : "doing (attempts+1)"}`);
    return { worked: true };
  }
  note(`${task.id}: QA result file has no QA-VERDICT line`);
  return { worked: false, qaError: true };
}

function commitPaths(paths, message) {
  if (paths.length === 0) return true;
  const add = git(["add", "--", ...paths]);
  if (add.code !== 0) { note(`git add failed: ${add.out.trim().slice(-200)}`); return false; }
  const c = git(["commit", "-m", message, "--", ...paths]);
  if (c.code !== 0) { note(`git commit failed: ${c.out.trim().slice(-200)}`); return false; }
  note(`committed: ${message}`);
  return true;
}

function commitFlow(task) {
  const changed = gitStatusPaths();
  const b = classify(task, changed);
  if (b.forbidden.length > 0 || b.unmapped.length > 0) {
    appendNote(task, "QA", `- **[Runner Gate]** commit refused. forbidden: [${b.forbidden.join(", ")}] unmapped: [${b.unmapped.join(", ")}]`);
    if ((task.attempts ?? 1) >= 3) taskCtl(["transition", task.file, "--to", "blocked"]);
    else taskCtl(["transition", task.file, "--to", "doing", "--bump-attempts"]);
    note(`${task.id}: commit gate refused (forbidden=${b.forbidden.length}, unmapped=${b.unmapped.length})`);
    return { worked: true };
  }
  if (!commitPaths(b.allowed, `feat(${curPhase}): complete ${task.id}`)) {
    note(`${task.id}: commit of deliverables failed; leaving status as ${task.status}`);
    return { worked: false };
  }
  taskCtl(["transition", task.file, "--to", "done"]);
  const ledgerFiles = [`${progressRel}/tasks/${task.id}.md`, `${progressRel}/PROGRESS.md`]
    .filter((p) => gitStatusPaths().includes(p));
  commitPaths(ledgerFiles, `docs(progress): mark ${task.id} done`);
  const pushed = gitPush();
  note(`${task.id}: done, committed${pushed ? " and pushed" : " (push failed)"}`);
  return { worked: true };
}

// ---------- プランナー (Luna: 分解・blocked 審査・次フェーズ起票) ----------
function roundsOf(phase) { return state.autoloop.planner.rounds[phase] ?? 0; }
function bumpRound(phase) {
  state.autoloop.planner.rounds[phase] = roundsOf(phase) + 1;
  saveState();
  return state.autoloop.planner.rounds[phase];
}
function appendProgressAlert(text) {
  if (fs.existsSync(PROGRESS_FILE)) fs.appendFileSync(PROGRESS_FILE, `\n${text}\n`, "utf-8");
}
function commitLedgerChanges(message) {
  const changed = gitStatusPaths().filter((p) => p.startsWith("progress/"));
  if (changed.length === 0) return false;
  if (!commitPaths(changed, message)) return false;
  gitPush();
  return true;
}
function nonLedgerChanges() {
  return gitStatusPaths().filter(
    (p) => !p.startsWith("progress/") && !p.startsWith(".pi/harness/"),
  );
}
function quarantineInvalidTasks() {
  let n = 0;
  for (const t of scanTasks()) {
    if (t.status !== "todo") continue;
    const missing = [];
    if (parseAllowed(t).length === 0) missing.push("allowed_paths");
    if (!t.test_cmd) missing.push("test_cmd");
    if (missing.length > 0) {
      taskCtl(["set", t.file, "--set", "status=blocked"]);
      appendNote(t, "REPORT", `- **[Planner Gate]** runner quarantined this task: frontmatter is missing ${missing.join(", ")}. Fix the fields and set status back to todo to resume.`);
      note(`quarantine: ${t.id} -> blocked (missing ${missing.join(", ")})`);
      n++;
    }
  }
  return n;
}

function runPlanner(mode) {
  const planFile = path.join(harnessDir, "tmp", "plan-verdict.txt");
  if (fs.existsSync(planFile)) fs.unlinkSync(planFile);
  const tasksNow = scanTasks();
  const blockedDetails = tasksNow.filter((t) => t.status === "blocked")
    .map((t) => `\n----- ${t.id} -----\n${fs.readFileSync(t.file, "utf-8")}`).join("\n") || "(なし)";
  let existingPhases = "(なし)";
  try {
    existingPhases = fs.readdirSync(path.join(REPO, "progress"), { withFileTypes: true })
      .filter((d) => d.isDirectory()).map((d) => d.name).join(", ") || "(なし)";
  } catch { /* progress/ 自体がない場合はそのまま */ }
  const prompt = fillTemplate("planner.md", {
    PHASE: curPhase, MODE: mode, ROUND: String(roundsOf(curPhase) + 1),
    SCAN_JSON: JSON.stringify(tasksNow.map((t) => ({
      id: t.id, status: t.status, weight: t.weight, attempts: t.attempts,
      allowed_paths: t.allowed_paths ?? "", test_cmd: t.test_cmd ?? "",
    })), null, 1),
    BLOCKED_DETAILS: blockedDetails,
    DIRTY_PATHS: gitStatusPaths().join(", ") || "(なし)",
    VERDICT_FILE: planFile,
    PROGRESS_PATH: `${progressRel}/PROGRESS.md`,
    EXISTING_PHASES: existingPhases,
  });
  const binParts = (process.env.CODEX_BIN || "codex").split(/\s+/);
  const r = sh(binParts[0], [...binParts.slice(1), "exec", "--model", LUNA_MODEL, "--sandbox", "workspace-write", "-"], {
    input: prompt,
    shell: process.platform === "win32" && !process.env.CODEX_BIN,
    timeout: 1800000,
  });
  if (!fs.existsSync(planFile)) {
    note(`planner (${mode}) produced no verdict file (codex code=${r.code})`);
    return { verdict: null, arg: "", reason: "" };
  }
  const lines = fs.readFileSync(planFile, "utf-8").split("\n").map((s) => s.trim()).filter(Boolean);
  const verdictRe = /^PLAN:\s*(MORE|COMPLETE|NEEDS_HUMAN|ALL_DONE|NEXT)\b\s*(\S+)?/;
  const m = lines.slice(0, 5).map((l) => verdictRe.exec(l)).find(Boolean) ?? null;
  if (!m) {
    note(`planner (${mode}) verdict unparsable: ${(lines[0] ?? "").slice(0, 80)}`);
    return { verdict: null, arg: "", reason: "" };
  }
  return { verdict: m[1], arg: m[2] ?? "", reason: lines.slice(1).join(" ").slice(0, 300) };
}

function plannerInvalid() {
  state.autoloop.planner.invalid = (state.autoloop.planner.invalid ?? 0) + 1;
  saveState();
  if (state.autoloop.planner.invalid >= 2) { finalize("planner verdict invalid twice"); return "stopped"; }
  return "continue";
}

// 駆動可能なタスクが尽きたときに呼ばれる。戻り値:
//   'continue'    … 駆動対象ができた (または再試行する) のでループ継続
//   'stopped'     … finalize 済み
//   'unavailable' … プランナー予算切れ。従来の停止理由にフォールバックする
async function planningStep() {
  if (roundsOf(curPhase) >= MAX_PLAN_ROUNDS) return "unavailable";
  const round = bumpRound(curPhase);
  const beforeActive = scanTasks().filter((t) => ["todo", "doing", "review", "qa"].includes(t.status)).length;
  const beforePaths = new Set(gitStatusPaths());
  note(`planner round ${round} for ${curPhase} (decompose)`);
  const res = runPlanner("decompose");
  // 越境判定は「プランナー実行前からあった変更」を除く。
  // blocked タスクの未コミット WIP が残っているのが正常で、それを誤検知しないため
  const outside = nonLedgerChanges().filter((p) => !beforePaths.has(p));
  if (outside.length > 0) {
    appendProgressAlert(`## 🚨 Planner overreach (round ${round})\n- プランナーが台帳外のパスを変更したため停止しました: ${outside.join(", ")}`);
    commitLedgerChanges(`chore(progress): planner round ${round} for ${curPhase}`);
    finalize(`planner touched non-ledger paths: ${outside.slice(0, 3).join(", ")}`);
    return "stopped";
  }
  if (!res.verdict) return plannerInvalid();
  state.autoloop.planner.invalid = 0;
  saveState();
  if (res.verdict === "NEEDS_HUMAN") {
    commitLedgerChanges(`chore(progress): planner round ${round} for ${curPhase} (needs human)`);
    finalize(`planner: needs human — ${res.reason || "see PROGRESS"}`);
    return "stopped";
  }
  if (res.verdict === "COMPLETE") {
    const check = scanTasks();
    const unfinished = check.filter((t) => ["todo", "doing", "review", "qa", "blocked", "corrupt"].includes(t.status));
    if (unfinished.length > 0) {
      note(`planner round ${round}: COMPLETE rejected (${unfinished.map((t) => `${t.id}:${t.status}`).join(", ")})`);
      return await plannerInvalid();
    }
    commitLedgerChanges(`chore(progress): planner round ${round} for ${curPhase} (phase complete)`);
    return await advancePhase();
  }
  if (res.verdict === "MORE") {
    quarantineInvalidTasks();
    commitLedgerChanges(`chore(progress): planner round ${round} for ${curPhase}`);
    const afterActive = scanTasks().filter((t) => ["todo", "doing", "review", "qa"].includes(t.status)).length;
    if (afterActive > beforeActive) {
      state.autoloop.planner.noProgress = 0;
      saveState();
      return "continue";
    }
    state.autoloop.planner.noProgress = (state.autoloop.planner.noProgress ?? 0) + 1;
    saveState();
    if (state.autoloop.planner.noProgress >= 2) {
      finalize("planner produced no actionable tasks in 2 rounds");
      return "stopped";
    }
    return "continue";
  }
  note(`planner: unexpected verdict ${res.verdict} in decompose mode`);
  return plannerInvalid();
}

// ---------- 統合ゲート (CI green → main マージ) ----------
function currentBranch() {
  return git(["rev-parse", "--abbrev-ref", "HEAD"]).out.trim();
}

function ciStatusForHead() {
  const sha = gitHead();
  const branch = currentBranch();
  const r = sh("gh", ["run", "list", "--branch", branch, "--limit", "15", "--json", "databaseId,headSha,status,conclusion,name,url"], { timeout: 60000 });
  if (r.code !== 0) return { state: "unavailable", detail: `${r.out ?? ""}`.trim().slice(-200) || "gh failed" };
  let runs;
  try { runs = JSON.parse(r.out); } catch { return { state: "unavailable", detail: "gh output unparsable" }; }
  const wanted = CI_WORKFLOWS ? CI_WORKFLOWS.split(",").map((s) => s.trim()).filter(Boolean) : null;
  const mine = runs.filter((x) => x.headSha === sha && (!wanted || wanted.includes(x.name)));
  if (mine.length === 0) return { state: "none", sha };
  if (wanted && wanted.length > 0) {
    const missing = wanted.filter((w) => !mine.some((x) => x.name === w));
    if (missing.length > 0) return { state: "pending", sha, missing };
  }
  if (mine.some((x) => x.status !== "completed")) return { state: "pending", sha };
  const failed = mine.filter((x) => x.conclusion !== "success")
    .map((x) => ({ id: x.databaseId, name: x.name, conclusion: x.conclusion, url: x.url }));
  if (failed.length > 0) return { state: "red", sha, failed };
  return { state: "green", sha, count: mine.length };
}

async function waitForCI() {
  const deadline = Date.now() + CI_TIMEOUT_MS;
  let unavailableCount = 0;
  for (;;) {
    if (fs.existsSync(STOP_FILE)) return { state: "stopped" };
    const s = ciStatusForHead();
    if (s.state === "green" || s.state === "red") return s;
    if (s.state === "unavailable") {
      unavailableCount += 1;
      if (unavailableCount >= 3) return s;
    } else {
      unavailableCount = 0;
    }
    if (Date.now() > deadline) return { state: "timeout", sha: s.sha };
    await sleep(CI_POLL_MS);
  }
}

function mergeToMain(sourceBranch, phase) {
  git(["fetch", "origin"], { timeout: 120000 });
  let r = git(["checkout", "main"], { timeout: 60000 });
  if (r.code !== 0) {
    r = git(["checkout", "-b", "main", "origin/main"], { timeout: 60000 });
    if (r.code !== 0) {
      git(["checkout", sourceBranch], { timeout: 60000 });
      return { ok: false, detail: `checkout main failed: ${r.out.trim().slice(-200)}` };
    }
  } else {
    const ff = git(["merge", "--ff-only", "origin/main"], { timeout: 60000 });
    if (ff.code !== 0) {
      git(["checkout", sourceBranch], { timeout: 60000 });
      return { ok: false, detail: "local main has diverged from origin/main; resolve manually" };
    }
  }
  const m = git(["merge", "--no-ff", sourceBranch, "-m", `chore: integrate ${phase} into main (autoloop phase completion)`], { timeout: 120000 });
  if (m.code !== 0) {
    git(["merge", "--abort"], { timeout: 60000 });
    git(["checkout", sourceBranch], { timeout: 60000 });
    return { ok: false, detail: `merge of ${sourceBranch} into main failed (conflict?): ${m.out.trim().slice(-200)}` };
  }
  const sha = gitHead();
  const p = git(["push", "origin", "main"], { timeout: 180000 });
  if (p.code !== 0) {
    git(["checkout", sourceBranch], { timeout: 60000 });
    return { ok: false, detail: `merge commit ${sha.slice(0, 8)} exists on local main but push failed: ${p.out.trim().slice(-200)}` };
  }
  return { ok: true, sha };
}

async function integrationGate(phase) {
  const branch = currentBranch();
  if (branch === "main") { note("integration gate: already on main; nothing to merge"); return "skipped"; }
  if (!gitPush()) {
    await stopWithAlert("integration-push-failed", `git push of ${branch} failed before CI check in ${phase}`);
    return "failed";
  }
  note(`integration gate: waiting for CI on ${branch} @ ${gitHead().slice(0, 8)}`);
  const ci = await waitForCI();
  if (ci.state === "stopped") { finalize("kill switch (STOP file)"); return "stopped"; }
  if (ci.state !== "green") {
    let reason;
    if (ci.state === "red") {
      let quotaHint = "";
      const first = ci.failed[0];
      if (first && first.id) {
        const log = sh("gh", ["run", "view", String(first.id), "--log-failed"], { timeout: 120000 });
        if (/spending limit|billing|payment|usage limit|quota/i.test(log.out)) {
          quotaHint = " (failed log mentions Actions billing/quota)";
        }
      }
      reason = `integration gate: CI not green on ${branch} — ${ci.failed.map((f) => `${f.name}: ${f.conclusion}`).join("; ")}${quotaHint}`;
    } else if (ci.state === "unavailable") {
      reason = `integration gate: CI status unavailable (${ci.detail})`;
    } else {
      reason = `integration gate: CI did not reach green (${ci.state})`;
    }
    appendProgressAlert(`## Integration gate (${new Date().toISOString()})\n- ${reason}\n- main へのマージは行っていません。CI を green にして再起動すると、ゲートから再開します`);
    commitLedgerChanges(`docs(progress): integration gate stop for ${phase}`);
    finalize(reason);
    return "stopped";
  }
  note(`integration gate: CI green (${ci.count} workflow(s)) on ${branch} @ ${ci.sha.slice(0, 8)}`);
  const m = mergeToMain(branch, phase);
  if (!m.ok) { finalize(`integration gate: merge failed — ${m.detail}`); return "stopped"; }
  if (!Array.isArray(state.autoloop.merges)) state.autoloop.merges = [];
  state.autoloop.merges.push({ phase, sha: m.sha, at: new Date().toISOString() });
  saveState();
  note(`integration gate: merged ${phase} into main at ${m.sha.slice(0, 8)}`);
  return "merged";
}

async function advancePhase() {
  const completedPhase = curPhase;
  if (MERGE_ENABLED) {
    const gate = await integrationGate(completedPhase);
    if (gate === "stopped") return "stopped";
  }
  if (state.autoloop.planner.phases.length >= MAX_PHASES) {
    finalize(`phase complete (${completedPhase}); max phases per run reached (${MAX_PHASES})`);
    return "stopped";
  }
  note(`planner: bootstrapping next phase after ${completedPhase}`);
  const beforePaths = new Set(gitStatusPaths());
  const res = runPlanner("bootstrap");
  const outside = nonLedgerChanges().filter((p) => !beforePaths.has(p));
  if (outside.length > 0) {
    appendProgressAlert(`## 🚨 Planner overreach (bootstrap)\n- プランナーが台帳外のパスを変更したため停止しました: ${outside.join(", ")}`);
    commitLedgerChanges(`chore(progress): planner bootstrap after ${completedPhase}`);
    finalize(`planner touched non-ledger paths: ${outside.slice(0, 3).join(", ")}`);
    return "stopped";
  }
  if (res.verdict === "ALL_DONE") {
    commitLedgerChanges(`chore(progress): planner bootstrap after ${completedPhase} (all phases done)`);
    finalize("all phases complete (planner: ALL_DONE)");
    return "stopped";
  }
  if (res.verdict === "NEXT" && /^phase-[a-z0-9][a-z0-9-]*$/.test(res.arg)) {
    if (fs.existsSync(path.join(REPO, "progress", res.arg, "tasks"))) {
      commitLedgerChanges(`chore(progress): bootstrap ${res.arg} (planner)`);
      setPhase(res.arg);
      state.autoloop.planner.phases.push(res.arg);
      saveState();
      note(`planner: advanced to phase ${res.arg}`);
      // 次フェーズの作業ブランチを現在のブランチ (通常はマージ済み main) から切る
      const wb = `loop/${res.arg}`;
      const br = git(["checkout", "-b", wb], { timeout: 60000 });
      if (br.code === 0) {
        note(`created branch ${wb}`);
      } else {
        const co = git(["checkout", wb], { timeout: 60000 });
        note(co.code === 0 ? `checked out existing branch ${wb}` : `could not switch to branch ${wb}; staying on ${currentBranch()}`);
      }
      gitPush();
      if (quarantineInvalidTasks() > 0) {
        commitLedgerChanges(`chore(progress): quarantine invalid tasks in ${res.arg}`);
      }
      return "continue";
    }
    note(`planner: NEXT ${res.arg} but progress/${res.arg}/tasks does not exist`);
  } else if (!res.verdict) {
    note("planner: bootstrap produced no valid verdict");
  }
  commitLedgerChanges(`chore(progress): planner bootstrap after ${completedPhase}`);
  finalize(`phase complete (${completedPhase}); next phase was not started (planner verdict: ${res.verdict ?? "none"})`);
  return "stopped";
}

// ---------- 起動時スイープと終了処理 ----------
function startupSweep(tasks) {
  for (const t of tasks) {
    if (t.status !== "done") continue;
    const b = classify(t, gitStatusPaths());
    if ((b.allowed.length > 0 || b.ledger.length > 0) && b.forbidden.length === 0 && b.unmapped.length === 0) {
      note(`sweep: ${t.id} is done but has uncommitted deliverables/ledger; committing`);
      if (b.allowed.length > 0 && !commitPaths(b.allowed, `feat(${curPhase}): complete ${t.id}`)) {
        note(`sweep: ${t.id} deliverable commit failed; skipping`);
        continue;
      }
      const ledgerFiles = [`${progressRel}/tasks/${t.id}.md`, `${progressRel}/PROGRESS.md`]
        .filter((p) => gitStatusPaths().includes(p));
      if (ledgerFiles.length > 0) commitPaths(ledgerFiles, `docs(progress): mark ${t.id} done`);
      if (!gitPush()) note(`sweep: ${t.id} push failed`);
    }
  }
}

function finalize(reason) {
  const tasks = scanTasks();
  const lines = [
    ``,
    `## autoloop run (${new Date().toISOString()})`,
    `- stop reason: ${reason}`,
    ...tasks.map((t) => `- ${t.id ?? "?"}: ${t.status}`),
    ...runLog.slice(-15).map((l) => `- log: ${l}`),
  ];
  if (fs.existsSync(PROGRESS_FILE)) {
    fs.appendFileSync(PROGRESS_FILE, lines.join("\n") + "\n", "utf-8");
  }
  const changed = gitStatusPaths().filter((p) => p.startsWith(`${progressRel}/`));
  if (changed.length > 0) {
    // 理由文をそのまま件名に入れると長大になり、コミット規約チェックを落とすため短く切る
    const shortReason = reason.replace(/\s+/g, " ").slice(0, 60);
    commitPaths(changed, `docs(progress): autoloop run summary (${shortReason})`);
    gitPush();
  }
  note(`stopped: ${reason}`);
}

function corruptGate(tasks) {
  const corrupt = tasks.filter((t) => t.status === "corrupt");
  if (corrupt.length === 0) return false;
  for (const t of corrupt) {
    note(`corrupt task file: ${t.file} (${t.error}); trying heal`);
    const r = taskCtl(["heal", t.file]);
    note(`heal result: ${r.out.trim()}`);
  }
  const after = scanTasks();
  const still = after.filter((t) => t.status === "corrupt");
  if (still.length > 0) {
    const names = still.map((t) => `${t.file} (${t.error})`).join("; ");
    if (fs.existsSync(PROGRESS_FILE)) {
      fs.appendFileSync(PROGRESS_FILE, `\n## 🚨 CORRUPT (要確認)\n- ${names}\n`, "utf-8");
    }
    const changed = gitStatusPaths().filter((p) => p.startsWith(`${progressRel}/`));
    if (changed.length > 0) commitPaths(changed, "docs(progress): corrupt task file alert");
    gitPush();
    console.error(`autoloop: unhealable corrupt task file(s): ${names}`);
    process.exit(2);
  }
  return true;
}

// ---------- メインループ ----------
async function sleep(ms) { return new Promise((res) => setTimeout(res, ms)); }

async function main() {
  note(`start: phase=${phaseSlug} maxCycles=${MAX_CYCLES} maxHours=${MAX_HOURS} plan=${PLAN_ENABLED ? `on (rounds<=${MAX_PLAN_ROUNDS}, phases<=${MAX_PHASES})` : "off"} merge=${MERGE_ENABLED ? `on${CI_WORKFLOWS ? ` (workflows: ${CI_WORKFLOWS})` : ""}` : "off"}`);
  if (!state.autoloop.planner.phases.includes(curPhase)) {
    state.autoloop.planner.phases.push(curPhase);
    saveState();
  }
  let tasks = scanTasks();
  corruptGate(tasks);
  tasks = scanTasks();
  refreshAllAllowed(tasks);
  startupSweep(tasks);

  let stagnation = 0;
  let qaErrors = 0;
  for (let cycle = 1; cycle <= MAX_CYCLES; cycle++) {
    if (fs.existsSync(STOP_FILE)) { finalize("kill switch (STOP file)"); return; }
    if (Date.now() - startedAt > MAX_HOURS * 3600000) { finalize("budget: max hours"); return; }
    tasks = scanTasks();
    if (tasks.some((t) => t.status === "corrupt")) { corruptGate(tasks); tasks = scanTasks(); }
    refreshAllAllowed(tasks);
    if (quarantineInvalidTasks() > 0) { tasks = scanTasks(); refreshAllAllowed(tasks); }
    const active = tasks.filter((t) => ["todo", "doing", "review", "qa"].includes(t.status));
    const blocked = tasks.filter((t) => t.status === "blocked");
    if (active.length === 0) {
      if (PLAN_ENABLED && !ONCE) {
        const ps = await planningStep();
        if (ps === "continue") continue;
        if (ps === "stopped") return;
        // 'unavailable' (プランナー予算切れ) のときは従来の停止理由へ
      }
      if (blocked.length > 0) { finalize(`all remaining tasks blocked (${blocked.map((b) => b.id).join(", ")})`); return; }
      const ci = sh("gh", ["run", "list", "--limit", "1"], { timeout: 60000 });
      note(`phase complete. latest CI: ${ci.code === 0 ? ci.out.trim().split("\n")[0] : "unavailable"}`);
      finalize("phase complete (all tasks done; main merge is a separate gate)");
      return;
    }
    const sigBefore = tasks.map((t) => `${t.id}:${t.status}:${t.verdict ?? ""}:${t.verdict_for ?? ""}`).join("|") + "@" + gitHead();
    const pick = active.find((t) => t.status === "qa")
      ?? active.find((t) => t.status === "review")
      ?? active.find((t) => t.status === "doing")
      ?? active.find((t) => t.status === "todo");
    let result;
    if (pick.status === "qa") result = handleQA(pick);
    else if (pick.status === "review") result = handleReview(pick);
    else result = handleImplement(pick);

    if (result.qaError) {
      qaErrors++;
      if (qaErrors >= 2) { finalize(`QA orchestrator failed twice for ${pick.id}`); return; }
    } else qaErrors = 0;

    if (result.noVerdict) { finalize(`review verdict could not be obtained for ${pick.id}`); return; }

    if (!result.worked && result.coolingUntil) {
      const waitMs = result.coolingUntil - Date.now();
      if (waitMs > 30 * 60000 || Date.now() + waitMs > startedAt + MAX_HOURS * 3600000) {
        finalize(`all candidate models cooling until ${new Date(result.coolingUntil).toISOString()}`);
        return;
      }
      note(`all candidates cooling; sleeping ${Math.round(waitMs / 1000)}s`);
      const step = 15000;
      for (let slept = 0; slept < waitMs; slept += step) {
        if (fs.existsSync(STOP_FILE)) { finalize("kill switch (STOP file)"); return; }
        await sleep(Math.min(step, waitMs - slept));
      }
      continue;
    }
    const sigAfter = scanTasks().map((t) => `${t.id}:${t.status}:${t.verdict ?? ""}:${t.verdict_for ?? ""}`).join("|") + "@" + gitHead();
    if (result.worked && sigAfter === sigBefore) {
      stagnation++;
      note(`no progress despite work (stagnation ${stagnation}/3)`);
      if (stagnation >= 3) { finalize("stagnation breaker (3 worked cycles, no progress)"); return; }
    } else if (sigAfter !== sigBefore) {
      stagnation = 0;
    }
    if (state.autoloop.pushFailures >= 3) { finalize("push failed 3 times (unsynced)"); return; }
    if (ONCE) { finalize("--once"); return; }
  }
  finalize("budget: max cycles");
}

main().catch((err) => {
  console.error(`autoloop fatal: ${err.stack ?? err}`);
  process.exit(1);
});
