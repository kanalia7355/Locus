// 表示テーマ（ライト / システムに従う / ダーク）の解決ロジック。
// 壊れた保存値の検証もここで行う。
// light dark は「両方に対応し、システム設定に従う」という color-scheme の値で、
// JS が動かない初期描画でも両方の配色を宣言できるように使う。
export type ColorScheme = "light" | "dark" | "light dark";
export type ThemePreference = "light" | "system" | "dark";

export const THEME_STORAGE_KEY = "locus-theme";

export function parseThemePreference(saved: string | null): ThemePreference {
  if (saved === "light" || saved === "dark" || saved === "system") return saved;
  return "system";
}

export function resolveColorScheme(
  saved: string | null,
  systemDark: boolean,
): ColorScheme {
  const preference = parseThemePreference(saved);
  if (preference !== "system") return preference;
  return systemDark ? "dark" : "light";
}

// <meta name="color-scheme"> の content に入れる値を返す。
// index.html のインラインスクリプトはモジュールを参照できないため、同じ対応表を
// 素の JavaScript で写している（theme.test.ts が両者の一致を実行で確かめる）。
//   保存値が "light" / "dark" / "light dark"  → そのまま
//   それ以外（"system"・未保存・壊れた値）     → "light dark"
// "system" をそのまま meta に入れると color-scheme のキーワードとして解釈されず
// 無効になるので、"light dark" に写す必要がある。
export function resolveColorSchemeMeta(saved: string | null): ColorScheme {
  if (saved === "light" || saved === "dark" || saved === "light dark") {
    return saved;
  }
  return "light dark";
}
