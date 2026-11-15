// git.ts — worktree / ブランチ / コミット / CI 確認 / マージ
//
// 決定事項:
// - ブランチ階層: main ← phase/<slug> ← worktree ごとのサブブランチ
// - コミットは 1 サイクル (実装 → レビュー → QA) の完了時に行う
// - マージ条件は GitHub Actions の CI がグリーンであること

import * as fs from "node:fs";
import * as path from "node:path";
import { runProcess, type RunResult } from "./runners/exec";

async function git(cwd: string, args: string[]): Promise<RunResult> {
  // git はネイティブ exe なのでシェルを介さない。シェル経由だと
  // コミットメッセージのような空白を含む引数が分割されてしまう
  // (Windows の npm シム対策で runProcess の既定はシェルありのため)
  return runProcess(["git", ...args], { cwd, shell: false });
}

export async function currentBranch(cwd: string): Promise<string> {
  const r = await git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"]);
  return r.stdout.trim();
}

/** 作業ツリーの変更ファイル一覧 (porcelain のパス部分) */
export async function changedFiles(cwd: string): Promise<string[]> {
  const r = await git(cwd, ["status", "--porcelain"]);
  return r.stdout
    .split("\n")
    .filter((l) => l.trim().length > 0)
    .map((l) => l.slice(3).trim().replace(/^"|"$/g, ""));
}

async function worktreePaths(repoRoot: string): Promise<string[]> {
  const r = await git(repoRoot, ["worktree", "list", "--porcelain"]);
  return r.stdout
    .split("\n")
    .filter((l) => l.startsWith("worktree "))
    .map((l) => l.slice("worktree ".length).trim());
}

async function branchExists(repoRoot: string, branch: string): Promise<boolean> {
  const r = await git(repoRoot, [
    "rev-parse",
    "--verify",
    "--quiet",
    `refs/heads/${branch}`,
  ]);
  return r.code === 0;
}

/**
 * worktree を用意する。既にあればそのパスを返し、無ければ作る。
 * ブランチが無ければ baseRef から新規作成、あればチェックアウトする。
 */
export async function ensureWorktree(
  repoRoot: string,
  worktreePath: string,
  branch: string,
  baseRef: string,
): Promise<{ path: string; created: boolean }> {
  const existing = await worktreePaths(repoRoot);
  const normalized = worktreePath.replace(/\\/g, "/").toLowerCase();
  if (
    existing.some((p) => p.replace(/\\/g, "/").toLowerCase() === normalized)
  ) {
    return { path: worktreePath, created: false };
  }
  const exists = await branchExists(repoRoot, branch);
  const args = exists
    ? ["worktree", "add", worktreePath, branch]
    : ["worktree", "add", "-b", branch, worktreePath, baseRef];
  const r = await git(repoRoot, args);
  if (r.code !== 0) {
    throw new Error(`git worktree add failed: ${r.stderr || r.stdout}`);
  }
  return { path: worktreePath, created: true };
}

/** 変更をすべてステージしてコミットする。変更が無ければ false */
export async function commitAll(
  worktree: string,
  message: string,
): Promise<boolean> {
  await git(worktree, ["add", "-A"]);
  const staged = await git(worktree, ["diff", "--cached", "--quiet"]);
  if (staged.code === 0) return false; // 差分なし
  const r = await git(worktree, ["commit", "-m", message]);
  if (r.code !== 0) {
    throw new Error(`git commit failed: ${r.stderr || r.stdout}`);
  }
  return true;
}

/** origin/<branch> へ未 push のコミット数。不明 (リモート側ブランチ無し等) は -1 */
export async function unpushedCount(
  worktree: string,
  branch: string,
): Promise<number> {
  const r = await git(worktree, [
    "rev-list",
    "--count",
    `origin/${branch}..HEAD`,
  ]);
  if (r.code !== 0) return -1;
  const n = Number.parseInt(r.stdout.trim(), 10);
  return Number.isNaN(n) ? -1 : n;
}

