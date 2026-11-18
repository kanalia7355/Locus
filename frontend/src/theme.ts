// 表示テーマ（ライト / システムに従う / ダーク）の解決ロジック。
// 壊れた保存値の検証もここで行う。
export type ColorScheme = "light" | "dark";
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
