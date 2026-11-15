// index.ts — pi extension のエントリポイント
//
// pi ホスト API との接点はこのファイルだけに閉じ込める。
// ロジック本体 (poll / state / rotation / runners / git / testscope) は
// ホストに依存しない純粋なモジュールなので、単体で検証できる。
//
// サイクル:
//   ポーリング間隔ごとに progress/ をポーリング → 差分があれば Luna (Codex) を起動し、
//   orchestrator.md の指示に従って割当・状態遷移・QA をファイル経由で行わせる。
//   Luna の割当結果を受けて、未起動のワーカーを最大1つ自動起動する (dispatch)。
//   タスクが done に遷移したら、そのサイクルの成果物をコミットする。
//   ワーカーの報告は次サイクルの差分として Luna が拾い、ループが進む。

import * as fs from "node:fs";
import * as path from "node:path";
import { DEFAULT_CONFIG, type HarnessConfig } from "./config";
import { loadState, saveState, pushCycleNote } from "./state";
import { detectDiff, parseFrontmatter, readTextSmart } from "./poll";
import { runLuna } from "./runners/codex";
import {
  findDispatchTarget,
  parseChangedFiles,
  runDispatch,
} from "./dispatch";
import {
  commitPaths,
  hasUncommitted,
  currentBranch,
  unpushedCount,
  pushCurrentBranch,
} from "./git";
import { formatStatus, formatElapsed } from "./status";

/** pi の ExtensionAPI のうち、このハーネスが使う最小限の形 */
interface PiContext {
  cwd: string;
  ui?: {
    notify?: (message: string, level?: string) => void;
    setStatus?: (key: string, text?: string) => void;
  };
}

/** サイクル内の段階変化をホスト (フッター表示) へ伝えるためのフック */
export interface CycleHooks {
  onStage?: (label: string | null) => void;
}

interface PiExtensionApi {
  on(
    event: string,
    handler: (event: unknown, ctx: PiContext) => unknown,
  ): void;
  registerCommand(
    name: string,
    opts: {
      description?: string;
      handler: (args: string, ctx: PiContext) => unknown;
    },
  ): void;
}

export interface PollCycleResult {
  changedCount: number;
  lunaStarted: boolean;
  dispatched: string | null;
  note: string;
}

