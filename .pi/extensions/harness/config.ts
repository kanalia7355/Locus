// config.ts — ハーネスの調整可能な既定値
//
// 値を変えたいときはこのファイルだけを直す。秘密情報はここに書かない。

export interface HarnessConfig {
  /** progress/ のポーリング間隔 (ms) */
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
  /** Luna の割当を受けてワーカーを自動起動するか (TODO-02 の dispatch) */
  dispatchEnabled: boolean;
  /** タスクが done に遷移したサイクルで、その成果物をコミットするか */
  commitOnDone: boolean;
  /** コミット後、現在のブランチを origin へ push して GitHub に同期するか */
  pushOnCommit: boolean;
}

export const DEFAULT_CONFIG: HarnessConfig = {
  pollIntervalMs: 10 * 60 * 1000,
  lunaModel: "gpt-6-luna",
  agyPrintTimeout: "30m",
  processTimeoutMs: 35 * 60 * 1000,
  stateFile: ".pi/harness/state.json",
  progressDir: "progress",
  promptsDir: ".pi/harness/prompts",
  dispatchEnabled: true,
  commitOnDone: true,
  pushOnCommit: true,
};
