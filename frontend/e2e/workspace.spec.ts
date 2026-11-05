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
  const sourceDialog = page.getByRole("dialog", { name: "出典の原文" });
  const close = sourceDialog.getByRole("button", {
    name: "閉じる",
    exact: true,
  });
  const related = sourceDialog.getByRole("button", {
    name: "関連資料を確認",
    exact: true,
  });
  await expect(
    sourceDialog.getByRole("region", { name: "引用箇所 p.1 chunk 1" }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(related).toBeFocused();
  await related.click();
  const relatedRegion = sourceDialog.getByRole("region", { name: "関連資料" });
  await expect(relatedRegion.getByText(/共通語句 \d+件/)).toBeVisible();
  await expect(
    relatedRegion.getByText(/この資料 p.1 → 関連資料 p.1/).first(),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("related-documents.png"),
  });
  await relatedRegion
    .getByRole("button", { name: "合成サンプル_成膜条件.txt" })
    .click();
  await expect(
    sourceDialog.getByRole("region", { name: "引用箇所 p.1 chunk 1" }),
  ).toBeFocused();
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

test("citations open the actual page and chunk and reject stale targets", async ({
  page,
}) => {
  await enter(page, 7);
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("uniqueanchor");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  const citation = page.getByRole("button", {
    name: /合成サンプル_成膜条件.txt · p.2 · chunk 1/,
  });
  await citation.click();
  const dialog = page.getByRole("dialog", { name: "出典の原文" });
  const selected = dialog.getByRole("region", { name: "引用箇所 p.2 chunk 1" });
  await expect(selected).toBeVisible();
  await expect(selected).toBeFocused();
  await expect(selected).toContainText("uniqueanchor");
  await expect(dialog.locator(".source-document-name")).toHaveText(
    "合成サンプル_成膜条件.txt",
  );
  await expect(dialog.locator(".source-document-name")).toBeInViewport();
  await expect(
    dialog.getByRole("button", { name: "閉じる", exact: true }),
  ).toBeInViewport();
  expect(await dialog.evaluate((element) => element.scrollTop)).toBeGreaterThan(
    0,
  );
  await page.screenshot({
    path: test.info().outputPath("citation-target.png"),
  });
  await page.keyboard.press("Escape");
  await expect(citation).toBeFocused();
  await page.route("**/api/documents/*/chunks**", (route) =>
    route.fulfill({ json: [] }),
  );
  await citation.click();
  await expect(page.getByRole("alert")).toContainText(
    "引用箇所が更新または削除",
  );
  await expect(dialog).not.toBeVisible();
});

test("related sources retain keyboard focus while pending and wrap long names", async ({
  page,
}) => {
  await enter(page, 4);
  await page
    .getByRole("textbox", { name: "メッセージ", exact: true })
    .fill("成膜");
  await page.getByRole("button", { name: "送信", exact: true }).click();
  const source = page
    .getByRole("button", { name: /合成サンプル_成膜条件.txt · p./ })
    .first();
  await source.click();
  const dialog = page.getByRole("dialog", { name: "出典の原文" });
  let release!: () => void;
  const responseReady = new Promise<void>((resolve) => {
    release = resolve;
  });
  const longName = "検証用の長い資料名".repeat(18) + ".txt";
  let requests = 0;
  await page.route("**/api/documents/*/related**", async (route) => {
    requests++;
    await responseReady;
    await route.fulfill({
      json: [
        {
          document: { id: "synthetic-target", name: longName },
          method: "lexical-common-terms",
          shared_term_count: 1,
          evidence: [
            {
              term: "成膜",
              source_page: 1,
              target_page: 2,
              source_chunk_id: "source-chunk",
              target_chunk_id: "target-chunk",
            },
          ],
        },
      ],
    });
  });
  const load = dialog.getByRole("button", {
    name: "関連資料を確認",
    exact: true,
  });
  await load.click();
  await expect(
    dialog.getByRole("button", { name: "関連資料を確認中", exact: true }),
  ).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await expect(
    dialog.getByRole("button", { name: "閉じる", exact: true }),
  ).toBeFocused();
  release();
  const target = dialog.getByRole("button", { name: longName });
  await expect(target).toBeVisible();
  expect(requests).toBe(1);
  await page.setViewportSize({ width: 320, height: 900 });
  await expect
    .poll(() =>
      dialog.evaluate((element) => element.scrollWidth <= element.clientWidth),
    )
    .toBe(true);
  await expect
    .poll(() =>
      target.evaluate((element) => element.scrollWidth <= element.clientWidth),
    )
    .toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(source).toBeFocused();
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

test("personal batch uploads report accepted and rejected files accurately", async ({
  page,
}) => {
  await enter(page, 8);
  await page.getByRole("button", { name: "個人資料", exact: true }).click();
  let uploads = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/documents"
    )
      uploads++;
  });
  const picker = page.locator('input[type="file"]');
  await picker.setInputFiles([
    {
      name: "batch-synthetic.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("合成資料の登録確認です。"),
    },
    {
      name: "rejected.exe",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("synthetic"),
    },
  ]);
  await expect(page.getByRole("status")).toContainText(
    "1件の登録を受け付けました",
  );
  await expect(page.getByRole("alert")).toContainText(
    "1件を登録できませんでした",
  );
  await expect(page.getByRole("alert")).toContainText("rejected.exe");
  await expect(
    page.getByRole("button", { name: "batch-synthetic.md", exact: true }),
  ).toBeDisabled();
  expect(uploads).toBe(1);
  await picker.setInputFiles([
    {
      name: "only-rejected.exe",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("synthetic"),
    },
  ]);
  await expect(page.getByRole("alert")).toContainText("only-rejected.exe");
  await expect(page.getByRole("status")).not.toBeVisible();
  expect(uploads).toBe(1);
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
  await page
    .getByRole("button", { name: "合成資料の閲覧担当を編集", exact: true })
    .click();
  await page.getByLabel("ロール名", { exact: true }).fill("合成資料の確認担当");
  await page.getByRole("button", { name: "チャット参照", exact: true }).click();
  await expect(
    page.getByText(/割り当て済みの利用者の操作権限に即時反映/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "ロールの変更を保存", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("ロールを更新しました");
  await page.getByRole("button", { name: "個人資料", exact: true }).click();
  await page.getByRole("button", { name: "公開先", exact: true }).click();
  await expect(
    page.getByRole("option", { name: "合成資料の確認担当", exact: true }),
  ).toBeAttached();
  await expect(page.getByLabel("許可する操作")).toHaveValue("read");
  await expect(page.locator(".publication")).toContainText(
    "研究者」に閲覧のみ",
  );
  const publication = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && request.url().endsWith("/publication"),
  );
  await page
    .getByRole("button", { name: "公開設定を保存", exact: true })
    .click();
  const saved = await publication;
  expect(saved.postDataJSON()).toEqual({
    grants: [{ role: "researcher", operations: ["read"] }],
  });
  await expect(page.locator(".publication")).not.toBeVisible();
  const documentId = new URL(saved.url()).pathname.split("/")[3];
  const readerContext = await page.context().browser()!.newContext();
  try {
    const reader = await readerContext.newPage();
    await enter(reader, 6);
    const base = `http://127.0.0.1:5174/api/documents/${documentId}`;
    expect((await reader.request.get(base)).status()).toBe(200);
    expect((await reader.request.get(`${base}/chunks`)).status()).toBe(200);
    expect((await reader.request.get(`${base}/related`)).status()).toBe(404);
    await reader
      .getByRole("textbox", { name: "メッセージ", exact: true })
      .fill("成膜");
    const message = reader.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/messages"),
    );
    await reader.getByRole("button", { name: "送信", exact: true }).click();
    const result = await (await message).json();
    expect(
      result.citations.some(
        (citation: { document_id: string }) =>
          citation.document_id === documentId,
      ),
    ).toBe(false);
  } finally {
    await readerContext.close();
  }
  await page.getByText("運用・記録", { exact: true }).click();
  await page.getByRole("button", { name: "操作記録", exact: true }).click();
  await expect(page.locator(".list")).toContainText("role.create");
  await expect(page.locator(".list")).toContainText("role.update");
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
