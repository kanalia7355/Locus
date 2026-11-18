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

// jsdom には Popover API が無い（実測: `"popover" in HTMLElement.prototype === false`）。
// ここに置くのは既存の単体テストを動かすための最小限の代替実装であって、
// light dismiss の正しさの証明ではない（それは e2e/appearance.spec.ts の仕事）。
// 代入先を `as unknown as` で型付けし直しているのは、`in` による型の narrowing を
// 避けるため（jsdom の型定義では showPopover は存在するので、そのまま代入すると never になる）。
const popoverProto =
  typeof window !== "undefined"
    ? (HTMLElement.prototype as unknown as {
        showPopover?: () => void;
        hidePopover?: () => void;
      })
    : undefined;
if (popoverProto && typeof popoverProto.showPopover !== "function") {
  const openPopovers = new Set<HTMLElement>();
  const toggleEvent = (newState: "open" | "closed") => {
    const event = new Event("toggle") as ToggleEvent;
    Object.defineProperty(event, "newState", { value: newState });
    Object.defineProperty(event, "oldState", {
      value: newState === "open" ? "closed" : "open",
    });
    return event;
  };
  const lightDismiss = (event: Event) => {
    // 開いている auto ポップオーバーの外側が押されたら閉じる
    // （ブラウザの light dismiss の真似をしているだけ）。
    const target = event.target as Node | null;
    for (const el of [...openPopovers]) {
      if (el.getAttribute("popover") !== "auto") continue;
      if (target && el.contains(target)) continue;
      openPopovers.delete(el);
      el.dispatchEvent(toggleEvent("closed"));
    }
  };
  // jsdom は `[popover]:not(:popover-open) { display: none }` だけを持ち、
  // `:popover-open` を成立させる術が無いので、inline style で打ち消す。
  popoverProto.showPopover = function showPopover(this: HTMLElement) {
    openPopovers.add(this);
    this.style.display = "block";
    this.dispatchEvent(toggleEvent("open"));
  };
  popoverProto.hidePopover = function hidePopover(this: HTMLElement) {
    if (!openPopovers.delete(this)) {
      // 実ブラウザと同じく、閉じているポップオーバーを hide すると投げる。
      throw new DOMException(
        "hidePopover() called on a popover that is not showing",
        "InvalidStateError",
      );
    }
    this.style.display = "none";
    this.dispatchEvent(toggleEvent("closed"));
  };
  document.addEventListener("mousedown", lightDismiss);
  document.addEventListener("pointerdown", lightDismiss);
}

afterEach(() => {
  cleanup();
  // 製品コードが <html data-mode> を書き換えるので、テスト間で持ち越さないようにする。
  document.documentElement.removeAttribute("data-mode");
});
