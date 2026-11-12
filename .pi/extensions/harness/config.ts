// config.ts — ハーネスの調整可能な既定値
//
// 値を変えたいときはこのファイルだけを直す。秘密情報はここに書かない。

export interface HarnessConfig {
  /** progress/ のポーリング間隔 (ms)。決定事項: 30分 */
  pollIntervalMs: number;
  /** オーケストレーター (Codex) のモデル ID。実在しない場合は BOOTSTRAP_TODO へ */
  lunaModel: string;
  /** agy の --print-timeout */
  agyPrintTimeout: string;
  /** ワーカー / Luna のプロセス上限 (ms) */
  processTimeoutMs: number;
  /** repo ルートからの相対パス: ハーネスの状態ファイル */
  stateFile: string;
  /** repo ルートからの相対パス: 進捗報告ディレクトリ */
  progressDir: string;
  /** repo ルートからの相対パス: プロンプト置き場 */
  promptsDir: string;
}

export const DEFAULT_CONFIG: HarnessConfig = {
  pollIntervalMs: 30 * 60 * 1000,
  lunaModel: "gpt-6-luna",
  agyPrintTimeout: "30m",
  processTimeoutMs: 35 * 60 * 1000,
  stateFile: ".pi/harness/state.json",
  progressDir: "progress",
  promptsDir: ".pi/harness/prompts",
};
