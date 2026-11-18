import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";
import {
  parseThemePreference,
  resolveColorScheme,
  resolveColorSchemeMeta,
  THEME_STORAGE_KEY,
} from "./theme";

describe("resolveColorScheme", () => {
  it("保存値なし・システムが暗いときは暗いモードになる", () => {
    expect(resolveColorScheme(null, true)).toBe("dark");
  });

  it("保存値なし・システムが明るいときは明るいモードになる", () => {
    expect(resolveColorScheme(null, false)).toBe("light");
  });

  it("保存値がライトなら、システムが暗くても明るいモードになる", () => {
    expect(resolveColorScheme("light", true)).toBe("light");
  });

  it("保存値がダークなら、システムが明るくても暗いモードになる", () => {
    expect(resolveColorScheme("dark", false)).toBe("dark");
  });

  it("保存値が空文字ならシステム設定に従い、例外を投げない", () => {
    expect(() => resolveColorScheme("", true)).not.toThrow();
    expect(resolveColorScheme("", true)).toBe("dark");
    expect(resolveColorScheme("", false)).toBe("light");
  });

  it("保存値が知らない値ならシステム設定に従い、例外を投げない", () => {
    expect(() => resolveColorScheme("solarized", false)).not.toThrow();
    expect(resolveColorScheme("solarized", true)).toBe("dark");
    expect(resolveColorScheme("solarized", false)).toBe("light");
  });

  it("保存値がシステムに従う指定ならシステム設定に従う", () => {
    expect(resolveColorScheme("system", true)).toBe("dark");
    expect(resolveColorScheme("system", false)).toBe("light");
  });
});

describe("parseThemePreference", () => {
  it("ライト・ダークをそのまま返す", () => {
    expect(parseThemePreference("light")).toBe("light");
    expect(parseThemePreference("dark")).toBe("dark");
  });

  it("未保存・壊れた値はシステムに従う扱いになる", () => {
    expect(parseThemePreference(null)).toBe("system");
    expect(parseThemePreference("")).toBe("system");
    expect(parseThemePreference("solarized")).toBe("system");
  });
});

// index.html のインラインスクリプトをそのまま実行して振る舞いを確かめる。
// 文字列の写しをテストに書くとインライン側だけ直されても気づかないので、
// ファイルから抜き出して実行する形にする。
function runInlineScript(
  storageGetItem: (key: string) => string | null,
): { content: string; key: string | null } {
  // jsdom の URL クラスだと readFileSync に渡せないので、cwd (frontend) から解決する
  const html = readFileSync("index.html", "utf8");
  const match = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!match) {
    throw new Error("index.html にインラインスクリプトが見つからない");
  }
  // マークアップの既定 (<meta content="light dark">) を反映した初期値にする。
  // 例外が起きた場合は書き込み自体がスキップされ、この既定のまま残るのが仕様。
  const meta = { content: "light dark" };
  let key: string | null = null;
  const sandbox = {
    localStorage: {
      getItem: (k: string) => {
        key = k;
        return storageGetItem(k);
      },
    },
    document: {
      querySelector: (selector: string) =>
        selector === 'meta[name="color-scheme"]' ? meta : null,
    },
  };
  runInNewContext(match[1], sandbox);
  return { content: meta.content, key };
}

describe("resolveColorSchemeMeta", () => {
  it("出力は light / dark / light dark の 3 値に限られる", () => {
    const values = new Set<string>();
    for (const saved of [null, "", "light", "dark", "system", "solarized", "light dark"]) {
      for (const systemDark of [true, false]) {
        values.add(resolveColorScheme(saved, systemDark));
      }
      values.add(resolveColorSchemeMeta(saved));
    }
    expect([...values].every((value) => ["light", "dark", "light dark"].includes(value))).toBe(
      true,
    );
    // light dark を含む 3 値すべてが出力されうること
    expect(values).toEqual(new Set(["light", "dark", "light dark"]));
  });

  it("保存値が light / dark / light dark ならそのまま返す", () => {
    expect(resolveColorSchemeMeta("light")).toBe("light");
    expect(resolveColorSchemeMeta("dark")).toBe("dark");
    expect(resolveColorSchemeMeta("light dark")).toBe("light dark");
  });

  it("システムに従う・未保存・壊れた値は light dark に落ちる", () => {
    expect(resolveColorSchemeMeta("system")).toBe("light dark");
    expect(resolveColorSchemeMeta(null)).toBe("light dark");
    expect(resolveColorSchemeMeta("")).toBe("light dark");
  });
});

describe("index.html のインラインスクリプト", () => {
  it("localStorage の読み出しに theme.ts と同じキーを使う", () => {
    const { key } = runInlineScript(() => null);
    expect(key).toBe(THEME_STORAGE_KEY);
  });

  it("保存値を <meta> の content にそのまま写す", () => {
    for (const value of ["light", "dark", "light dark"]) {
      expect(runInlineScript(() => value).content).toBe(value);
    }
  });

  it("読み出しが例外を投げても既定の light dark に落ちる", () => {
    expect(
      runInlineScript(() => {
        throw new Error("denied");
      }).content,
    ).toBe("light dark");
  });

  it("保存値がシステムに従う・壊れた値でも light dark に落ちる", () => {
    expect(runInlineScript(() => "system").content).toBe("light dark");
    expect(runInlineScript(() => "solarized").content).toBe("light dark");
    expect(runInlineScript(() => null).content).toBe("light dark");
  });
});
