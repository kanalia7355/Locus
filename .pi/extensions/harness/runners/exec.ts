// exec.ts — 子プロセス実行の共通基盤
//
// Windows では codex / opencode が npm のシム (.cmd) として入っているため、
// win32 では shell 経由で起動する (cmd.exe が PATHEXT で .cmd を解決する)。
// タイムアウト時はプロセスツリーごと止める (win32 は taskkill /T)。

import { spawn } from "node:child_process";

export interface RunResult {
  code: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
}

export interface RunOptions {
  cwd: string;
  timeoutMs?: number;
  env?: NodeJS.ProcessEnv;
  /** 子プロセスの stdin に流す文字列。undefined の場合は stdin を即閉じる (EOF) */
  input?: string;
}

export function runProcess(
  argv: string[],
  opts: RunOptions,
): Promise<RunResult> {
  return new Promise((resolve) => {
    const isWin = process.platform === "win32";
    const child = spawn(argv[0], argv.slice(1), {
      cwd: opts.cwd,
      env: opts.env ?? process.env,
      shell: isWin,
      windowsHide: true,
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let settled = false;

    const timer =
      opts.timeoutMs && opts.timeoutMs > 0
        ? setTimeout(() => {
            timedOut = true;
            if (isWin && child.pid) {
              spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
                windowsHide: true,
              });
            } else {
              child.kill("SIGKILL");
            }
          }, opts.timeoutMs)
        : null;

    const done = (code: number | null) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      resolve({ code, stdout, stderr, timedOut });
    };

    // stdin: プロンプトは引数ではなく stdin で渡すのが原則 (Windows のシム経由では
    // 引数文字列が空白で割れて化けるため)。渡すものが無くても必ず EOF を送る —
    // codex exec は引数プロンプト時でも stdin を読むため、開いたままにすると固まる。
    if (child.stdin) {
      child.stdin.on("error", () => {
        // 子が即終了した場合の EPIPE は無視する (終了コード側で判定する)
      });
      if (opts.input !== undefined) child.stdin.write(opts.input, "utf-8");
      child.stdin.end();
    }

    child.stdout?.on("data", (d: Buffer) => {
      stdout += d.toString("utf-8");
    });
    child.stderr?.on("data", (d: Buffer) => {
      stderr += d.toString("utf-8");
    });
    child.on("error", (err) => {
      stderr += `\n[spawn error] ${err.message}`;
      done(null);
    });
    child.on("close", (code) => done(code));
  });
}
