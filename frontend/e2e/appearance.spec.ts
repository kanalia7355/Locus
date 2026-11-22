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

/** Widths for responsive layout checks. */
const WIDTHS = [
  { name: "desktop", width: 1280, height: 820 },
  { name: "tablet", width: 768, height: 900 },
  { name: "phone", width: 360, height: 740 },
  { name: "phone-narrow", width: 320, height: 740 },
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

/** Ask one question, and wait for this answer rather than any answer.
 *
 * Waiting on the heading itself only works for the first exchange: from the
 * second one there are two of them and the locator is ambiguous, which reads as
 * a product failure when it is only an ambiguous selector.
 */
async function askSomething(page: Page) {
  const answers = page.getByRole("heading", { name: "資料に見つかった記述" });
  const before = await answers.count();
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("成膜条件を比較");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(answers).toHaveCount(before + 1);
}

/** Sign in as an account an earlier check already rotated.
 *
 * The e2e server provisions one throwaway account per check (0..12) and
 * enter() spends it by rotating the temporary password, so a later check
 * cannot use enter() again. It signs in with the rotated password instead.
 * Like the scope-popup check below, this depends on the file's execution
 * order (workers: 1, retries: 0); run the whole file, not a single -g case.
 */
async function signInAgain(page: Page, index: number) {
  await page.goto("/");
  await page.getByLabel("利用者ID").fill(`test-researcher-${index}`);
  await page
    .getByLabel("パスワード", { exact: true })
    .fill("Changed-synthetic-password-01!");
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "メッセージ", exact: true }),
  ).toBeVisible();
}

/** Open the source modal the way a reader does: click the citation.
 *
 * Clicking the citation is what wires up the document and chunk the modal
 * shows, so the check drives the real path instead of a shortcut.
 */
async function openSourceModal(page: Page) {
  await page
    .getByRole("button", { name: /合成サンプル_成膜条件\.txt · p\./ })
    .first()
    .click();
  const modal = page.getByRole("dialog", { name: "出典の原文" });
  await expect(modal).toBeVisible();
  return modal;
}

/**
 * A button that is enabled but always fails is worse than no button: copying
 * the temporary password is how an administrator hands the account over, and
 * the LAN screen must not offer that control when the clipboard API is absent
 * (ProvisionUser.tsx does not render it in that case).
 *
 * Limitation: Playwright runs at http://127.0.0.1:5174, which is a SecureContext,
 * so navigator.clipboard exists here and this test cannot reproduce the plain
 * HTTP LAN case. ProvisionUser.test.tsx covers the non-SecureContext path.
 */
test("every enabled control on the one-time password screen works", async ({
  page,
}) => {
  // Clipboard write needs a granted permission even in headless Chromium; the
  // copy itself has to succeed here, or this check measures the wrong thing.
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "http://127.0.0.1:5174",
  });
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 0);
  await page.getByRole("button", { name: "利用者", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "利用者の追加" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "追加", exact: true }).click();
  await page.getByRole("textbox", { name: "利用者ID" }).fill("test-user-e2e");
  await page.getByRole("button", { name: "作成", exact: true }).click();

  const passwordRegion = page.getByRole("region", {
    name: "一度だけ表示される仮パスワード",
  });
  await expect(passwordRegion).toBeVisible();
  // The password itself is shown whether or not copying is available, so the
  // administrator can still pass it on by selecting it.
  await expect(passwordRegion.locator("code")).not.toHaveText("");

  // There is no enabled button in this region that the test does not exercise.
  const enabledLabels = await passwordRegion
    .getByRole("button")
    .evaluateAll((buttons) =>
      buttons
        .filter((button) => !(button as HTMLButtonElement).disabled)
        .map((button) => (button.textContent ?? "").trim()),
    );
  expect(enabledLabels).toEqual(["コピー", "閉じる"]);

  const copyButton = passwordRegion.getByRole("button", {
    name: "コピー",
    exact: true,
  });
  await expect(copyButton).toBeEnabled();
  await copyButton.click();
  // Wait for the result of the click instead of counting synchronously: the
  // notice is set after the clipboard promise settles.
  await expect(passwordRegion.getByText("コピーしました。")).toBeVisible();
  await expect(passwordRegion.getByText(/できませんでした/)).toHaveCount(0);

  const closeButton = passwordRegion.getByRole("button", {
    name: "閉じる",
    exact: true,
  });
  await expect(closeButton).toBeEnabled();
  await closeButton.click();
  await expect(passwordRegion).toHaveCount(0);
  await expect(page.getByText(/できませんでした/)).toHaveCount(0);
});

