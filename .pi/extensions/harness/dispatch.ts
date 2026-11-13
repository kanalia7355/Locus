// dispatch.ts — Luna の割当結果を受けてワーカーを自動起動する (TODO-02)
//
// ポリシー (ドライランで検証された運用に合わせた v1):
// - 1 サイクルで起動するワーカーは最大1つ (逐次実行が前提の設計)
// - 起動対象は「Luna が割り当てたのに、まだ誰も動いていない」タスクだけ:
//   - 実装: status=doing かつ frontmatter に assignee / model がある
//   - レビュー: status=review かつ REVIEW 欄に Reviewer 割当があり、判定が未記入
// - 二重起動防止: 起動前に state.dispatchLog へ (file, stage, 起動時点の内容
//   ハッシュ) を記録する。同じ内容に対しては再起動しない (ワーカーが何も
//   変えなかった場合も含む)。Luna がファイルに触れて内容が変われば再び対象になる
// - 作業場所はメイン checkout (ドライランの形)。worktree 分離は次段階

import * as fs from "node:fs";
import * as path from "node:path";
import { createHash } from "node:crypto";
import { listMarkdownFiles, parseFrontmatter } from "./poll";
import type { HarnessState } from "./state";
import { runAgy } from "./runners/agy";
import { runOpenCode } from "./runners/opencode";

export type DispatchStage = "implement" | "review";

export interface DispatchTarget {
  /** progress/ からの相対パス */
  file: string;
  stage: DispatchStage;
  /** "agy" | "opencode" */
  runner: string;
  /** agy は基本名 ("Claude Sonnet 5.5")、opencode は slug */
  model: string;
  /** 起動時点のファイル内容ハッシュ */
  hash: string;
}

export interface DispatchOutcome {
  target: DispatchTarget;
  /** ワーカーの終了コードが 0 だったか (agy では参考値。本当の成否は fileChanged) */
  processOk: boolean;
  quota: boolean;
  /** ワーカーがタスクファイルに変化を起こしたか */
  fileChanged: boolean;
  /** 実行後の status (読めなければ null) */
  newStatus: string | null;
  note: string;
}

function hashContent(raw: string): string {
  return createHash("sha256").update(raw).digest("hex").slice(0, 16);
}

/** `## 見出し` セクションの本文を返す (次の `## ` 見出しまで)。無ければ "" */
export function sectionBody(content: string, heading: string): string {
  const lines = content.split("\n");
  const start = lines.findIndex((l) => l.trim() === `## ${heading}`);
  if (start === -1) return "";
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((l) => /^##\s/.test(l));
  return (end === -1 ? rest : rest.slice(0, end)).join("\n");
}

/**
 * REVIEW 欄のレビュアー割当行から runner / model を読む。
 * Luna の表記は揺れるので、複数形式に対応する:
 *   "- **Reviewer 割当**: `agy` / `Claude Sonnet 5.5`"
 *   "- **Assigned Reviewer**: `agy` / `Gemini 4 Carbon` (補足...)"
 * レビュアーに言及した行に限り、`runner` / model の形を探す。
 */
export function parseReviewerAssignment(
  content: string,
): { runner: string; model: string } | null {
  const review = sectionBody(content, "REVIEW");
  for (const line of review.split("\n")) {
    if (!/reviewer|レビュアー|割当/i.test(line)) continue;
    const both = line.match(/`([^`]+)`\s*\/\s*`([^`]+)`/);
    if (both) return { runner: both[1].trim(), model: both[2].trim() };
    const bare = line.match(/`([^`]+)`\s*\/\s*([^\n(（]+)/);
    if (bare) {
      const model = bare[2].replace(/`/g, "").replace(/[。\s]+$/, "").trim();
      if (model) return { runner: bare[1].trim(), model };
    }
  }
  return null;
}

