#!/usr/bin/env node
// run-worker.mjs — ワーカー CLI (agy / opencode) を1回だけ同期実行するラッパー。
//
// - 指示はファイル経由 (dispatch prompt) で渡し、引数は短いポインタだけにする
//   (Windows のシム経由で長い引数が壊れる事故の回避)
// - 終了コードではなく、終了コード + 出力 + 成果物で結果を分類する
// - 結果は最終行に JSON で stdout へ出す:
//   {"outcome":"ok|quota|timeout|error","code":n,"verdict":"APPROVED|CHANGES_REQUESTED|BLOCKED|null","log":"..."}
//
// 使い方:
//   node scripts/run-worker.mjs --runner agy --model "Gemini 4 Argon" --effort Medium \
//     --stage implement --prompt-file <abs> --workdir <abs> --log <abs> --timeout-ms 1800000
//   node scripts/run-worker.mjs --runner opencode --model opencode/glm-5.3-flash-free \
//     --stage review --prompt-file <abs> --workdir <abs> --log <abs> --timeout-ms 900000 \
//     --verdict-file <abs>
//
// バイナリの上書き (テスト用): AGY_BIN / OPENCODE_BIN 環境変数 ("cmd args..." 形式可)

import fs from "node:fs";
import path from "node:path";
import { spawn, execFileSync } from "node:child_process";

function arg(name, def = null) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const runner = arg("runner");
const model = arg("model");
const effort = arg("effort", "Medium");
const stage = arg("stage", "implement");
const promptFile = arg("prompt-file");
const workdir = arg("workdir", process.cwd());
const logFile = arg("log");
const timeoutMs = Number.parseInt(arg("timeout-ms", "1800000"), 10);
const verdictFile = arg("verdict-file");

if (!runner || !model || !promptFile) {
  console.error("run-worker: --runner, --model, --prompt-file are required");
  process.exit(2);
}

function splitBin(envVal, def) {
  const v = envVal && envVal.trim() ? envVal.trim() : def;
  const parts = v.split(/\s+/);
  return { cmd: parts[0], prefix: parts.slice(1) };
}

const pointer = `Read and follow the instructions in the file ${promptFile} exactly. Work only in ${workdir}.`;
let bin, args, useShell = false;

if (runner === "agy") {
  const b = splitBin(process.env.AGY_BIN, "agy");
  bin = b.cmd;
  const display = model.includes("(") ? model : `${model} (${effort})`;
  const printTimeoutMin = Math.max(1, Math.round(timeoutMs / 60000) - 5);
  args = [...b.prefix, "--model", display, "--print-timeout", `${printTimeoutMin}m`, "-p", pointer];
  if (stage === "review") {
    args.push("--output-format", "json", "--json-schema", '{"type":"object","properties":{"verdict":{"type":"string","enum":["APPROVED","CHANGES_REQUESTED","BLOCKED"]},"findings":{"type":"array","items":{"type":"string"}}},"required":["verdict"]}');
  }
} else if (runner === "opencode") {
  const b = splitBin(process.env.OPENCODE_BIN, "opencode");
  bin = b.cmd;
  args = [...b.prefix, "run", "--model", model, "--auto", pointer];
  // Windows では opencode は npm シム (.cmd) のためシェル経由が必要
  useShell = process.platform === "win32" && !process.env.OPENCODE_BIN;
} else {
  console.error(`run-worker: unknown runner ${runner}`);
  process.exit(2);
}

if (verdictFile && fs.existsSync(verdictFile)) fs.unlinkSync(verdictFile);
if (logFile) fs.mkdirSync(path.dirname(logFile), { recursive: true });
const logStream = logFile ? fs.createWriteStream(logFile, { flags: "a" }) : null;
logStream?.write(`\n===== ${new Date().toISOString()} ${runner} ${model} (${stage}) =====\n`);

function quoteShellArg(s) {
  return /[\s"&|<>^]/.test(s) ? `"${String(s).replace(/"/g, '\\"')}"` : s;
}

const spawnBin = useShell ? quoteShellArg(bin) : bin;
const spawnArgs = useShell ? args.map(quoteShellArg) : args;

const child = spawn(spawnBin, spawnArgs, {
  cwd: workdir,
  shell: useShell,
  env: { ...process.env, CI: "true" },
  detached: process.platform !== "win32",
  stdio: ["ignore", "pipe", "pipe"],
});

let captured = "";
child.stdout.on("data", (d) => { captured += d; logStream?.write(d); });
child.stderr.on("data", (d) => { captured += d; logStream?.write(d); });

let timedOut = false;
const timer = setTimeout(() => {
  timedOut = true;
  try {
    if (process.platform === "win32") {
      execFileSync("taskkill", ["/F", "/T", "/PID", String(child.pid)], { stdio: "ignore" });
    } else {
      process.kill(-child.pid, "SIGKILL");
    }
  } catch { /* already gone */ }
}, timeoutMs);

const QUOTA_RE = /quota|rate[\s_-]?limit|\b429\b|resource_exhausted|insufficient|usage limit/i;
const QUOTA_STRICT_RE = /individual quota reached|quota\s+(?:reached|exceeded|exhausted)|usage limit|rate[\s_-]?limit|insufficient\s+(?:balance|quota|credit)|no resource package|\b429\b/i;

function extractVerdict() {
  // 1) agy の構造化 JSON 出力
  const jsonMatches = captured.match(/\{[^{}]*"verdict"\s*:\s*"(APPROVED|CHANGES_REQUESTED|BLOCKED)"[^{}]*\}/g);
  if (jsonMatches && jsonMatches.length > 0) {
    try {
      const obj = JSON.parse(jsonMatches[jsonMatches.length - 1]);
      if (obj && typeof obj.verdict === "string") return obj.verdict.toUpperCase();
    } catch { /* fall through */ }
  }
  // 2) verdict ファイル (1語)
  if (verdictFile && fs.existsSync(verdictFile)) {
    const word = fs.readFileSync(verdictFile, "utf-8").trim().split(/\s+/)[0]?.toUpperCase();
    if (["APPROVED", "CHANGES_REQUESTED", "BLOCKED"].includes(word)) return word;
  }
  return null;
}

child.on("error", (err) => {
  clearTimeout(timer);
  logStream?.end();
  console.log(JSON.stringify({ outcome: "error", code: -1, verdict: null, log: logFile, error: String(err.message || err) }));
});

child.on("close", (code) => {
  clearTimeout(timer);
  logStream?.end();
  let outcome;
  if (timedOut) outcome = "timeout";
  else if (QUOTA_STRICT_RE.test(captured) || (code !== 0 && QUOTA_RE.test(captured))) outcome = "quota";
  else if (code !== 0) outcome = "error";
  else outcome = "ok";
  const verdict = stage === "review" ? extractVerdict() : null;
  console.log(JSON.stringify({ outcome, code: code ?? -1, verdict, log: logFile }));
});
