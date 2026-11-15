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
  // 注意: codex exec に --full-auto は無い (対話モード側のフラグ)。
  // exec は非対話で承認を求めず、触れる範囲は --sandbox で決まる。
  // プロンプトは引数で渡さない: Windows の npm シム経由だと空白・改行で割れて
  // 化ける (実証済み)。`codex exec -` で stdin から全文を読むのが公式の形。
  const result = await runProcess(
    [
      "codex",
      "exec",
      "--model",
      opts.model,
      "--sandbox",
      "workspace-write",
      "-",
    ],
    { cwd: opts.cwd, timeoutMs: opts.timeoutMs, input: opts.prompt },
  );
  return {
    ...result,
    // 正常終了した実行の要約文に "usage limit" 等の語が混ざっても誤判定しないよう、
    // quota 判定は異常終了のときに限る
    quota: result.code !== 0 && isQuotaError(`${result.stdout}\n${result.stderr}`),
  };
}