/** frontmatter の reviewer 指定 ("agy/Claude Sonnet 5.5") を読む */
export function parseFrontmatterReviewer(
  fm: Record<string, string>,
): { runner: string; model: string } | null {
  const raw = fm.reviewer?.trim();
  if (!raw) return null;
  const idx = raw.indexOf("/");
  if (idx === -1) return null;
  const runner = raw.slice(0, idx).trim();
  const model = raw.slice(idx + 1).trim();
  return runner && model ? { runner, model } : null;
}

/** REVIEW 欄に判定 (承認 / 差し戻し) が既に記入されているか */
export function reviewVerdictPresent(content: string): boolean {
  const review = sectionBody(content, "REVIEW");
  // QA 差し戻し (## QA Return) が記録されるたびに、それ以前のレビュー判定は
  // 「旧リビジョンへの判定」として失効する (Luna の再 QA 要件: 変更分への
  // 新規レビューが必要)。判定の件数が差し戻し回数を上回る場合のみ、
  // 現リビジョンへの判定があるとみなす
  const qaReturns = (content.match(/^##\s*QA Return/gm) ?? []).length;
  if (qaReturns === 0) return /APPROVED|CHANGES\s+REQUESTED/i.test(review);
  const verdicts = (
    review.match(/Verdict\*\*:?\s*(APPROVED|CHANGES\s+REQUESTED)/gi) ?? []
  ).length;
  return verdicts > qaReturns;
}

/** REPORT 欄の Changed Files から変更ファイルのパス一覧を読む (コミット用) */
export function parseChangedFiles(content: string): string[] {
  const report = sectionBody(content, "REPORT");
  if (!report) return [];
  const marker = report.match(/Changed Files\*\*:\s*\n([\s\S]*?)(?:\n\s*-\s*\*\*|$)/);
  const block = marker ? marker[1] : report;
  const paths = new Set<string>();
  for (const mm of block.matchAll(/`([^`]+)`/g)) {
    const p = mm[1].trim().replace(/\\/g, "/");
    if (p.includes("/") && !p.includes(" ") && !p.startsWith("http")) {
      paths.add(p);
    }
  }
  return [...paths];
}

/** 起動すべきワーカーを1つ探す。無ければ null */
export function findDispatchTarget(
  progressDir: string,
  state: HarnessState,
): DispatchTarget | null {
  const targets: DispatchTarget[] = [];
  for (const rel of listMarkdownFiles(progressDir, progressDir).sort()) {
    if (rel.split(/[\\/]/).includes("_template")) continue;
    let raw: string;
    try {
      raw = fs.readFileSync(path.join(progressDir, rel), "utf-8");
    } catch {
      continue;
    }
    const fm = parseFrontmatter(raw);
    if (!fm.id || !fm.status) continue; // タスクファイルだけが対象
    const hash = hashContent(raw);
    const logged = state.dispatchLog[rel];
    if (logged && logged.hash === hash) continue; // 同じ内容には再起動しない

    if (fm.status === "doing" && fm.assignee && fm.model) {
      targets.push({
        file: rel,
        stage: "implement",
        runner: fm.assignee,
        model: fm.model,
        hash,
      });
    } else if (fm.status === "review" && !reviewVerdictPresent(raw)) {
      // frontmatter の reviewer 指定を優先し、無ければ REVIEW 欄の割当行を読む
      const assignment =
        parseFrontmatterReviewer(fm) ?? parseReviewerAssignment(raw);
      if (assignment) {
        targets.push({
          file: rel,
          stage: "review",
          runner: assignment.runner,
          model: assignment.model,
          hash,
        });
      }
    }
  }
  // 実装を優先し、無ければレビュー
  return targets.find((t) => t.stage === "implement") ?? targets[0] ?? null;
}

/** ワーカーを起動し、タスクファイルの変化で結果を判定する */
export async function runDispatch(
  target: DispatchTarget,
  opts: {
    repoRoot: string;
    /** repo ルートからの相対パス (progress / prompts の置き場) */
    progressDir: string;
    promptsDir: string;
    agyPrintTimeout: string;
    timeoutMs?: number;
  },
): Promise<DispatchOutcome> {
  const taskRel = `${opts.progressDir}/${target.file.replace(/\\/g, "/")}`;
  const instruction =
    target.stage === "implement"
      ? `${opts.promptsDir}/implementer.md の指示に従い、タスク ${taskRel} を実装せよ。完了したら PROTOCOL 通りにタスクファイルの REPORT と status を更新すること。`
      : `${opts.promptsDir}/reviewer.md の指示に従い、タスク ${taskRel} をレビューせよ。対象の変更ファイルはタスクファイルの REPORT 欄に記載されている。完了したら PROTOCOL 通りにタスクファイルの REVIEW 欄と status を更新すること。`;

  // 指示はファイル経由で渡し、引数のプロンプトは短いポインタだけにする
  // (このハーネスの通信は Markdown ファイル経由が原則。長い日本語文を
  // コマンドライン引数で渡すと、シェル経由で化ける事故が起きたため)。
  // 書き込みに失敗した場合は従来通り全文を引数で渡す。
  let prompt = instruction;
  try {
    const promptFile = path.join(
      opts.repoRoot,
      ".pi",
      "harness",
      "dispatch-prompt.md",
    );
    fs.mkdirSync(path.dirname(promptFile), { recursive: true });
    fs.writeFileSync(promptFile, instruction, "utf-8");
    prompt =
      "指示ファイル .pi/harness/dispatch-prompt.md を読み、その内容に従って作業せよ。";
  } catch {
    // フォールバック: prompt は全文のまま
  }

  let processOk = false;
  let quota = false;
  let processCode: number | null = null;
  let outputTail = "";
  if (target.runner === "agy") {
    const r = await runAgy({
      model: target.model,
      prompt,
      cwd: opts.repoRoot,
      printTimeout: opts.agyPrintTimeout,
      timeoutMs: opts.timeoutMs,
    });
    processOk = r.code === 0;
    quota = r.quota;
    processCode = r.code;
    outputTail = `${r.stderr}\n${r.stdout}`.trim().slice(-300);
  } else if (target.runner === "opencode") {
    const r = await runOpenCode({
      model: target.model,
      prompt,
      cwd: opts.repoRoot,
      timeoutMs: opts.timeoutMs,
    });
    processOk = r.code === 0;
    quota = r.quota;
    processCode = r.code;
    outputTail = `${r.stderr}\n${r.stdout}`.trim().slice(-300);
  } else {
    return {
      target,
      processOk: false,
      quota: false,
      fileChanged: false,
      newStatus: null,
      note: `dispatch skipped for ${target.file}: unknown runner "${target.runner}"`,
    };
  }

  // 成否は終了コードではなく、タスクファイルがどう変わったかで見る
  let newStatus: string | null = null;
  let fileChanged = false;
  try {
    const rawAfter = fs.readFileSync(
      path.join(opts.repoRoot, taskRel),
      "utf-8",
    );
    fileChanged = hashContent(rawAfter) !== target.hash;
    newStatus = parseFrontmatter(rawAfter).status ?? null;
  } catch {
    // ファイルが読めない場合は変化なしとして扱う (note に残る)
  }

  // ファイルが変わらなかったときは、ワーカーの終了コードと出力末尾を証跡として残す
  // (黙って失敗されると切り分けができないため)
  const note = quota
    ? `dispatched ${target.stage} for ${target.file} (${target.runner}/${target.model}): quota hit: ${outputTail}`
    : `dispatched ${target.stage} for ${target.file} (${target.runner}/${target.model}): ${
        fileChanged
          ? `file updated, status -> ${newStatus ?? "?"}`
          : `no file change (code=${processCode}): ${outputTail}`
      }`;
  return { target, processOk, quota, fileChanged, newStatus, note };
}
