import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test as base, expect } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";

// Synthetic fixture credentials created by tests/e2e_server.py.
const ORIGINAL_PASSWORD = "Synthetic-test-password-01!";
const ROTATED_PASSWORD = "Changed-synthetic-password-01!";

// test-researcher-5 is the only fixture account that workspace.spec.ts leaves
// unused, so both suites can sign in without sharing credentials.
const KEYBOARD_USER = "test-researcher-5";

// The signed in session is reused between the tests of this file because the
// backend rate limits repeated sign-ins per account and per client address.
const storageStatePath = join(tmpdir(), "locus-a11y-storage-state.json");
const rotatedUsers = new Set<string>();

const test = base.extend<{ signedInPage: Page }>({
  signedInPage: async ({ browser }, provide) => {
    const context: BrowserContext = await browser.newContext(
      existsSync(storageStatePath) ? { storageState: storageStatePath } : {},
    );
    const page = await context.newPage();
    await ensureSignedIn(page);
    await context.storageState({ path: storageStatePath });
    await provide(page);
    await context.close();
  },
});

async function activeName(page: Page): Promise<string> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return "";
    const labelled = element as HTMLInputElement;
    const labels = labelled.labels
      ? Array.from(labelled.labels)
          .map((label) => (label.textContent ?? "").replace(/\s+/g, " ").trim())
          .join(" ")
      : "";
    const text = (element.textContent ?? "").replace(/\s+/g, " ").trim();
    return (element.getAttribute("aria-label") || text || labels).slice(0, 60);
  });
}

async function tabUntil(
  page: Page,
  pattern: RegExp,
  options: { backwards?: boolean; limit?: number } = {},
): Promise<string> {
  const limit = options.limit ?? 60;
  for (let index = 0; index < limit; index++) {
    const name = await activeName(page);
    if (name && pattern.test(name)) return name;
    await page.keyboard.press(options.backwards ? "Shift+Tab" : "Tab");
  }
  throw new Error(`キーボードで到達できませんでした: ${pattern}`);
}

async function signIn(page: Page, username: string): Promise<void> {
  const candidate = rotatedUsers.has(username)
    ? ROTATED_PASSWORD
    : ORIGINAL_PASSWORD;
  const rotate = page.getByRole("heading", { name: "仮パスワードの変更" });
  const workspace = page.getByRole("heading", {
    name: "資料を調べる",
    exact: true,
  });
  await page.goto("/");
  await page.getByLabel("利用者ID").fill(username);
  await page.getByLabel("パスワード", { exact: true }).fill(candidate);
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  await expect(
    rotate.or(workspace).or(page.getByRole("alert")).first(),
  ).toBeVisible({ timeout: 10000 });
  if (await workspace.isVisible()) return;
  if (!(await rotate.isVisible()))
    throw new Error(`ログインに失敗しました: ${username}`);
  await page.getByLabel("仮パスワード", { exact: true }).fill(candidate);
  await page
    .getByLabel("新しいパスワード", { exact: true })
    .fill(ROTATED_PASSWORD);
  await page
    .getByLabel("新しいパスワード（確認）", { exact: true })
    .fill(ROTATED_PASSWORD);
  await page.getByRole("button", { name: "変更して続ける" }).click();
  await expect(workspace).toBeVisible({ timeout: 15000 });
  rotatedUsers.add(username);
}

async function ensureSignedIn(page: Page): Promise<void> {
  const workspace = page.getByRole("heading", {
    name: "資料を調べる",
    exact: true,
  });
  await page.goto("/");
  await expect(
    workspace.or(page.getByRole("heading", { name: "ログイン", exact: true })).first(),
  ).toBeVisible({ timeout: 10000 });
  if (await workspace.isVisible()) return;
  await signIn(page, KEYBOARD_USER);
}

