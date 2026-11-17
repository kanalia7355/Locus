import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

/**
 * Looking at a screenshot is not a check. These are the layout invariants that
 * a human noticed by scrolling around, written so a machine notices instead.
 *
 * Each one exists because the real screen broke it, not because it sounded
 * sensible. A test marked `test.fail()` is a bug we have measured and not fixed
 * yet: it flips to a failure the moment the fix lands, which is the signal to
 * delete the marker in the same job.
 */

const WIDTHS = [
  { name: "desktop", width: 1280, height: 820 },
  { name: "tablet", width: 768, height: 900 },
  { name: "phone", width: 360, height: 740 },
];

// The owner settled this on 2026-11-17: no emoji anywhere in the product.
// One property escape, no character class: a class holding a base character and
// a variation selector is misleading (eslint no-misleading-character-class), and
// the `v` flag that would fix it needs an es2024 target this project does not set.
const EMOJI = /\p{Extended_Pictographic}/u;

async function enter(page: Page, index: number) {
  await page.goto("/");
  await page.getByLabel("利用者ID").fill(`test-researcher-${index}`);
  await page
    .getByLabel("パスワード", { exact: true })
    .fill("Synthetic-test-password-01!");
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  await page
    .getByLabel("仮パスワード", { exact: true })
    .fill("Synthetic-test-password-01!");
  await page
    .getByLabel("新しいパスワード", { exact: true })
    .fill("Changed-synthetic-password-01!");
  await page
    .getByLabel("新しいパスワード（確認）", { exact: true })
    .fill("Changed-synthetic-password-01!");
  await page.getByRole("button", { name: "変更して続ける" }).click();
  // Wait on the composer rather than a heading: the headings are being renamed
  // by T-PH6-112, the message box is the one thing the chat screen always has.
  await expect(
    page.getByRole("textbox", { name: "メッセージ", exact: true }),
  ).toBeVisible();
}

/** Ask one question so the transcript is long enough to need scrolling. */
async function askSomething(page: Page) {
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("成膜条件を比較");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();
}

test("no screen scrolls sideways at any supported width", async ({ page }) => {
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 1);
  await askSomething(page);
  for (const size of WIDTHS) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    const overflow = await page.evaluate(() => {
      const root = document.scrollingElement ?? document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    expect(overflow, `${size.name} scrolls sideways by ${overflow}px`).toBeLessThanOrEqual(1);
  }
});

test("nothing is rendered off the right edge", async ({ page }) => {
  // Catches a long document name or an unwrapped control pushing content out of
  // reach — the kind of break that a screenshot of the default data never shows.
  await page.setViewportSize(WIDTHS[2]);
  await enter(page, 2);
  const escaping = await page.evaluate(() => {
    const limit = document.documentElement.clientWidth + 2;
    return [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((node) => {
        const box = node.getBoundingClientRect();
        return box.width > 0 && box.height > 0 && box.right > limit;
      })
      .slice(0, 5)
      .map((node) => `${node.tagName.toLowerCase()}.${node.className}`.slice(0, 80));
  });
  expect(escaping, "elements past the right edge").toEqual([]);
});

test("the screens render without a console or page error", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    // The browser logs every non-2xx response as a console error. A 401 before
    // sign-in and a 409 on a conflicting action are the product working, so
    // matching on "console error" alone would fail forever and teach everyone
    // to ignore this check. Only faults thrown by our own code count.
    const text = message.text();
    if (message.type() === "error" && !text.startsWith("Failed to load resource")) {
      problems.push(`console: ${text}`);
    }
  });
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 3);
  await askSomething(page);
  for (const name of ["共有資料", "個人資料", "調査履歴"]) {
    const link = page.getByRole("button", { name, exact: true });
    if (await link.count()) {
      await link.first().click();
      await page.waitForTimeout(300);
    }
  }
  expect(problems).toEqual([]);
});

test("no emoji reaches the screen", async ({ page }) => {
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 4);
  await askSomething(page);
  const text = await page.evaluate(() => document.body.innerText);
  const found = text.match(EMOJI);
  expect(found?.[0] ?? null, "an emoji is rendered").toBeNull();
});

test("every icon-only control says what it does", async ({ page }) => {
  // Icon buttons carry the main actions here (sidebar, attach, send, new chat).
  // Without a name they are unusable by keyboard and by screen reader alike.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 5);
  const nameless = await page.evaluate(() =>
    [...document.querySelectorAll("button")]
      .filter((node) => {
        const visible = node.getBoundingClientRect().height > 0;
        const labelled =
          (node.textContent ?? "").trim().length > 0 ||
          node.getAttribute("aria-label") ||
          node.getAttribute("title");
        return visible && !labelled;
      })
      .map((node) => node.outerHTML.slice(0, 90)),
  );
  expect(nameless, "buttons with no accessible name").toEqual([]);
});

test.fail(
  "the top bar stays put while the conversation scrolls",
  async ({ page }) => {
    // Measured 2026-11-17: the whole document scrolls, so the product name,
    // project switcher and sign-out leave the screen. Fixed by T-PH6-109 —
    // when this starts passing, remove the test.fail marker in that job.
    await page.setViewportSize(WIDTHS[0]);
    await enter(page, 6);
    await askSomething(page);
    await page.mouse.wheel(0, 1200);
    await page.waitForTimeout(400);
    const bar = await page.locator("header, .topbar").first().boundingBox();
    expect(bar?.y ?? -1, "top bar scrolled off the screen").toBeGreaterThanOrEqual(0);
  },
);

test.fail("the message box stays reachable", async ({ page }) => {
  // Measured 2026-11-17: the composer sits at the end of the document and
  // scrolls away with it. Fixed by T-PH6-111 — remove this marker in that job.
  // One exchange is not enough to prove it: the page has to be tall enough that
  // the end of the document is off screen while you are reading the start.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 8);
  for (let turn = 0; turn < 3; turn++) await askSomething(page);
  await page.evaluate(() => (document.scrollingElement ?? document.body).scrollTo(0, 0));
  await page.waitForTimeout(400);
  await expect(
    page.getByRole("textbox", { name: "メッセージ", exact: true }),
  ).toBeInViewport();
});
