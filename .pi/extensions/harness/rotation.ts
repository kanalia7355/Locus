// rotation.ts — タスクの重みによるモデル選択と、枠枯渇時の自動切替
//
// - 候補列は MODEL_ROTATION-Locus.md の確定表をコード化したもの
// - 枠切れは「モデルの失敗」ではない: リトライせず候補列の次へ進む
// - cooldown は絶対時刻で state に保持し、再起動後も引き継ぐ

import { isCoolingDown, type HarnessState } from "./state";

export type Weight = "heavy" | "medium" | "light";
export type RunnerKind = "agy" | "opencode" | "ollama";
export type Pool = "gemini" | "claude-gpt" | "free" | "local";

export interface Candidate {
  runner: RunnerKind;
  /**
   * agy は表示名 ("Gemini 4 Argon" 等)、opencode は完全な slug
   * ("opencode/big-pickle" 等)、ollama はモデル名。
   * "*opencode-free*" は無料プールのマーカーで、実モデルは
   * pickOpenCodeFree() でカーソル位置から解決する。
   */
  model: string;
  /** agy の effort 目安 (オーケストレーターがプロンプトに添える情報) */
  effort?: "low" | "medium" | "high";
  pool: Pool;
}

/** OpenCode 無料プール (2026-11-12 に `opencode models` で実機確認済み) */
export const OPENCODE_FREE_MODELS: string[] = [
  "opencode/beam-free",
  "opencode/big-pickle",
  "opencode/deepseek-v4.1-flash-free",
  "opencode/flint-40b-free",
  "opencode/glm-5.3-flash-free",
  "opencode/iceman-free",
  "opencode/inkling-2-small-free",
  "opencode/longcat-2.5-free",
  "opencode/mimo-v2.6-flash-free",
  "opencode/minimax-m3.1-flash-free",
  "opencode/nemotron-3.5-lightning-free",
  "opencode/nemotron-3.5-super-vl-free",
];

const FREE_MARKER = "*opencode-free*";

/** 重み別の候補列 (上から順に試す) */
export function candidatesFor(weight: Weight): Candidate[] {
  switch (weight) {
    case "heavy":
      return [
        { runner: "agy", model: "Gemini 4 Argon", effort: "high", pool: "gemini" },
        { runner: "agy", model: "Claude Opus 5.5", pool: "claude-gpt" },
        { runner: "agy", model: "Claude Sonnet 5.5", pool: "claude-gpt" },
      ];
    case "medium":
      return [
        { runner: "agy", model: "Gemini 4 Argon", effort: "medium", pool: "gemini" },
        { runner: "agy", model: "Claude Sonnet 5.5", pool: "claude-gpt" },
        { runner: "opencode", model: FREE_MARKER, pool: "free" },
      ];
    case "light":
      return [
        { runner: "agy", model: "Gemini 3.8 Flash", pool: "gemini" },
        { runner: "agy", model: "Gemini 4 Carbon", pool: "gemini" },
        { runner: "agy", model: "GPT-OSS 120B", pool: "claude-gpt" },
        { runner: "opencode", model: FREE_MARKER, pool: "free" },
        { runner: "ollama", model: "gemma3:4b", pool: "local" },
      ];
  }
}

/** 無料プールのマーカーを、カーソル位置の実モデルへ解決する */
export function resolveFree(
  candidate: Candidate,
  freeCursor: number,
): Candidate {
  if (candidate.model !== FREE_MARKER) return candidate;
  const model =
    OPENCODE_FREE_MODELS[freeCursor % OPENCODE_FREE_MODELS.length];
  return { ...candidate, model };
}

/** cooldown 中のモデル / プールを候補から落とす */
export function filterAvailable(
  candidates: Candidate[],
  state: HarnessState,
  now: Date = new Date(),
): Candidate[] {
  return candidates.filter(
    (c) =>
      !isCoolingDown(state, "model", c.model, now) &&
      !isCoolingDown(state, "pool", c.pool, now),
  );
}

/** 重み→候補列を、cooldown を除いて実モデルまで解決した列で返す */
export function planFor(
  weight: Weight,
  state: HarnessState,
  now: Date = new Date(),
): Candidate[] {
  return filterAvailable(candidatesFor(weight), state, now).map((c) =>
    resolveFree(c, state.freeCursor),
  );
}

const QUOTA_PATTERNS: RegExp[] = [
  /individual quota reached/i,
  /quota (reached|exceeded|exhausted)/i,
  /usage limit/i,
  /rate limit/i,
  /insufficient (balance|quota|credit)/i,
  /no resource package/i,
  /\b429\b/,
];

/** 出力テキストが「枠枯渇」を示しているか */
export function isQuotaError(text: string): boolean {
  return QUOTA_PATTERNS.some((p) => p.test(text));
}

/**
 * agy の "Resets in <duration>" 表記から cooldown 終了時刻を推定する。
 * 読めなければ null (呼び出し側が既定の cooldown を使う)。
 */
export function parseCooldownUntil(
  text: string,
  now: Date = new Date(),
): Date | null {
  const hm = text.match(
    /resets? in\s+(\d+(?:\.\d+)?)\s*h(?:ours?)?\s*(?:(\d+(?:\.\d+)?)\s*m)?/i,
  );
  if (hm) {
    const hours = parseFloat(hm[1]);
    const minutes = hm[2] ? parseFloat(hm[2]) : 0;
    return new Date(now.getTime() + (hours * 60 + minutes) * 60 * 1000);
  }
  const m = text.match(/resets? in\s+(\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?/i);
  if (m) {
    return new Date(now.getTime() + parseFloat(m[1]) * 60 * 1000);
  }
  return null;
}

/** cooldown の既定値: リセット時刻が読めない枠切れ用 (5時間枠に合わせる) */
export const DEFAULT_COOLDOWN_MS = 5 * 60 * 60 * 1000;