function focusIndicatorScript(): () => {
  name: string;
  visible: boolean;
  ratio: number;
} | null {
  return () => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return null;
    if (!element.getClientRects().length) return null;
    const parse = (value: string) => {
      const match = value.match(/rgba?\(([^)]+)\)/);
      if (!match) return null;
      const parts = match[1].split(",").map((part) => parseFloat(part));
      return {
        rgb: parts.slice(0, 3),
        alpha: parts.length > 3 ? parts[3] : 1,
      };
    };
    const luminance = (color: { rgb: number[] }) =>
      color.rgb.reduce((total, value, index) => {
        const channel = value / 255;
        const linear =
          channel <= 0.03928
            ? channel / 12.92
            : Math.pow((channel + 0.055) / 1.055, 2.4);
        return total + linear * [0.2126, 0.7152, 0.0722][index];
      }, 0);
    const contrast = (first: number, second: number) => {
      const high = Math.max(first, second);
      const low = Math.min(first, second);
      return (high + 0.05) / (low + 0.05);
    };
    const backgroundOf = (node: HTMLElement) => {
      let current: HTMLElement | null = node;
      while (current) {
        const color = parse(getComputedStyle(current).backgroundColor);
        if (color && color.alpha > 0) return color;
        current = current.parentElement;
      }
      return { rgb: [255, 255, 255], alpha: 1 };
    };
    const style = getComputedStyle(element);
    const outline = parse(style.outlineColor);
    const width = parseFloat(style.outlineWidth) || 0;
    const visible =
      style.outlineStyle !== "none" && width > 0 && !!outline && outline.alpha > 0;
    const ratio = visible
      ? contrast(luminance(outline!), luminance(backgroundOf(element)))
      : 0;
    return {
      name:
        element.getAttribute("aria-label") ||
        (element.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 40),
      visible,
      ratio: Math.round(ratio * 100) / 100,
    };
  };
}

test("keyboard only flow covers login, chat, sources, history and logout", async ({
  page,
}) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("利用者ID")).toBeFocused();
  await page.keyboard.type(KEYBOARD_USER);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("パスワード", { exact: true })).toBeFocused();
  await page.keyboard.type(ORIGINAL_PASSWORD);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "ログイン", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "仮パスワードの変更" }),
  ).toBeVisible();

  await tabUntil(page, /^仮パスワード$/);
  await page.keyboard.type(ORIGINAL_PASSWORD);
  await tabUntil(page, /^新しいパスワード$/);
  await page.keyboard.type(ROTATED_PASSWORD);
  await tabUntil(page, /^新しいパスワード（確認）$/);
  await page.keyboard.type(ROTATED_PASSWORD);
  await tabUntil(page, /^変更して続ける$/);
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "資料を調べる", exact: true }),
  ).toBeVisible();
  rotatedUsers.add(KEYBOARD_USER);

  const topbarOrder: string[] = [];
  for (let index = 0; index < 3; index++) {
    await page.keyboard.press("Tab");
    topbarOrder.push(await activeName(page));
  }
  expect(topbarOrder).toEqual(["サイドバーを閉じる", "プロジェクト", "ログアウト"]);

  const navigationOrder: string[] = [];
  for (let index = 0; index < 8; index++) {
    await page.keyboard.press("Tab");
    navigationOrder.push(await activeName(page));
  }
  expect(navigationOrder).toEqual([
    "資料を調べる",
    "共有資料",
    "個人資料",
    "調査履歴",
    "利用者・アクセス",
    "管理委任",
    "データ・処理",
    "取り込み状況",
  ]);

  await tabUntil(page, /^メッセージ$/);
  await page.keyboard.type("成膜条件を比較");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();

  await tabUntil(page, /合成サンプル_成膜条件\.txt · p\./);
  const citation = page.getByRole("button", {
    name: /合成サンプル_成膜条件.txt · p\./,
  });
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "出典の原文" });
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 6; index++) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(() => {
        const element = document.querySelector('[role="dialog"]');
        return !!element && !!document.activeElement
          ? element.contains(document.activeElement)
          : false;
      }),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(citation.first()).toBeFocused();

  await tabUntil(page, /^調査履歴$/);
  await page.keyboard.press("Enter");
  const historyHeading = page.getByRole("heading", {
    name: "調査履歴",
    exact: true,
  });
  await expect(historyHeading).toBeVisible();
  await expect(historyHeading).toBeFocused();

  await tabUntil(page, /^成膜条件/);
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "資料を調べる", exact: true }),
  ).toBeVisible();

  await tabUntil(page, /^ログアウト$/, { backwards: true });
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "ログイン", exact: true }),
  ).toBeVisible();

  // The session is restored so that the remaining tests reuse it.
  await tabUntil(page, /^利用者ID$/);
  await page.keyboard.type(KEYBOARD_USER);
  await tabUntil(page, /^パスワード$/);
  await page.keyboard.type(ROTATED_PASSWORD);
  await tabUntil(page, /^ログイン$/);
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "資料を調べる", exact: true }),
  ).toBeVisible();
  await page.context().storageState({ path: storageStatePath });
});

