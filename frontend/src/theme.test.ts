import { describe, expect, it } from "vitest";
import { parseThemePreference, resolveColorScheme } from "./theme";

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