/** 現在のブランチを origin へ push する (upstream 未設定なら設定する) */
export async function pushCurrentBranch(
  worktree: string,
): Promise<{ pushed: boolean; branch: string; detail: string }> {
  const branch = await currentBranch(worktree);
  if (!branch || branch === "HEAD") {
    return { pushed: false, branch, detail: "detached HEAD" };
  }
  const r = await git(worktree, ["push", "-u", "origin", branch]);
  if (r.code !== 0) {
    throw new Error(
      `git push failed: ${(r.stderr || r.stdout).trim().slice(-300)}`,
    );
  }
  return { pushed: true, branch, detail: (r.stderr || r.stdout).trim() };
}

/** 指定パスに未コミットの変更 (未追跡ファイル含む) が残っているか */
export async function hasUncommitted(
  worktree: string,
  paths: string[],
): Promise<boolean> {
  if (paths.length === 0) return false;
  const r = await git(worktree, ["status", "--porcelain", "--", ...paths]);
  return r.stdout.trim().length > 0;
}

/** 指定パスだけをステージしてコミットする。変更が無ければ committed: false */
export async function commitPaths(
  worktree: string,
  paths: string[],
  message: string,
): Promise<{ committed: boolean; skipped: string[] }> {
  if (paths.length === 0) return { committed: false, skipped: [] };
  // 実在するファイルか、追跡済み (削除された) ファイルだけを add 対象にする。
  // REPORT の記載ミス等で存在しないパスが混ざってもコミット全体を
  // 失敗させず、skipped として呼び出し側に返す
  const tracked = new Set(
    (await git(worktree, ["ls-files"])).stdout
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
  );
  const valid: string[] = [];
  const skipped: string[] = [];
  for (const p of paths) {
    if (fs.existsSync(path.join(worktree, p)) || tracked.has(p)) {
      valid.push(p);
    } else {
      skipped.push(p);
    }
  }
  if (valid.length === 0) return { committed: false, skipped };
  const add = await git(worktree, ["add", "--", ...valid]);
  if (add.code !== 0) {
    throw new Error(`git add failed: ${add.stderr || add.stdout}`);
  }
  // 判定もコミットも対象パスに限定する。index 全体を見ると、他のタスクや
  // 人間が stage した無関係な変更まで巻き込んでコミットしてしまう
  const staged = await git(worktree, [
    "diff",
    "--cached",
    "--quiet",
    "--",
    ...valid,
  ]);
  if (staged.code === 0) return { committed: false, skipped }; // 差分なし
  const r = await git(worktree, ["commit", "-m", message, "--", ...valid]);
  if (r.code !== 0) {
    throw new Error(`git commit failed: ${r.stderr || r.stdout}`);
  }
  return { committed: true, skipped };
}

export type CiConclusion =
  | "success"
  | "failure"
  | "in_progress"
  | "none"
  | "unknown";

/** 対象ブランチの最新 CI run の結論を gh で確認する */
export async function ciConclusion(
  repoRoot: string,
  branch: string,
): Promise<CiConclusion> {
  const r = await runProcess(
    [
      "gh",
      "run",
      "list",
      "--branch",
      branch,
      "--limit",
      "1",
      "--json",
      "status,conclusion",
    ],
    { cwd: repoRoot },
  );
  if (r.code !== 0) return "unknown";
  try {
    const runs = JSON.parse(r.stdout) as Array<{
      status: string;
      conclusion: string | null;
    }>;
    if (runs.length === 0) return "none";
    const run = runs[0];
    if (run.status !== "completed") return "in_progress";
    return run.conclusion === "success" ? "success" : "failure";
  } catch {
    return "unknown";
  }
}

/**
 * fromBranch を intoBranch へマージする (repoRoot のチェックアウトで実行)。
 * 呼び出し側は事前に (1) 作業ツリーがクリーンであること、
 * (2) CI がグリーンであること、を確認する責務を持つ。
 */
export async function mergeInto(
  repoRoot: string,
  fromBranch: string,
  intoBranch: string,
): Promise<RunResult> {
  const checkout = await git(repoRoot, ["checkout", intoBranch]);
  if (checkout.code !== 0) return checkout;
  return git(repoRoot, [
    "merge",
    "--no-ff",
    "-m",
    `Merge ${fromBranch} into ${intoBranch}`,
    fromBranch,
  ]);
}
