// poll.ts — progress/ の差分検出
//
// 前回ポーリング時のスナップショット (state.json に保存される) と比較し、
// frontmatter の status / updated が変わったファイルだけを返す。
// 依存ライブラリなし (frontmatter は単純な key: value 行だけを読む)。

import * as fs from "node:fs";
import * as path from "node:path";

export interface TaskSnapshot {
  status: string;
  updated: string;
}

/** ファイル相対パス → スナップショット */
export type PollState = Record<string, TaskSnapshot>;

export interface ChangedFile {
  /** progress/ からの相対パス */
  file: string;
  /** undefined = 新規ファイル */
  before?: TaskSnapshot;
  after: TaskSnapshot;
}

/** 先頭の --- ... --- ブロックから key: value を拾う (YAML の単純なスカラーのみ) */
function parseFrontmatter(content: string): Record<string, string> {
  if (!content.startsWith("---")) return {};
  const end = content.indexOf("\n---", 3);
  if (end === -1) return {};
  const result: Record<string, string> = {};
  for (const line of content.slice(3, end).split("\n")) {
    const m = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (m) result[m[1]] = m[2].trim().replace(/^["']|["']$/g, "");
  }
  return result;
}

function listMarkdownFiles(dir: string, base: string): string[] {
  if (!fs.existsSync(dir)) return [];
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listMarkdownFiles(full, base));
    else if (entry.isFile() && entry.name.endsWith(".md")) {
      out.push(path.relative(base, full));
    }
  }
  return out;
}

/** progress/ 配下の全タスクファイルの現在状態を読む */
export function scanProgress(progressDir: string): PollState {
  const state: PollState = {};
  for (const rel of listMarkdownFiles(progressDir, progressDir)) {
    const fm = parseFrontmatter(
      fs.readFileSync(path.join(progressDir, rel), "utf-8"),
    );
    if (fm.status !== undefined || fm.updated !== undefined) {
      state[rel] = { status: fm.status ?? "", updated: fm.updated ?? "" };
    }
  }
  return state;
}

/**
 * 前回スナップショットと比較して差分を返す。
 * 呼び出し側は戻り値の current を state.json に保存し、次回の previous に使う。
 */
export function detectDiff(
  progressDir: string,
  previous: PollState,
): { changed: ChangedFile[]; current: PollState } {
  const current = scanProgress(progressDir);
  const changed: ChangedFile[] = [];
  for (const [file, after] of Object.entries(current)) {
    const before = previous[file];
    if (
      !before ||
      before.status !== after.status ||
      before.updated !== after.updated
    ) {
      changed.push({ file, before, after });
    }
  }
  return { changed, current };
}