test("keyboard focus stays inside the source dialog and returns to its trigger", async ({
  signedInPage: page,
}) => {
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("成膜条件を比較");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();
  const citation = page
    .getByRole("button", { name: /合成サンプル_成膜条件.txt · p\./ })
    .first();
  await citation.click();
  const dialog = page.getByRole("dialog", { name: "出典の原文" });
  await expect(dialog).toBeVisible();
  const inside = () =>
    page.evaluate(() => {
      const element = document.querySelector('[role="dialog"]');
      return !!element && !!document.activeElement
        ? element.contains(document.activeElement)
        : false;
    });
  expect(await inside()).toBe(true);
  for (let index = 0; index < 8; index++) {
    await page.keyboard.press("Tab");
    expect(await inside()).toBe(true);
  }
  await page.keyboard.press("Shift+Tab");
  expect(await inside()).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(citation).toBeFocused();
});

test("every keyboard control shows a focus indicator with enough contrast", async ({
  signedInPage: page,
}) => {
  const indicators: { name: string; visible: boolean; ratio: number }[] = [];
  for (let index = 0; index < 40; index++) {
    await page.keyboard.press("Tab");
    const indicator = await page.evaluate(focusIndicatorScript());
    if (indicator) indicators.push(indicator);
  }
  expect(indicators.length).toBeGreaterThan(10);
  const weak = indicators.filter(
    (indicator) => !indicator.visible || indicator.ratio < 3,
  );
  expect(
    weak.map((indicator) => `${indicator.name} ${indicator.ratio}`),
  ).toEqual([]);
});

test("the workspace stays operable at a 375px viewport", async ({
  signedInPage: page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375);
  await ensureSignedIn(page);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375);

  const open = page.getByRole("button", { name: "サイドバーを開く", exact: true });
  await expect(open).toBeVisible();
  await open.click();
  await expect(page.locator("#workspace-sidebar")).toBeVisible();
  await tabUntil(page, /^共有資料$/);
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "サイドバーを開く", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(
    page.getByRole("button", { name: "サイドバーを開く", exact: true }),
  ).toBeFocused();

  await page.getByRole("textbox", { name: "メッセージ", exact: true }).fill("成膜");
  await expect(
    page.getByRole("button", { name: "送信", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375);
});

test("live regions and accessible names cover the dynamic workspace", async ({
  signedInPage: page,
}) => {
  const live = page.locator(".messages[aria-live='polite']");
  await expect(live).toHaveCount(1);
  await expect(page.locator(".send-state[role='status']")).toHaveCount(1);
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("成膜条件を比較");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();
  await expect(live).toContainText("資料に見つかった記述");

  const unnamed = await page.evaluate(() => {
    const problems: string[] = [];
    document
      .querySelectorAll("button, a[href], input, select, textarea")
      .forEach((element) => {
        const node = element as HTMLElement;
        if (node.hasAttribute("hidden")) return;
        if (!node.getClientRects().length) return;
        const labelled = node as HTMLInputElement;
        const labels = labelled.labels
          ? Array.from(labelled.labels)
              .map((label) => (label.textContent ?? "").trim())
              .join(" ")
          : "";
        const name =
          node.getAttribute("aria-label") ||
          (node.textContent ?? "").trim() ||
          (node.getAttribute("title") ?? "").trim() ||
          labels.trim();
        if (!name) problems.push(node.outerHTML.slice(0, 90));
      });
    return problems;
  });
  expect(unnamed).toEqual([]);
});
