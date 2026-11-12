// git.ts — worktree / ブランチ / コミット / CI 確認 / マージ
//
// 決定事項:
// - ブランチ階層: main ← phase/<slug> ← worktree ごとのサブブランチ
// - コミットは 1 サイクル (実装 → レビュー → QA) の完了時に行う
// - マージ条件は GitHub Actions の CI がグリーンであること

import { runProcess, type RunResult } from "./runners/exec";

async function git(cwd: string, args: string[]): Promise<RunResult> {
  return runProcess(["git", ...args], { cwd });
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
