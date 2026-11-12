// testscope.ts — 変更ファイルから「回すべきテスト」を絞る
//
// 決定事項: テストは無駄に回さない。変更に関連するテストだけを実行し、
// フルスイートは Phase の節目でのみ回す。
// 対応付けできないソース変更は unmapped に残し、呼び出し側 (Luna / 人間) が
// 節目でまとめて扱う。ドキュメントや進捗報告だけの変更ではテストを回さない。

import * as fs from "node:fs";
import * as path from "node:path";

/** argv 形式のコマンド (例: ["python", "-m", "pytest", "tests/test_x.py"]) */
export type TestCommand = string[];

export interface TestScope {
  commands: TestCommand[];
  /** テストに対応付けできなかったソースファイル */
  unmapped: string[];
}

const IGNORED_PREFIXES = ["progress/", "docs/", ".pi/"];

function isIgnored(file: string): boolean {
  const f = file.replace(/\\/g, "/");
  return f.endsWith(".md") || IGNORED_PREFIXES.some((p) => f.startsWith(p));
}

function isPythonTest(file: string): boolean {
  const base = path.basename(file);
  return base.startsWith("test_") && base.endsWith(".py");
}

function isJsTest(file: string): boolean {
  return /\.(test|spec)\.(ts|tsx|js|jsx)$/.test(file);
}

/** testsDir 配下から test_<stem>.py を探す (深さ上限つき) */
function findPythonTest(
  testsDir: string,
  stem: string,
  depth = 0,
): string | null {
  if (depth > 4 || !fs.existsSync(testsDir)) return null;
  for (const entry of fs.readdirSync(testsDir, { withFileTypes: true })) {
    const full = path.join(testsDir, entry.name);
    if (entry.isFile() && entry.name === `test_${stem}.py`) return full;
    if (entry.isDirectory()) {
      const hit = findPythonTest(full, stem, depth + 1);
      if (hit) return hit;
    }
  }
  return null;
}

export function relatedTests(
  changedFiles: string[],
  repoRoot: string,
): TestScope {
  const commands: TestCommand[] = [];
  const seen = new Set<string>();
  const unmapped: string[] = [];
  const add = (cmd: TestCommand) => {
    const key = cmd.join(" ");
    if (!seen.has(key)) {
      seen.add(key);
      commands.push(cmd);
    }
  };

  for (const file of changedFiles) {
    const rel = file.replace(/\\/g, "/");
    if (isIgnored(rel)) continue;
    const abs = path.join(repoRoot, rel);

    // テストファイル自体の変更は、そのテストを実行する
    if (isPythonTest(rel)) {
      add(["python", "-m", "pytest", rel, "-x", "-q"]);
      continue;
    }
    if (isJsTest(rel)) {
      add(["npm", "--prefix", "frontend", "test", "--", rel]);
      continue;
    }

    // Python ソース → 対応する test_<stem>.py を tests/ から探す
    if (rel.endsWith(".py")) {
      const stem = path.basename(rel, ".py");
      const hit = findPythonTest(path.join(repoRoot, "tests"), stem);
      if (hit) {
        add([
          "python",
          "-m",
          "pytest",
          path.relative(repoRoot, hit).replace(/\\/g, "/"),
          "-x",
          "-q",
        ]);
      } else {
        unmapped.push(rel);
      }
      continue;
    }

    // フロントエンドのソース → 同名の .test / .spec を探す
    if (/\.(ts|tsx|js|jsx)$/.test(rel)) {
      const stem = rel.replace(/\.(ts|tsx|js|jsx)$/, "");
      const candidates = [".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"].map(
        (s) => path.join(repoRoot, stem + s),
      );
      const hit = candidates.find((c) => fs.existsSync(c));
      if (hit) {
        add([
          "npm",
          "--prefix",
          "frontend",
          "test",
          "--",
          path.relative(repoRoot, hit).replace(/\\/g, "/"),
        ]);
      } else {
        unmapped.push(rel);
      }
      continue;
    }

    // それ以外の変更 (設定・infra 等) は節目で扱う
    if (fs.existsSync(abs)) unmapped.push(rel);
  }

  return { commands, unmapped };
}