export async function runPollCycle(
  repoRoot: string,
  config: HarnessConfig = DEFAULT_CONFIG,
  hooks: CycleHooks = {},
): Promise<PollCycleResult> {
  const stateFile = path.join(repoRoot, config.stateFile);
  const progressDir = path.join(repoRoot, config.progressDir);
  const state = loadState(stateFile);
  state.lastPollAt = new Date().toISOString();

  const notes: string[] = [];
  let lunaStarted = false;

  const { changed, current } = detectDiff(
    progressDir,
    state.progressSnapshot,
  );

  // ---- Luna フェーズ (差分があるときだけ) ----
  if (changed.length > 0) {
    const promptFile = path.join(
      repoRoot,
      config.promptsDir,
      "orchestrator.md",
    );
    if (!fs.existsSync(promptFile)) {
      // プロンプトが無い間はスナップショットを進めない (次サイクルで再試行する)
      pushCycleNote(
        state,
        `changed ${changed.length} file(s) but orchestrator prompt is missing: ${promptFile}`,
      );
      saveState(stateFile, state);
      return {
        changedCount: changed.length,
        lunaStarted: false,
        dispatched: null,
        note: state.lastCycleNote,
      };
    }

    const orchestratorPrompt = fs.readFileSync(promptFile, "utf-8");
    const diffSummary = changed
      .map(
        (c) =>
          `- ${c.file}: ${c.before ? `${c.before.status} -> ` : "(new) "}${c.after.status} (updated: ${c.after.updated})`,
      )
      .join("\n");
    const prompt = [
      orchestratorPrompt,
      "",
      "## 今回のポーリング差分",
      diffSummary,
      "",
      "上記の変化に対して、PROTOCOL に従い割当・状態遷移・QA をファイル経由で行うこと。",
    ].join("\n");

    hooks.onStage?.(`Luna 処理中 (差分 ${changed.length} 件)`);
    const luna = await runLuna({
      prompt,
      cwd: repoRoot,
      model: config.lunaModel,
      timeoutMs: config.processTimeoutMs,
    });
    lunaStarted = true;

    if (luna.quota) {
      // Luna 側の枠切れ: スナップショットは進めず、次サイクルで再試行する。
      // 判定根拠 (codex の出力末尾) を証跡として残す — 本物の枠切れか誤判定か切り分けるため
      const tail = `${luna.stderr}\n${luna.stdout}`.trim().slice(-300);
      pushCycleNote(state, `Luna quota exhausted; will retry next cycle: ${tail}`);
      saveState(stateFile, state);
      return {
        changedCount: changed.length,
        lunaStarted: true,
        dispatched: null,
        note: state.lastCycleNote,
      };
    }

    if (luna.code !== 0) {
      // Luna の起動失敗 (モデル ID の誤り等): スナップショットは進めず、
      // 出力の末尾を証跡として残す。失敗を「処理済み」として握りつぶさない
      const tail = `${luna.stderr}\n${luna.stdout}`.trim().slice(-300);
      pushCycleNote(
        state,
        `Luna failed (code=${luna.code}, timedOut=${luna.timedOut}): ${tail}`,
      );
      saveState(stateFile, state);
      return {
        changedCount: changed.length,
        lunaStarted: true,
        dispatched: null,
        note: state.lastCycleNote,
      };
    }

    // Luna が正常終了したのでスナップショットを進める。
    // ただし「読めなくなった」ファイルの記録は前回のものを残す:
    // 落としてしまうと、そのファイルは二度と差分として上がってこない
    const nextSnapshot = { ...current };
    for (const c of changed) {
      if (c.after.status === "(missing-or-unreadable)" && c.before) {
        nextSnapshot[c.file] = c.before;
      }
    }
    state.progressSnapshot = nextSnapshot;
    notes.push(`Luna processed ${changed.length} changed file(s)`);

  }

  // ---- コミットフェーズ: done になったタスクの成果物をコミットする ----
  // このサイクルで done に遷移したタスクに加え、done なのに成果物が
  // 未コミットのまま残っているタスクも拾う (自己回復): コミット失敗で
  // スナップショットだけが進んだ場合や、コミット配線が無かった頃に
  // done になったタスクを取りこぼさないため。差分ゼロのサイクルでも実行する
  if (config.commitOnDone) {
    const candidateFiles = new Set<string>(
      changed
        .filter((c) => c.after.status === "done" && c.before?.status !== "done")
        .map((c) => c.file),
    );
    for (const rel of Object.keys(current)) {
      if (current[rel]?.status !== "done" || candidateFiles.has(rel)) continue;
      if (!rel.replace(/\\/g, "/").includes("/tasks/")) continue;
      try {
        const content = readTextSmart(path.join(progressDir, rel));
        const deliverables = parseChangedFiles(content);
        const taskPath = `${config.progressDir}/${rel.replace(/\\/g, "/")}`;
        if (await hasUncommitted(repoRoot, [...deliverables, taskPath])) {
          candidateFiles.add(rel);
        }
      } catch {
        // 読めないファイルは対象外
      }
    }
    let anyCommitted = false;
    for (const file of candidateFiles) {
      try {
        const content = readTextSmart(path.join(progressDir, file));
        const fm = parseFrontmatter(content);
        const label = fm.id ?? file;
        const paths = new Set<string>(parseChangedFiles(content));
        // タスクファイル自身と、フェーズの PROGRESS.md も一緒にコミットする
        paths.add(`${config.progressDir}/${file.replace(/\\/g, "/")}`);
        const parts = file.replace(/\\/g, "/").split("/");
        if (parts.length >= 2) {
          paths.add(`${config.progressDir}/${parts[0]}/PROGRESS.md`);
        }
        const result = await commitPaths(
          repoRoot,
          [...paths],
          `feat: complete ${label} (implementation, review, QA)`,
        );
        const skippedNote = result.skipped.length
          ? ` (skipped missing: ${result.skipped.join(", ")})`
          : "";
        if (result.committed) anyCommitted = true;
        notes.push(
          result.committed
            ? `committed cycle for ${label}${skippedNote}`
            : `nothing to commit for ${label}${skippedNote}`,
        );
      } catch (err) {
        notes.push(
          `commit failed for ${file}: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }

    // ---- push: コミットを GitHub (origin) へ同期する ----
    // このサイクルで新規コミットが無くても、未 push 分が残っていれば送る
    // (push 失敗や配線前のコミットを取りこぼさないための自己回復)
    if (config.pushOnCommit) {
      try {
        const branch = await currentBranch(repoRoot);
        const ahead =
          branch && branch !== "HEAD"
            ? await unpushedCount(repoRoot, branch)
            : 0;
        if (anyCommitted || ahead !== 0) {
          const res = await pushCurrentBranch(repoRoot);
          if (res.pushed) notes.push(`pushed to origin/${res.branch}`);
        }
      } catch (err) {
        notes.push(
          `push failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
  }

  // ---- dispatch フェーズ: Luna の割当を受けて未起動のワーカーを最大1つ起動する ----
  // 差分が無いサイクルでも、未起動の割当が残っていれば拾う
  let dispatched: string | null = null;
  if (config.dispatchEnabled) {
    const target = findDispatchTarget(progressDir, state);
    if (target) {
      // 起動前に記録する (起動中の異常終了でも二重起動しないための先行記録)
      state.dispatchLog[target.file] = {
        stage: target.stage,
        hash: target.hash,
        at: new Date().toISOString(),
      };
      try {
        const taskLabel = path.basename(target.file).replace(/\.md$/i, "");
        hooks.onStage?.(
          `${target.stage === "implement" ? "実装中" : "レビュー中"} ${taskLabel} (${target.runner}/${target.model})`,
        );
        const outcome = await runDispatch(target, {
          repoRoot,
          progressDir: config.progressDir,
          promptsDir: config.promptsDir,
          agyPrintTimeout: config.agyPrintTimeout,
          timeoutMs: config.processTimeoutMs,
        });
        dispatched = outcome.note;
        notes.push(outcome.note);
      } catch (err) {
        notes.push(
          `dispatch failed for ${target.file}: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
  }

  if (notes.length === 0) notes.push("no changes");
  pushCycleNote(state, notes.join(" | "));
  saveState(stateFile, state);
  return {
    changedCount: changed.length,
    lunaStarted,
    dispatched,
    note: state.lastCycleNote,
  };
}

export default function harness(pi: PiExtensionApi): void {
  const config = DEFAULT_CONFIG;
  let timer: ReturnType<typeof setInterval> | null = null;
  let running = false;

  // ---- 可視化: フッターに「今何が起きているか」を常時表示する ----
  let activity: { label: string; since: number } | null = null;
  let nextPollAt: number | null = null;
  let footerTimer: ReturnType<typeof setInterval> | null = null;
  let lastCtx: PiContext | null = null;

  const renderFooter = () => {
    const ctx = lastCtx;
    if (!ctx?.ui?.setStatus) return;
    if (activity) {
      const elapsed = formatElapsed(Date.now() - activity.since);
      ctx.ui.setStatus("harness", `⏳ harness: ${activity.label} · 経過 ${elapsed}`);
    } else if (nextPollAt) {
      const d = new Date(nextPollAt);
      const p = (n: number) => String(n).padStart(2, "0");
      const remain = formatElapsed(Math.max(0, nextPollAt - Date.now()));
      ctx.ui.setStatus(
        "harness",
        `harness: 待機中 · 次回ポーリングまで あと ${remain} (${p(d.getHours())}:${p(d.getMinutes())})`,
      );
    } else {
      ctx.ui.setStatus("harness", "harness: 待機中");
    }
  };

  const setActivity = (label: string | null) => {
    activity = label ? { label, since: Date.now() } : null;
    renderFooter();
  };

  const cycle = async (ctx: PiContext, verbose: boolean) => {
    if (running) return; // サイクルの重なりを防ぐ
    running = true;
    lastCtx = ctx;
    try {
      const result = await runPollCycle(ctx.cwd, config, {
        onStage: (label) => setActivity(label),
      });
      // 手動実行時は結果を必ず表示する。タイマー実行時は差分・dispatch・失敗だけ
      const notable =
        result.changedCount > 0 ||
        result.dispatched !== null ||
        result.note.includes("failed") ||
        result.note.includes("quota") ||
        result.note.includes("missing") ||
        result.note.includes("committed") ||
        result.note.includes("pushed");
      if (verbose || notable) {
        ctx.ui?.notify?.(`harness: ${result.note}`, "info");
      }
    } catch (err) {
      ctx.ui?.notify?.(
        `harness: poll cycle failed: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    } finally {
      running = false;
      nextPollAt = Date.now() + config.pollIntervalMs;
      setActivity(null);
    }
  };

  pi.on("session_start", (_event, ctx) => {
    lastCtx = ctx;
    if (timer) clearInterval(timer);
    nextPollAt = Date.now() + config.pollIntervalMs;
    timer = setInterval(() => {
      void cycle(ctx, false);
    }, config.pollIntervalMs);
    if (footerTimer) clearInterval(footerTimer);
    footerTimer = setInterval(renderFooter, 10 * 1000);
    renderFooter();
  });

  pi.on("session_shutdown", (_event, ctx) => {
    if (timer) clearInterval(timer);
    timer = null;
    if (footerTimer) clearInterval(footerTimer);
    footerTimer = null;
    ctx.ui?.setStatus?.("harness", undefined);
  });

  pi.registerCommand("harness-poll", {
    description: "Run one harness poll cycle now",
    handler: async (_args, ctx) => {
      await cycle(ctx, true);
    },
  });

  pi.registerCommand("harness-status", {
    description: "Show the harness loop status (tasks, activity, cooldowns)",
    handler: async (_args, ctx) => {
      lastCtx = ctx;
      const state = loadState(path.join(ctx.cwd, config.stateFile));
      const text = formatStatus(
        path.join(ctx.cwd, config.progressDir),
        state,
        {
          activity: activity?.label ?? null,
          activitySince: activity ? new Date(activity.since) : null,
          nextPollAt: nextPollAt ? new Date(nextPollAt) : null,
        },
      );
      ctx.ui?.notify?.(text, "info");
    },
  });
}
