// runners/opencode.ts — OpenCode ワーカーの起動
//
// 無料モデルは完全な slug ("opencode/big-pickle" 等) で指定する。
// ローカルモデル (ollama/gemma3:4b) も同じ経路で呼べる。

import { runProcess, type RunResult } from "./exec";
import { isQuotaError, parseCooldownUntil } from "../rotation";

export interface OpenCodeResult extends RunResult {
  quota: boolean;
  cooldownUntil: Date | null;
}

export async function runOpenCode(opts: {
  model: string;
  prompt: string;
  cwd: string;
  timeoutMs?: number;
}): Promise<OpenCodeResult> {
  const result = await runProcess(
    ["opencode", "run", "--model", opts.model, "--auto", opts.prompt],
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
