// state.ts — ハーネスの状態 (.pi/harness/state.json) の読み書き
//
// 状態はプロセスを跨いで保持する: 最終ポーリング時刻、progress/ の
// スナップショット、モデルの cooldown、OpenCode 無料プールのカーソル。
// 壊れた JSON や欠けたフィールドがあっても既定値で復旧する (落とさない)。

import * as fs from "node:fs";
import * as path from "node:path";
import type { PollState } from "./poll";

export interface Cooldown {
  scope: "model" | "pool";
  /** モデル表示名 / slug、またはプール名 ("gemini" | "claude-gpt" | "free") */
  id: string;
  /** ISO 8601。この時刻まで候補から除外する */
  until: string;
  reason: string;
}

export interface HarnessState {
  version: 1;
  lastPollAt: string | null;
  progressSnapshot: PollState;
  cooldowns: Cooldown[];
  /** OpenCode 無料プールのローテーションカーソル */
  freeCursor: number;
  /** 直近サイクルの要約 (人間と Luna が状況を掴むためのメモ) */
  lastCycleNote: string;
  /** 直近のサイクル履歴 (新しい順、最大10件)。失敗の痕跡を上書きで消さないため */
  cycleLog: Array<{ at: string; note: string }>;
}

export function defaultState(): HarnessState {
  return {
    version: 1,
    lastPollAt: null,
    progressSnapshot: {},
    cooldowns: [],
    freeCursor: 0,
    lastCycleNote: "",
    cycleLog: [],
  };
}

/** サイクル結果を記録する (lastCycleNote の更新と履歴への追加) */
export function pushCycleNote(state: HarnessState, note: string): void {
  state.lastCycleNote = note;
  state.cycleLog = [
    { at: new Date().toISOString(), note },
    ...state.cycleLog,
  ].slice(0, 10);
}

export function loadState(file: string): HarnessState {
  try {
    const raw = fs.readFileSync(file, "utf-8");
    const parsed = JSON.parse(raw) as Partial<HarnessState>;
    return { ...defaultState(), ...parsed, version: 1 };
  } catch {
    return defaultState();
  }
}

export function saveState(file: string, state: HarnessState): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2), "utf-8");
  fs.renameSync(tmp, file);
}

/** 現在有効な cooldown だけを返す (期限切れは捨てる) */
export function activeCooldowns(
  state: HarnessState,
  now: Date = new Date(),
): Cooldown[] {
  return state.cooldowns.filter((c) => new Date(c.until) > now);
}

export function isCoolingDown(
  state: HarnessState,
  scope: "model" | "pool",
  id: string,
  now: Date = new Date(),
): boolean {
  return activeCooldowns(state, now).some(
    (c) => c.scope === scope && c.id === id,
  );
}

/** 同じ scope + id があれば置き換え、無ければ追加する */
export function addCooldown(state: HarnessState, cooldown: Cooldown): void {
  state.cooldowns = state.cooldowns.filter(
    (c) => !(c.scope === cooldown.scope && c.id === cooldown.id),
  );
  state.cooldowns.push(cooldown);
}
