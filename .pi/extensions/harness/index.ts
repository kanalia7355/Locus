// index.ts — pi extension のエントリポイント
//
// pi ホスト API との接点はこのファイルだけに閉じ込める。
// ロジック本体 (poll / state / rotation / runners / git / testscope) は
// ホストに依存しない純粋なモジュールなので、単体で検証できる。
//
// サイクル:
//   30分ごとに progress/ をポーリング → 差分があれば Luna (Codex) を起動し、
//   orchestrator.md の指示に従って割当・状態遷移・QA をファイル経由で行わせる。
//   ワーカーの起動は Luna の割当結果を受けて runners が担う (将来の拡張点。
//   現段階ではポーリングと Luna 起動までを自動化し、結果は state に記録する)。

import * as fs from "node:fs";
import * as path from "node:path";
import { DEFAULT_CONFIG, type HarnessConfig } from "./config";
import { loadState, saveState } from "./state";
import { detectDiff } from "./poll";
import { runLuna } from "./runners/codex";

/** pi の ExtensionAPI のうち、このハーネスが使う最小限の形 */
interface PiContext {
  cwd: string;
  ui?: { notify?: (message: string, level?: string) => void };
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
  note: string;
}

export async function runPollCycle(
  repoRoot: string,
  config: HarnessConfig = DEFAULT_CONFIG,
): Promise<PollCycleResult> {
  const stateFile = path.join(repoRoot, config.stateFile);
  const progressDir = path.join(repoRoot, config.progressDir);
  const state = loadState(stateFile);
  state.lastPollAt = new Date().toISOString();

  const { changed, current } = detectDiff(
    progressDir,
    state.progressSnapshot,
  );

  if (changed.length === 0) {
    state.lastCycleNote = "no changes";
    saveState(stateFile, state);
    return { changedCount: 0, lunaStarted: false, note: state.lastCycleNote };
  }

  const promptFile = path.join(
    repoRoot,
    config.promptsDir,
    "orchestrator.md",
  );
  if (!fs.existsSync(promptFile)) {
    // プロンプトが無い間はスナップショットを進めない (次サイクルで再試行する)
    state.lastCycleNote = `changed ${changed.length} file(s) but orchestrator prompt is missing: ${promptFile}`;
    saveState(stateFile, state);
    return { changedCount: changed.length, lunaStarted: false, note: state.lastCycleNote };
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

  const luna = await runLuna({
    prompt,
    cwd: repoRoot,
    model: config.lunaModel,
    timeoutMs: config.processTimeoutMs,
  });

  if (luna.quota) {
    // Luna 側の枠切れ: スナップショットは進めず、次サイクルで再試行する
    state.lastCycleNote = "Luna quota exhausted; will retry next cycle";
    saveState(stateFile, state);
    return { changedCount: changed.length, lunaStarted: true, note: state.lastCycleNote };
  }

  // Luna が処理したのでスナップショットを進める
  state.progressSnapshot = current;
  state.lastCycleNote = `Luna processed ${changed.length} changed file(s)`;
  saveState(stateFile, state);
  return { changedCount: changed.length, lunaStarted: true, note: state.lastCycleNote };
}

export default function harness(pi: PiExtensionApi): void {
  const config = DEFAULT_CONFIG;
  let timer: ReturnType<typeof setInterval> | null = null;
  let running = false;

  const cycle = async (ctx: PiContext) => {
    if (running) return; // サイクルの重なりを防ぐ
    running = true;
    try {
      const result = await runPollCycle(ctx.cwd, config);
      if (result.changedCount > 0) {
        ctx.ui?.notify?.(`harness: ${result.note}`, "info");
      }
    } catch (err) {
      ctx.ui?.notify?.(
        `harness: poll cycle failed: ${err instanceof Error ? err.message : String(err)}`,
        "error",
      );
    } finally {
      running = false;
    }
  };

  pi.on("session_start", (_event, ctx) => {
    if (timer) clearInterval(timer);
    timer = setInterval(() => {
      void cycle(ctx);
    }, config.pollIntervalMs);
  });

  pi.on("session_shutdown", () => {
    if (timer) clearInterval(timer);
    timer = null;
  });

  pi.registerCommand("harness-poll", {
    description: "Run one harness poll cycle now",
    handler: async (_args, ctx) => {
      await cycle(ctx);
    },
  });
}
