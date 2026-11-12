// runners/agy.ts — Antigravity CLI (agy) ワーカーの起動
//
// 注意: agy の終了コードは信頼できない報告があるため、成否は終了コードではなく
// 成果物ファイルとテスト結果で判定する (呼び出し側の責務)。
// ここでは出力と、枠枯渇の検出・cooldown 終了時刻の推定までを返す。

import { runProcess, type RunResult } from "./exec";
import { isQuotaError, parseCooldownUntil } from "../rotation";

export interface AgyResult extends RunResult {
  quota: boolean;
  /** "Resets in ..." から推定した cooldown 終了時刻。読めなければ null */
  cooldownUntil: Date | null;
}

export async function runAgy(opts: {
  /** 表示名で指定する ("Gemini 4 Argon" 等) */
  model: string;
  prompt: string;
  cwd: string;
  printTimeout: string;
  timeoutMs?: number;
}): Promise<AgyResult> {
  const result = await runProcess(
    [
      "agy",
      "-p",
      opts.prompt,
      "--model",
      opts.model,
      "--dangerously-skip-permissions",
      "--print-timeout",
      opts.printTimeout,
    ],
    { cwd: opts.cwd, timeoutMs: opts.timeoutMs },
  );
  const text = `${result.stdout}\n${result.stderr}`;
  const quota = isQuotaError(text);
  return {
    ...result,
    quota,
    cooldownUntil: quota ? parseCooldownUntil(text) : null,
  };
}
