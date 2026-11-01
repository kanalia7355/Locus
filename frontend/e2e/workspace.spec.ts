import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";

async function enter(page: Page, index: number) {
  await page.goto("/");
  await page.getByLabel("利用者ID").fill(`test-researcher-${index}`);
  await page
    .getByLabel("パスワード", { exact: true })
    .fill("Synthetic-test-password-01!");
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "仮パスワードの変更" }),
  ).toBeVisible();
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
  await expect(
    page.getByRole("heading", { name: "資料を調べる", exact: true }),
  ).toBeVisible();
}

test("first login, source retrieval, history and logout use actual API", async ({
  page,
}) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  await enter(page, 1);
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("成膜条件を比較");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();
  await expect(
    page.getByText("AI生成の回答ではありません", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /合成サンプル_成膜条件.txt · p./ })
    .first()
    .click();
  await expect(page.getByRole("dialog", { name: "出典の原文" })).toBeVisible();
  await expect(
    page.getByRole("dialog").getByText("処理温度180°C", { exact: false }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "調査履歴", exact: true }).click();
  await page.getByRole("button", { name: /調査 ·/ }).click();
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "ログアウト", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "ログイン", exact: true }),
  ).toBeVisible();
  expect(failures).toEqual([]);
});

test("attachments preserve draft, quarantine, remove, and share the drop path", async ({
  page,
}) => {
  await enter(page, 2);
  const input = page.getByRole("textbox", { name: "メッセージ", exact: true });
  await input.fill("消してはいけない下書き");
  await page
    .locator("input[type=file]")
    .first()
    .setInputFiles({
      name: "sample.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("synthetic text"),
    });
  await expect(page.getByText("隔離中", { exact: true })).toBeVisible();
  await expect(input).toHaveValue("消してはいけない下書き");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("参照できない添付");
  await page
    .getByRole("button", { name: "sample.txtを取り外す", exact: true })
    .click();
  await expect(page.getByText("sample.txt", { exact: true })).not.toBeVisible();
  const data = await page.evaluateHandle(() => {
    const data = new DataTransfer();
    data.items.add(
      new File(["synthetic drop"], "drop.md", { type: "text/markdown" }),
    );
    return data;
  });
  await page.locator(".composer").dispatchEvent("drop", { dataTransfer: data });
  await expect(page.getByText("drop.md", { exact: true })).toBeVisible();
  await expect(input).toHaveValue("消してはいけない下書き");
  await page
    .getByRole("button", { name: "drop.mdを取り外す", exact: true })
    .click();
  await expect(page.getByText("drop.md", { exact: true })).not.toBeVisible();
  await input.fill("成膜");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();
});

test("sidebar, long names, mobile widths and reduced motion", async ({
  page,
}) => {
  await enter(page, 3);
  await page
    .getByRole("button", { name: "サイドバーを閉じる", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "サイドバーを開く", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#workspace-sidebar")).toHaveAttribute("inert", "");
  await page
    .getByRole("button", { name: "サイドバーを開く", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "個人資料", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("成膜");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "資料に見つかった記述" }),
  ).toBeVisible();
  for (const width of [320, 375, 414, 768, 1024]) {
    await page.setViewportSize({ width, height: 1000 });
    if (
      width < 768 &&
      (await page
        .getByRole("button", { name: "サイドバーを閉じる", exact: true })
        .isVisible())
    )
      await page
        .getByRole("button", { name: "サイドバーを閉じる", exact: true })
        .click();
    if (
      width >= 768 &&
      (await page
        .getByRole("button", { name: "サイドバーを開く", exact: true })
        .isVisible())
    ) {
      await page
        .getByRole("button", { name: "サイドバーを開く", exact: true })
        .click();
    }
    await expect
      .poll(() =>
        page
          .locator(".main")
          .evaluate((element) =>
            Math.round(element.getBoundingClientRect().left),
          ),
      )
      .toBe(width < 768 ? 0 : 220);
    if (width < 768)
      await expect
        .poll(() =>
          page
            .locator(".sidebar")
            .evaluate((element) =>
              Math.round(element.getBoundingClientRect().right),
            ),
        )
        .toBe(0);
    await page.mouse.move(width - 4, 995);
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await page.screenshot({
      path: `test-results/workspace-${width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 320, height: 1000 });
  await page
    .getByRole("button", { name: "サイドバーを閉じる", exact: true })
    .click();
  const longName = "長い合成資料名".repeat(15) + ".txt";
  await page
    .locator("input[type=file]")
    .first()
    .setInputFiles({
      name: longName,
      mimeType: "text/plain",
      buffer: Buffer.from("synthetic"),
    });
  await expect(page.getByText("隔離中", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page
      .locator(".workspace")
      .evaluate((element) => getComputedStyle(element).transitionDuration),
  ).toBe("0s");
});

test("role editor previews scoped subsets and administrator audit is redacted", async ({
  page,
}) => {
  await enter(page, 0);
  await page
    .getByRole("button", { name: "役割・管理権限", exact: true })
    .click();
  await page
    .getByLabel("新しいロール名", { exact: true })
    .fill("合成資料の閲覧担当");
  await expect(page.locator(".permission-preview")).toContainText(
    "現在のプロジェクト",
  );
  await page.getByRole("button", { name: "ロールを作成", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("ロールを作成しました");
  await page.getByText("運用・記録", { exact: true }).click();
  await page.getByRole("button", { name: "操作記録", exact: true }).click();
  await expect(page.locator(".list")).toContainText("role.create");
  await expect(page.locator(".list")).not.toContainText(
    "Synthetic-test-password",
  );
});

test("development server rejects hostile and absent mutation origins", async ({
  request,
}) => {
  for (const origin of ["", "null", "https://hostile.example"]) {
    const response = await request.post("/api/auth/logout", {
      headers: origin ? { Origin: origin } : {},
    });
    expect(response.status()).toBe(403);
  }
  expect(
    (await request.get("/", { headers: { Host: "hostile.example" } })).status(),
  ).toBe(403);
});
