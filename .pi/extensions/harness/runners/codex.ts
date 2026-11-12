// runners/codex.ts — オーケストレーター (Codex / Luna) の起動
//
// Luna の仕事は判断とファイル更新 (タスク割当・状態遷移・QA 照合) だけ。
// 実装はさせない。前提は .pi/harness/prompts/orchestrator.md を参照。

import { runProcess, type RunResult } from "./exec";
import { isQuotaError } from "../rotation";

export interface LunaResult extends RunResult {
  quota: boolean;
}

export async function runLuna(opts: {
  prompt: string;
  cwd: string;
  model: string;
  timeoutMs?: number;
}): Promise<LunaResult> {
  const result = await runProcess(
    [
      "codex",
      "exec",
      "--model",
      opts.model,
      "--sandbox",
      "workspace-write",
      "--full-auto",
      opts.prompt,
    ],
    { cwd: opts.cwd, timeoutMs: opts.timeoutMs },
  );
  return {
    ...result,
    quota: isQuotaError(`${result.stdout}\n${result.stderr}`),
  };
}