test("login: no field reports aria-invalid=true straight after the page loads", async ({
  page,
}) => {
  // Limitation of this check: test:appearance only runs chromium (see
  // playwright.config.ts), so it cannot observe Firefox/Safari publishing an
  // empty required control as invalid from load. It pins the explicit
  // aria-invalid="false" initial value — the thing that keeps those engines
  // from announcing a pristine form as invalid — not the engines' own UI.
  await page.setViewportSize(WIDTHS[0]);
  await page.goto("/");
  await expect(page.locator('[aria-invalid="true"]')).toHaveCount(0);
  const requiredFields = page.locator("input[required]");
  await expect(requiredFields).toHaveCount(2);
  for (const field of await requiredFields.all()) {
    await expect(field).toHaveAttribute("aria-invalid", "false");
  }
});

test("login: submitting an empty form shows the field errors and focuses the first field", async ({
  page,
}) => {
  // Measured 2026-11-19: before this job the empty submit was swallowed by
  // native validation with nothing rendered and no coded focus move.
  await page.setViewportSize(WIDTHS[0]);
  await page.goto("/");
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  await expect(page.locator("#access-username-error")).toBeVisible();
  await expect(page.locator("#access-username-error")).toContainText(
    "利用者ID",
  );
  await expect(page.locator("#access-password-error")).toBeVisible();
  await expect(page.locator("#access-password-error")).toContainText(
    "パスワード",
  );
  await expect(page.getByLabel("利用者ID")).toBeFocused();
  await expect(page.getByLabel("利用者ID")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  await expect(page.getByLabel("利用者ID")).toHaveAttribute(
    "aria-describedby",
    "access-username-error",
  );
});

test("login: the field error state does not scroll sideways at any supported width", async ({
  page,
}) => {
  await page.setViewportSize(WIDTHS[0]);
  await page.goto("/");
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  for (const size of WIDTHS) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    const overflow = await page.evaluate(() => {
      const root = document.scrollingElement ?? document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    expect(
      overflow,
      `${size.name} scrolls sideways by ${overflow}px`,
    ).toBeLessThanOrEqual(1);
  }
});

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
    expect(
      overflow,
      `${size.name} scrolls sideways by ${overflow}px`,
    ).toBeLessThanOrEqual(1);
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
      .map((node) =>
        `${node.tagName.toLowerCase()}.${node.className}`.slice(0, 80),
      );
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
    if (
      message.type() === "error" &&
      !text.startsWith("Failed to load resource")
    ) {
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

test("the top bar stays put while the conversation scrolls", async ({
  page,
}) => {
  // Measured 2026-11-17: the whole document scrolled, so the product name,
  // project switcher and sign-out left the screen. The shell is pinned to the
  // viewport now, so the page must not move when the content scrolls.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 6);
  await askSomething(page);
  await page.mouse.wheel(0, 1200);
  await page.waitForTimeout(400);
  const bar = await page.locator("header, .topbar").first().boundingBox();
  expect(
    bar?.y ?? -1,
    "top bar scrolled off the screen",
  ).toBeGreaterThanOrEqual(0);
});

test("the message box stays reachable", async ({ page }) => {
  // One exchange is not enough to prove it: the page has to be tall enough that
  // the end of the document is off screen while you are reading the start.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 8);
  for (let turn = 0; turn < 3; turn++) await askSomething(page);
  await page.evaluate(() =>
    (document.scrollingElement ?? document.body).scrollTo(0, 0),
  );
  await page.waitForTimeout(400);
  await expect(
    page.getByRole("textbox", { name: "メッセージ", exact: true }),
  ).toBeInViewport();
});

test("a jump to the first message lands clear of the notice and the composer", async ({
  page,
}) => {
  // The notice rides above the conversation and the composer below it. A
  // programmatic jump (from a citation, or to a fresh answer) must land the
  // target fully between them, not underneath either.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 9);
  for (let turn = 0; turn < 3; turn++) await askSomething(page);
  await page.evaluate(() => {
    const messages = document.querySelector<HTMLElement>(".messages");
    if (messages) messages.scrollTop = 0;
  });
  await page.evaluate(() => {
    document
      .querySelector<HTMLElement>(".user-message")
      ?.scrollIntoView({ block: "nearest" });
  });
  const targetBox = await page.locator(".user-message").first().boundingBox();
  const noticeBox = await page.locator(".chat-notice").boundingBox();
  const composerBox = await page.locator(".composer").boundingBox();
  expect(targetBox, "the jump target is not visible").not.toBeNull();
  expect(noticeBox, "the notice is not visible").not.toBeNull();
  expect(composerBox, "the composer is not visible").not.toBeNull();
  const targetTop = targetBox!.y;
  const targetBottom = targetBox!.y + targetBox!.height;
  const noticeBottom = noticeBox!.y + noticeBox!.height;
  const composerTop = composerBox!.y;
  expect(
    targetTop,
    `target top ${targetTop}px is under the notice bottom ${noticeBottom}px`,
  ).toBeGreaterThanOrEqual(noticeBottom);
  expect(
    targetBottom,
    `target bottom ${targetBottom}px is under the composer top ${composerTop}px`,
  ).toBeLessThanOrEqual(composerTop);
});

test("the reading position holds while the conversation grows", async ({
  page,
}) => {
  // Overflow anchoring is on by default and is what keeps a reader's place
  // when content is inserted. This is the invariant a future
  // `overflow-anchor: none` would silently break.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 7);
  await askSomething(page);
  await askSomething(page);
  await page.evaluate(() => {
    const messages = document.querySelector<HTMLElement>(".messages");
    if (messages) messages.scrollTop = 0;
  });
  const before = await page.evaluate(
    () => document.querySelector<HTMLElement>(".messages")?.scrollTop ?? -1,
  );
  // Equivalent to receiving more SSE content: the list grows underneath a
  // reader who is scrolled up.
  await askSomething(page);
  const after = await page.evaluate(
    () => document.querySelector<HTMLElement>(".messages")?.scrollTop ?? -1,
  );
  expect(after, "scrollTop moved while the conversation grew").toBe(before);
});

test("the message box grows with its content", async ({ page }) => {
  // Measured 2026-11-19: the textarea had a fixed height, so a five-line
  // draft scrolled inside it instead of growing it. With
  // `field-sizing: content` the box fits its content, so five lines must
  // render taller than one.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 10);
  const box = page.getByRole("textbox", { name: "メッセージ", exact: true });
  await box.fill("一行");
  const one = (await box.boundingBox())?.height ?? 0;
  await box.fill("一行目\n二行目\n三行目\n四行目\n五行目");
  const five = (await box.boundingBox())?.height ?? 0;
  expect(
    five,
    `five lines (${five}px) are not taller than one line (${one}px)`,
  ).toBeGreaterThan(one);
});

test("the message box stops at its upper limit below the notice", async ({
  page,
}) => {
  // Measured 2026-11-19: with enough lines the box must stop at
  // `max-block-size` (a share of the viewport height) rather than eat the
  // conversation, and its top edge must stay below the standing notice
  // (T-PH6-115). Twenty and thirty lines both exceed the cap, so the two
  // heights must be equal; the exact ratio lives in styles.css.
  await page.setViewportSize(WIDTHS[0]);
  await enter(page, 11);
  const box = page.getByRole("textbox", { name: "メッセージ", exact: true });
  const lines = (count: number) =>
    Array.from({ length: count }, (_, i) => `${i + 1}行目`).join("\n");
  await box.fill(lines(20));
  const twenty = (await box.boundingBox())?.height ?? 0;
  await box.fill(lines(30));
  const thirtyBox = await box.boundingBox();
  expect(thirtyBox, "the message box is not visible").not.toBeNull();
  const notice = await page.locator(".chat-notice").boundingBox();
  expect(notice, "the notice is not visible").not.toBeNull();
  // Two separate boundingBox calls, each after a re-layout; allow the same
  // 1px of sub-pixel rounding the rest of this file allows.
  expect(
    Math.abs(thirtyBox!.height - twenty),
    `thirty lines drew ${thirtyBox!.height}px but twenty drew ${twenty}px; the box did not stop at its limit`,
  ).toBeLessThanOrEqual(1);
  const noticeBottom = notice!.y + notice!.height;
  expect(
    thirtyBox!.y,
    `the box top ${thirtyBox!.y}px is not below the notice bottom ${noticeBottom}px`,
  ).toBeGreaterThanOrEqual(noticeBottom - 1);
  // A tall draft must not push any supported width sideways either.
  for (const size of WIDTHS) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    const overflow = await page.evaluate(() => {
      const root = document.scrollingElement ?? document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    expect(
      overflow,
      `${size.name} scrolls sideways by ${overflow}px with a tall draft`,
    ).toBeLessThanOrEqual(1);
  }
});

test("the last utterance is not hidden under the grown input box", async ({
  page,
}) => {
  // T-PH6-111 kept the last message clear of the composer. The composer is
  // taller once the box fits its content, so re-measure with a five-line
  // draft: scrolled to the end, the last exchange must sit entirely above
  // the composer.
  await page.setViewportSize(WIDTHS[0]);
  // Its own account: index 0 is the administrator the one-time-password test
  // logs in as, and `enter()` can only run once per account.
  await enter(page, 12);
  for (let turn = 0; turn < 3; turn++) await askSomething(page);
  const box = page.getByRole("textbox", { name: "メッセージ", exact: true });
  await box.fill("一行目\n二行目\n三行目\n四行目\n五行目");
  await page.evaluate(() => {
    const messages = document.querySelector<HTMLElement>(".messages");
    // A huge top value is clamped by the browser to the maximum scroll
    // position, so this lands on the last utterance without measuring
    // content height (reading content height to size the input is what
    // this job exists to avoid).
    if (messages) messages.scrollTo({ top: Number.MAX_SAFE_INTEGER });
  });
  await page.waitForTimeout(400);
  const lastBox = await page.locator(".exchange").last().boundingBox();
  const composerBox = await page.locator(".composer").boundingBox();
  expect(lastBox, "the last exchange is not rendered").not.toBeNull();
  expect(composerBox, "the composer is not visible").not.toBeNull();
  const lastBottom = lastBox!.y + lastBox!.height;
  expect(
    lastBottom,
    `the last exchange bottom ${lastBottom}px is under the composer top ${composerBox!.y}px`,
  ).toBeLessThanOrEqual(composerBox!.y + 1);
});

// T-PH6-118 / T-PH6-110 受入条件5「明るい配色が一瞬見えてから暗くなることがない」。
// 正攻法は <meta name="color-scheme"> とその直後の同期インラインスクリプト（CSS だけでは
// 初期描画に間に合わない）。この2本はそのちらつきを機械的に代用する検査。
// このファイルのテストはテスト利用者 (test-researcher-0..11) を各1回ずつ使い切る
// （enter() が仮パスワードを回すため再ログインできない）。新しいアカウントは
// テスト用サーバ (tests/e2e_server.py) が range(12) しか provision せず、そのファイルは
// 本ジョブの許可パス外なので、ここでは未ログインのエントリー画面で測る。
// エントリー画面も配色トークン全体を読み込む実際の画面なので、ちらつきの検査として成立する。
test.describe("color-scheme in a dark browser context", () => {
  test.use({ colorScheme: "dark" });

  test("the page paints on a dark background in a dark browser context", async ({
    page,
  }) => {
    // Measured 2026-11-19: ダークブラウザ文脈で入場したとき、<html> の背景は
    // --color-paper のトークン値を持つ。明るい側 (#fff) ではないことを確かめる。
    await page.setViewportSize(WIDTHS[0]);
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    const background = await page.evaluate(
      () => getComputedStyle(document.documentElement).backgroundColor,
    );
    expect(background, "the page painted with the light paper token").not.toBe(
      "rgb(255, 255, 255)",
    );
  });
});

// T-PH6-117: 参照範囲のポップオーバーを Popover API に載せ替えた。ここからは
// 「ポップオーバーが top layer に出る」ことに依存する検査。このファイルは使い切りの
// 合成アカウントで動き、新規ログイン分のアカウントは無いので、冒頭の横スクロール検査が
// 一度だけ回し終えた test-researcher-1 に、このファイルが enter() で使うのと同じ合成の
// 変更後パスワードで入り直す。
// 注意: このテストはファイル全体の実行順に依存する（fresh DB・workers:1・retries:0・
// ファイル順）。-g でこの1件だけを抜き出すと test-researcher-1 は未回転のままなので、
// 変更後パスワードでは入れずログイン待ちで失敗する。ファイル全体で実行すること。
test("the scope popup dismisses on an outside click and is not covered", async ({
  page,
}) => {
  await page.setViewportSize(WIDTHS[0]);
  await page.goto("/");
  await page.getByLabel("利用者ID").fill("test-researcher-1");
  await page
    .getByLabel("パスワード", { exact: true })
    .fill("Changed-synthetic-password-01!");
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  const textbox = page.getByRole("textbox", {
    name: "メッセージ",
    exact: true,
  });
  await expect(textbox).toBeVisible();

  const chip = page.getByRole("button", { name: "参照範囲" });
  await chip.click();
  const popup = page.getByRole("listbox", { name: "参照範囲" });
  await expect(popup).toBeVisible();

  // Measured 2026-11-19: ポップオーバーは top layer に出るので、矩形の中心を叩けば
  // 中身の要素が返る。入力欄や textarea が返ってくる = 入力欄の下に隠れている、が
  // この検査が捕まえる故障。
  const hitInside = await popup.evaluate((el) => {
    const rect = el.getBoundingClientRect();
    const hit = document.elementFromPoint(
      rect.left + rect.width / 2,
      rect.top + rect.height / 2,
    );
    return hit !== null && el.contains(hit);
  });
  expect(
    hitInside,
    "the scope popup is covered by another element at its own center",
  ).toBe(true);

  // <strong> はフォーカスを奪わない非フォーカス要素なので、外側へのクリックとして
  // 一意に light dismiss だけを試せる。閉じたらチップへフォーカスが戻る。
  await page.locator(".topbar strong").click();
  await expect(popup).toBeHidden();
  await expect(chip).toBeFocused();

  // Escape でも閉じてチップへフォーカスが戻る。light dismiss と自前の Escape
  // 処理が二重に走り得る経路なので、実ブラウザで確かめる。
  await chip.click();
  await expect(popup).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(popup).toBeHidden();
  await expect(chip).toBeFocused();

  // 開いた状態でも横スクロールしない（既存の invariant と同じ条件）。
  await chip.click();
  await expect(popup).toBeVisible();
  for (const size of WIDTHS) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    const overflow = await page.evaluate(() => {
      const root = document.scrollingElement ?? document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    expect(
      overflow,
      `${size.name} scrolls sideways by ${overflow}px with the scope popup open`,
    ).toBeLessThanOrEqual(1);
  }
});

test("a dark choice is dark from the first paint after reload", async ({
  page,
}) => {
  // Measured 2026-11-19: ダークが保存された状態 (= ダークを選んだ直後と同じ状態) で
  // 再読み込みし、描画開始時点の <meta name="color-scheme"> の content と
  // document.documentElement の colorScheme を読む。インラインスクリプトが
  // 保存値を <meta> に書き戻し、CSS の :has() 規則がそれを写し戻さなければ、
  // <meta> 自体が存在せず基底値 light dark のままになる。
  // ブラウザ文脈は既定のライトにしておく — ここをダーク文脈にすると、システムの
  // 暗さだけで通ってしまい、ちらつきの検査として機能しなくなる。
  // なお Vite の開発サーバはスタイルを JS で注入するため、モジュール実行後は
  // data-mode 経路でも colorScheme が dark になりうる。現状コードでも
  // domcontentloaded 以降なら computed colorScheme は dark に見えるため、
  // computed の側は回帰ガードに留め、インラインスクリプトの動作証拠は <meta> の
  // content が担う（<meta> が保存値 dark を持つことは修正前のコードでは成立しない）。
  await page.setViewportSize(WIDTHS[0]);
  await page.addInitScript(() => {
    try {
      localStorage.setItem("locus-theme", "dark");
    } catch {
      // 保存できない環境ではこの検査自体が意味をなさないので、失敗は測定側で出す
    }
  });
  await page.goto("/");
  await page.reload({ waitUntil: "domcontentloaded" });
  const measured = await page.evaluate(() => {
    const meta = document.querySelector<HTMLMetaElement>(
      'meta[name="color-scheme"]',
    );
    return {
      meta: meta?.content ?? null,
      scheme: getComputedStyle(document.documentElement).colorScheme,
    };
  });
  expect(
    measured.meta,
    "the inline script did not write the stored choice into <meta>",
  ).toBe("dark");
  expect(
    measured.scheme,
    "color-scheme when the first paint was requested",
  ).toBe("dark");
});

// T-PH6-116: the source modal is a native <dialog> opened with showModal().
// Its own 35-line Tab trap is gone, so these checks pin the property the trap
// used to guarantee — focus stays inside the modal — in a real browser. The
// file runs these after the earlier checks have rotated test-researcher-1.
test("Tab does not move focus out of the source modal", async ({ page }) => {
  await page.setViewportSize(WIDTHS[0]);
  await signInAgain(page, 1);
  await askSomething(page);
  await openSourceModal(page);
  const focusState = () =>
    page.evaluate(() => {
      // Matches the migrated native <dialog> and the pre-migration
      // [role="dialog"] section, so the same probe measures both builds.
      const dialog = document.querySelector('dialog, [role="dialog"]');
      const active = document.activeElement as HTMLElement | null;
      if (!dialog) return "no-dialog";
      if (!active) return "no-active";
      if (active === document.body) return "body";
      return dialog.contains(active)
        ? "inside"
        : `outside <${active.tagName.toLowerCase()}>`;
    });
  for (let tab = 0; tab < 20; tab++) {
    await page.keyboard.press("Tab");
    expect(await focusState(), `focus after Tab #${tab + 1}`).toBe("inside");
  }
  for (let tab = 0; tab < 20; tab++) {
    await page.keyboard.press("Shift+Tab");
    expect(await focusState(), `focus after Shift+Tab #${tab + 1}`).toBe(
      "inside",
    );
  }
});

test("Escape closes the source modal", async ({ page }) => {
  // Closing on Escape is native <dialog> behaviour; before the migration the
  // modal needed a hand-written key handler for the same effect.
  await page.setViewportSize(WIDTHS[0]);
  await signInAgain(page, 1);
  await askSomething(page);
  const modal = await openSourceModal(page);
  await page.keyboard.press("Escape");
  await expect(modal).toBeHidden();
});

test("the page behind the source modal does not scroll", async ({ page }) => {
  // The modal must not let a wheel over its backdrop move the chat behind it.
  // The conversation is tall enough to scroll, or the check proves nothing.
  await page.setViewportSize(WIDTHS[0]);
  await signInAgain(page, 1);
  for (let turn = 0; turn < 3; turn++) await askSomething(page);
  const messages = page.locator(".messages");
  const scrollable = await messages.evaluate(
    (element) => element.scrollHeight - element.clientHeight,
  );
  expect(
    scrollable,
    "fixture page is not tall enough to scroll",
  ).toBeGreaterThan(0);
  await openSourceModal(page);
  // Opening the modal re-renders the conversation and may scroll it, so the
  // wheel check starts from a known position *after* the modal is open.
  await messages.evaluate((element) => {
    element.scrollTop = 0;
  });
  // The dialog is centred (max width 800px at 1280px), so this point is on
  // the backdrop below-left of it, over the chat that sits behind.
  await page.mouse.move(40, 780);
  await page.mouse.wheel(0, 800);
  await page.waitForTimeout(200);
  const top = await messages.evaluate((element) => element.scrollTop);
  expect(top, "wheel over the backdrop scrolled the text behind").toBe(0);
  const documentTop = await page.evaluate(
    () => (document.scrollingElement ?? document.documentElement).scrollTop,
  );
  expect(documentTop, "the document itself scrolled behind the modal").toBe(0);
});
