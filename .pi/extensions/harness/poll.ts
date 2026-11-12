// poll.ts — progress/ の差分検出
//
// 前回ポーリング時のスナップショット (state.json に保存される) と比較し、
// 内容が変わったファイルだけを返す。判定は frontmatter の status / updated に
// 加えてファイル内容のハッシュでも行う (本文だけの編集や、frontmatter の
// 値を元に戻すような書き換えでも見落とさないため)。
// スナップショットにあるのに読めなくなったファイルも「差分」として上げる
// (文字コードが化ける等で黙って見えなくなる事故を防ぐ)。
// 依存ライブラリなし (frontmatter は単純な key: value 行だけを読む)。

import * as fs from "node:fs";
import * as path from "node:path";
import { createHash } from "node:crypto";

export interface TaskSnapshot {
  status: string;
  updated: string;
  /** ファイル内容の sha256 先頭16桁。旧スナップショットには無い場合がある */
  hash?: string;
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
function parseFrontmatter(raw: string): Record<string, string> {
  // BOM が付いていても読めるようにする (Windows のエディタ/コマンドが付けがち)
  const content = raw.replace(/^\uFEFF/, "");
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
    const raw = fs.readFileSync(path.join(progressDir, rel), "utf-8");
    const fm = parseFrontmatter(raw);
    if (fm.status !== undefined || fm.updated !== undefined) {
      state[rel] = {
        status: fm.status ?? "",
        updated: fm.updated ?? "",
        hash: createHash("sha256").update(raw).digest("hex").slice(0, 16),
      };
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
      before.updated !== after.updated ||
      before.hash !== after.hash
    ) {
      changed.push({ file, before, after });
    }
  }
  // 前回読めたのに今回読めないファイル (削除・文字コード化け等) も差分として上げる。
  // 黙って見えなくなるより、Luna と人間に知らせる方が安全。
  for (const [file, before] of Object.entries(previous)) {
    if (!(file in current)) {
      changed.push({
        file,
        before,
        after: { status: "(missing-or-unreadable)", updated: "", hash: "" },
      });
    }
  }
  return { changed, current };
}
