import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom は window.matchMedia を実装していない。システムのカラースキーム
// 設定を読む製品コードをテストできるよう、既定でライトを返す差し替えを用意する。
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList) as typeof window.matchMedia;
}

afterEach(() => {
  cleanup();
  // 製品コードが <html data-mode> を書き換えるので、テスト間で持ち越さないようにする。
  document.documentElement.removeAttribute("data-mode");
});
