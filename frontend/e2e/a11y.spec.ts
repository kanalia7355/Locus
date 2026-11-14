import { spawn } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { test as base, expect } from "@playwright/test";
import type { BrowserContext, Page } from "@playwright/test";

// This spec owns its backend instance and its own account, so it never depends
// on the accounts, the password state or the numbering of the ambient e2e
// fixture that workspace.spec.ts uses.
const repoRoot = findRepoRoot();
const python = resolve(
  repoRoot,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
// 4173 is one of the hosts the local-only backend accepts.
const apiPort = 4173;
const apiBase = `http://127.0.0.1:${apiPort}`;
const uniqueUser = `a11y-${Date.now().toString(36)}-${Math.random()
  .toString(36)
  .slice(2, 8)}`;
const uniquePassword = "Synthetic-a11y-password-01!";
const rotatedPassword = "Synthetic-a11y-rotated-01!";

// Reuses the reviewed e2e fixture and only adds this spec's own account.
const serverRunner = `
import os
import runpy

import uvicorn

import app.main as main_module

port = int(os.environ["A11Y_PORT"])
username = os.environ["A11Y_USERNAME"]
password = os.environ["A11Y_PASSWORD"]
fixture = os.environ["A11Y_FIXTURE"]

original_create = main_module.create_app


def create_app(**kwargs):
    service = kwargs.get("service")
    if service is not None:
        service.provision(username, password)
        service.assign(username, "synthetic-project", "researcher")
        service.seed_synthetic(username, "synthetic-project")
    return original_create(**kwargs)


main_module.create_app = create_app
original_run = uvicorn.run


def run(app, **kwargs):
    kwargs["port"] = port
    kwargs["host"] = "127.0.0.1"
    return original_run(app, **kwargs)


uvicorn.run = run
runpy.run_path(fixture, run_name="__main__")
`;

function findRepoRoot(): string {
  let current = process.cwd();
  for (let depth = 0; depth < 6; depth++) {
    if (existsSync(join(current, "tests", "e2e_server.py"))) return current;
    const parent = resolve(current, "..");
    if (parent === current) break;
    current = parent;
  }
  throw new Error("リポジトリのルートが見つかりません");
}

async function waitForApi(): Promise<void> {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${apiBase}/api/health`);
      if (response.ok) return;
    } catch {
      // The dedicated backend is still starting.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error("専用のバックエンドが起動しませんでした");
}

let backend: ChildProcess | null = null;
let backendLog = "";
let sessionState: Awaited<ReturnType<BrowserContext["storageState"]>> | null =
  null;

const test = base.extend<{ a11yPage: Page }>({
  a11yPage: async ({ browser }, provide) => {
    const context = await browser.newContext(
      sessionState ? { storageState: sessionState } : {},
    );
    await context.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      url.protocol = "http:";
      url.host = `127.0.0.1:${apiPort}`;
      const response = await route.fetch({ url: url.toString() });
      await route.fulfill({ response });
    });
    const page = await context.newPage();
    await provide(page);
    await context.close();
  },
});

test.beforeAll(async () => {
  backend = spawn(python, ["-c", serverRunner], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: join(repoRoot, "backend"),
      LOCUS_E2E: "1",
      A11Y_PORT: String(apiPort),
      A11Y_USERNAME: uniqueUser,
      A11Y_PASSWORD: uniquePassword,
      A11Y_FIXTURE: join(repoRoot, "tests", "e2e_server.py"),
    },
    stdio: ["ignore", "ignore", "pipe"],
  });
  backend.stderr?.on("data", (chunk: Buffer) => {
    backendLog = `${backendLog}${chunk.toString()}`.slice(-4000);
  });
  await waitForApi().catch((error: Error) => {
    throw new Error(`${error.message}\n${backendLog}`);
  });
});

test.afterAll(async () => {
  backend?.kill();
  backend = null;
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

async function signIn(page: Page): Promise<void> {
  const rotate = page.getByRole("heading", { name: "仮パスワードの変更" });
  const workspace = page.getByRole("heading", {
    name: "資料を調べる",
    exact: true,
  });
  for (const candidate of [rotatedPassword, uniquePassword]) {
    await page.goto("/");
    await page.getByLabel("利用者ID").fill(uniqueUser);
    await page.getByLabel("パスワード", { exact: true }).fill(candidate);
    await page.getByRole("button", { name: "ログイン", exact: true }).click();
    await expect(
      rotate.or(workspace).or(page.getByRole("alert")).first(),
    ).toBeVisible({ timeout: 15000 });
    if (await workspace.isVisible()) return;
    if (await rotate.isVisible()) {
      await page.getByLabel("仮パスワード", { exact: true }).fill(candidate);
      await page
        .getByLabel("新しいパスワード", { exact: true })
        .fill(rotatedPassword);
      await page
        .getByLabel("新しいパスワード（確認）", { exact: true })
        .fill(rotatedPassword);
      await page.getByRole("button", { name: "変更して続ける" }).click();
      await expect(workspace).toBeVisible({ timeout: 15000 });
      return;
    }
  }
  throw new Error(`ログインできませんでした: ${uniqueUser}`);
}

async function ensureSignedIn(page: Page): Promise<void> {
  const workspace = page.getByRole("heading", {
    name: "資料を調べる",
    exact: true,
  });
  await page.goto("/");
  await expect(
    workspace.or(page.getByRole("heading", { name: "ログイン", exact: true })).first(),
  ).toBeVisible({ timeout: 15000 });
  if (await workspace.isVisible()) return;
  await signIn(page);
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
  a11yPage: page,
}) => {
  await page.goto("/");
  await expect(page.getByLabel("利用者ID")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("利用者ID")).toBeFocused();
  await page.keyboard.type(uniqueUser);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("パスワード", { exact: true })).toBeFocused();
  await page.keyboard.type(uniquePassword);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "ログイン", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "仮パスワードの変更" }),
  ).toBeVisible();

  await tabUntil(page, /^仮パスワード$/);
  await page.keyboard.type(uniquePassword);
  await tabUntil(page, /^新しいパスワード$/);
  await page.keyboard.type(rotatedPassword);
  await tabUntil(page, /^新しいパスワード（確認）$/);
  await page.keyboard.type(rotatedPassword);
  await tabUntil(page, /^変更して続ける$/);
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "資料を調べる", exact: true }),
  ).toBeVisible();

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

  // A fresh session is prepared for the remaining checks of this file.
  await signIn(page);
  sessionState = await page.context().storageState();
});

test("keyboard focus stays inside the source dialog and returns to its trigger", async ({
  a11yPage: page,
}) => {
  await ensureSignedIn(page);
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
  a11yPage: page,
}) => {
  await ensureSignedIn(page);
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

test("the workspace stays operable at a 375px viewport and the desktop layout ignores Escape", async ({
  a11yPage: page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
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

  // The wide layout belongs to the page: Escape inside the sidebar must not
  // collapse it, because that interaction does not exist in the baseline.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "サイドバーを閉じる", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("button", { name: "共有資料", exact: true }).focus();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "サイドバーを閉じる", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
});

test("live regions and accessible names cover the dynamic workspace", async ({
  a11yPage: page,
}) => {
  await ensureSignedIn(page);
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
