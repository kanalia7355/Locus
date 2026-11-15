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
  /** モデルの基本名で指定する ("Gemini 4 Argon" 等) */
  model: string;
  /** effort。--model の正式名は "Name (Medium)" 形式で effort 込み (実機確認済み) */
  effort?: "low" | "medium" | "high";
  prompt: string;
  cwd: string;
  printTimeout: string;
  timeoutMs?: number;
}): Promise<AgyResult> {
  // agy headless の --model は effort サフィックス込みの表示名でないと認識されない
  // (例: "Claude Sonnet 5.5 (Medium)")。effort 未指定時は Medium を補う。
  // 注意: Gemini 4 Carbon は headless の Available models 一覧に無い (2026-11-12 実機確認)。
  // 候補に含める場合は、実行時エラーを「そのモデルは使えない」として次候補へ進むこと。
  const cap = (e: string) => e.charAt(0).toUpperCase() + e.slice(1);
  const display = opts.model.includes("(")
    ? opts.model
    : `${opts.model} (${cap(opts.effort ?? "medium")})`;
  const result = await runProcess(
    [
      "agy",
      "-p",
      opts.prompt,
      "--model",
      display,
      "--dangerously-skip-permissions",
      "--print-timeout",
      opts.printTimeout,
    ],
    // agy はネイティブ exe なのでシェルを経由しない (cmd.exe 越しだと
    // 日本語プロンプトが化けてワーカーが無言で終わる。手動実行との差分で実証済み)
    { cwd: opts.cwd, timeoutMs: opts.timeoutMs, shell: false },
  );
  const text = `${result.stdout}\n${result.stderr}`;
  const quota = isQuotaError(text);
  return {
    ...result,
    quota,
    cooldownUntil: quota ? parseCooldownUntil(text) : null,
  };
}
