import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const initialViewportWidth = window.innerWidth;

function setViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", {
    value: width,
    configurable: true,
    writable: true,
  });
}

const requests: { path: string; options?: RequestInit }[] = [];
beforeEach(() => {
  requests.length = 0;
  localStorage.clear();
  setViewportWidth(initialViewportWidth);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      requests.push({ path, options });
      let data: unknown = [];
      if (path.endsWith("/auth/me"))
        data = {
          id: "alice",
          username: "alice",
          system_admin: false,
          must_rotate: false,
        };
      if (path.endsWith("/projects"))
        data = [
          {
            id: "project",
            org_id: "org",
            name: "検証",
            role: "researcher",
            permissions: ["read", "retrieve", "upload"],
          },
        ];
      if (path === "/api/conversations" && options?.method === "POST")
        data = { id: "conversation", project_id: "project" };
      if (path.endsWith("/messages"))
        data = { id: "message", text: "成膜", scope: "all", citations: [] };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});

describe("approved chat interaction baseline", () => {
  it("warns that a queued question's position may change", async () => {
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      if (String(input).endsWith("/messages") && options?.method === "POST")
        return new Response(JSON.stringify({ job_id: "job-1", status: "queued", text: "成膜" }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      return originalFetch(input, options);
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    expect(await screen.findByText(/待ち位置は混雑により変動します/)).toBeVisible();
  });
  it("renders a streamed answer while it arrives and keeps the committed message", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const frame = (event: string, data: unknown) =>
      `event: ${event}
data: ${JSON.stringify(data)}

`;
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/messages/stream")) {
        const encoder = new TextEncoder();
        const body = new ReadableStream({
          async start(controller) {
            controller.enqueue(encoder.encode(frame("start", { job_id: "job-1" })));
            controller.enqueue(encoder.encode(frame("delta", { text: "成膜条件は" })));
            await gate;
            controller.enqueue(encoder.encode(frame("delta", { text: "180°Cです" })));
            controller.enqueue(
              encoder.encode(
                frame("message", {
                  id: "message-1",
                  text: "成膜",
                  scope: "all",
                  answer: "成膜条件は180°Cです",
                  model: "fixture:latest",
                  citations: [],
                }),
              ),
            );
            controller.close();
          },
        });
        return new Response(body, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return originalFetch(input, options);
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    // The first fragment is visible before the answer is committed.
    expect(await screen.findByText("成膜条件は")).toBeVisible();
    expect(screen.getByRole("button", { name: "この質問を取り消す" })).toBeVisible();
    release();
    expect(await screen.findByText("成膜条件は180°Cです")).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByText(/途中経過を表示しています/)).toBeNull(),
    );
    expect(
      requests.filter((request) => request.path.endsWith("/messages")),
    ).toHaveLength(0);
  });

  it("keeps a question the server queued mid-stream without resending it", async () => {
    const frame = (event: string, data: unknown) =>
      `event: ${event}
data: ${JSON.stringify(data)}

`;
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/messages/stream"))
        return new Response(
          frame("start", { job_id: "stream-1" }) +
            frame("queued", {
              job_id: "job-2",
              status: "queued",
              text: "成膜",
            }),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        );
      if (path.startsWith("/api/chat-jobs/"))
        return new Response(
          JSON.stringify({
            id: "job-2",
            conversation_id: "conversation",
            status: "queued",
            detail: "",
            message_id: null,
            cancel_requested: false,
            created: 1,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      return originalFetch(input, options);
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    expect(await screen.findByText(/順番待ちです/)).toBeVisible();
    expect(
      requests.filter((request) => request.path.endsWith("/messages")),
    ).toHaveLength(0);
  });

  it("falls back to the ordinary request when streaming is unavailable", async () => {
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      if (path.endsWith("/messages/stream")) {
        requests.push({ path, options });
        return new Response(
          JSON.stringify({ detail: "逐次表示は利用できません。通常の送信に切り替えます" }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        );
      }
      return originalFetch(input, options);
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    await screen.findByRole("heading", {
      name: "参照できる記述が見つかりませんでした",
    });
    expect(
      requests.filter((request) => request.path.endsWith("/messages/stream")),
    ).toHaveLength(1);
    expect(
      requests.filter((request) => request.path.endsWith("/messages")),
    ).toHaveLength(1);
  });

  it("preserves the sidebar control and excludes collapsed navigation from focus", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "資料を調べる" });
    fireEvent.click(screen.getByRole("button", { name: "サイドバーを閉じる" }));
    expect(
      screen.getByRole("button", { name: "サイドバーを開く" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector("#workspace-sidebar")).toHaveAttribute(
      "inert",
    );
    fireEvent.click(screen.getByRole("button", { name: "サイドバーを開く" }));
    expect(screen.getByRole("button", { name: "個人資料" })).toBeVisible();
    expect(
      screen.queryByText("ここへドラッグ＆ドロップ"),
    ).not.toBeInTheDocument();
  });

  it("does not submit during Japanese IME composition or Shift+Enter", async () => {
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).not.toBeDisabled());
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.keyDown(field, { key: "Enter", isComposing: true, keyCode: 229 });
    fireEvent.keyDown(field, { key: "Enter", shiftKey: true });
    expect(
      requests.filter((request) => request.path.endsWith("/messages")),
    ).toHaveLength(0);
    expect(field).toHaveValue("成膜");
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    await screen.findByRole("heading", {
      name: "参照できる記述が見つかりませんでした",
    });
    expect(
      requests.filter((request) => request.path.endsWith("/messages")),
    ).toHaveLength(1);
  });

  it("renders an unambiguous retrieved markdown table with accessible headers", async () => {
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/auth/me"))
        return new Response(
          JSON.stringify({
            id: "alice",
            username: "alice",
            system_admin: false,
            must_rotate: false,
          }),
        );
      if (path.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            {
              id: "project",
              org_id: "org",
              name: "検証",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
          ]),
        );
      if (path.endsWith("/messages"))
        return new Response(
          JSON.stringify({
            id: "message-table",
            text: "条件を比較",
            scope: "all",
            citations: [
              {
                id: "citation-table",
                document_id: "document-table",
                page: 2,
                ordinal: 3,
                name: "合成資料.md",
                text: "| 項目 | 条件A | 条件B |\n| --- | --- | --- |\n| 温度 | 180°C | 200°C |\n| 注記 | <script>文字列</script> | 記録なし |\n",
              },
              {
                id: "citation-tsv",
                document_id: "document-table",
                page: 3,
                ordinal: 4,
                name: "合成資料.tsv",
                text: "比較項目\t条件A\t条件B\n温度\t180°C\t200°C",
              },
            ],
          }),
        );
      return new Response(JSON.stringify([]));
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    fireEvent.change(field, { target: { value: "条件を比較" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));

    const table = await screen.findByRole("table", {
      name: "合成資料.md p.2 chunk 3 の表",
    });
    expect(screen.getAllByRole("columnheader")).toHaveLength(6);
    expect(screen.getByRole("columnheader", { name: "項目" })).toHaveAttribute(
      "scope",
      "col",
    );
    expect(table.querySelector('th[scope="row"]')).toHaveTextContent("温度");
    expect(table.closest('[role="region"]')).toHaveAttribute("tabindex", "0");
    expect(table).toHaveTextContent("180°C");
    const tsvTable = screen.getByRole("table", {
      name: "合成資料.tsv p.3 chunk 4 の表",
    });
    expect(tsvTable).toHaveTextContent("200°C");
    expect(table.querySelector("script")).toBeNull();
    expect(table).toHaveTextContent("<script>文字列</script>");
  });

  it("keeps ambiguous retrieved tabular text in the existing plain rendering", async () => {
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/auth/me"))
        return new Response(
          JSON.stringify({
            id: "alice",
            username: "alice",
            system_admin: false,
            must_rotate: false,
          }),
        );
      if (path.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            {
              id: "project",
              org_id: "org",
              name: "検証",
              role: "researcher",
              permissions: ["read", "retrieve"],
            },
          ]),
        );
      if (path.endsWith("/messages"))
        return new Response(
          JSON.stringify({
            id: "message-ambiguous",
            text: "条件を確認",
            scope: "all",
            citations: [
              {
                id: "citation-ambiguous",
                document_id: "document-ambiguous",
                page: 1,
                ordinal: 1,
                name: "曖昧な資料.txt",
                text: "| 項目 | 条件A |\n| --- | --- |\n| 温度 | 180°C | 200°C |\n",
              },
            ],
          }),
        );
      return new Response(JSON.stringify([]));
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    fireEvent.change(field, { target: { value: "条件を確認" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));

    expect(await screen.findByText(/\| 項目 \| 条件A \|/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "資料に見つかった記述" })).toBeVisible();
  });

  it("keeps a draft when a file is rejected and allows individual removal", async () => {
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).not.toBeDisabled());
    fireEvent.change(field, { target: { value: "残す下書き" } });
    const input = screen.getByLabelText("添付ファイルを選択");
    fireEvent.change(input, {
      target: { files: [new File(["binary"], "bad.exe")] },
    });
    await screen.findByText("失敗", { exact: true });
    expect(field).toHaveValue("残す下書き");
    fireEvent.click(screen.getByRole("button", { name: "bad.exeを取り外す" }));
    await waitFor(() =>
      expect(screen.queryByText("bad.exe")).not.toBeInTheDocument(),
    );
    expect(field).toHaveValue("残す下書き");
  });

  it("does not acknowledge personal uploads that all failed validation", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "個人資料" }));
    await screen.findByRole("button", { name: "資料を追加" });
    const input =
      document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input!, {
      target: { files: [new File(["synthetic"], "bad.exe")] },
    });
    await screen.findByRole("alert");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(
      requests.filter(
        (request) =>
          request.path === "/api/documents" &&
          request.options?.method === "POST",
      ),
    ).toHaveLength(0);
  });

  it("preserves mixed upload outcomes when refreshing the library fails", async () => {
    const original = vi.mocked(fetch).getMockImplementation()!;
    let uploads = 0;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      if (path === "/api/documents" && options?.method === "POST") {
        uploads++;
        return new Response(
          JSON.stringify({ id: "new-document", status: "queued" }),
          { status: 201 },
        );
      }
      if (uploads && path.startsWith("/api/documents?"))
        return new Response(
          JSON.stringify({ detail: "更新を確認できません" }),
          { status: 503 },
        );
      return original(input, options);
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "個人資料" }));
    await screen.findByRole("button", { name: "資料を追加" });
    const valid = new File(["synthetic"], "accepted.txt");
    Object.defineProperty(valid, "arrayBuffer", {
      value: async () => new TextEncoder().encode("synthetic").buffer,
    });
    fireEvent.change(
      document.querySelector<HTMLInputElement>('input[type="file"]')!,
      {
        target: { files: [valid, new File(["synthetic"], "rejected.exe")] },
      },
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "1件の登録を受け付けました",
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "一覧の更新に失敗しました",
      ),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "1件を登録できませんでした",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("rejected.exe");
    expect(uploads).toBe(1);
  });

  it("displays accurate delegation guidance on settings and role editor pages", async () => {
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/auth/me"))
        return new Response(
          JSON.stringify({
            id: "alice",
            username: "alice",
            system_admin: false,
            must_rotate: false,
          }),
        );
      if (path.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            {
              id: "project",
              org_id: "org",
              name: "検証",
              role: "project_lead",
              permissions: ["read", "retrieve", "upload", "manage_roles"],
            },
          ]),
        );
      if (path.endsWith("/projects/project/roles"))
        return new Response(
          JSON.stringify({
            templates: [],
            custom: [],
            allowed_permissions: ["read", "retrieve"],
          }),
        );
      return new Response(JSON.stringify([]));
    });
    render(<App />);
    fireEvent.click(
      await screen.findByRole("button", { name: "モデル・同時利用" }),
    );
    expect(
      await screen.findByText(
        "LAN公開、回復、組織単位の委任拡張、保存期間は承認待ちです。プロジェクト単位の権限委任は「管理委任」から設定できます。",
      ),
    ).toBeVisible();
    expect(
      screen.queryByText("LAN公開、回復、管理委任、保存期間は承認待ちです。"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "役割・管理権限" }));
    expect(
      await screen.findByText(
        "ロールは現在のプロジェクト内で有効です。管理操作の権限は委任できません。",
      ),
    ).toBeVisible();
    expect(
      screen.queryByText(/管理権限の委任は無効です/),
    ).not.toBeInTheDocument();
  });

  it("moves focus to the page heading when the keyboard user changes pages", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "資料を調べる" });
    fireEvent.click(screen.getByRole("button", { name: "共有資料" }));
    const heading = await screen.findByRole("heading", { name: "共有資料" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  it("names the target of repeated row actions with the document or conversation", async () => {
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/auth/me"))
        return new Response(
          JSON.stringify({
            id: "alice",
            username: "alice",
            system_admin: false,
            must_rotate: false,
          }),
        );
      if (path.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            {
              id: "project",
              org_id: "org",
              name: "検証",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
          ]),
        );
      if (path.includes("/documents?"))
        return new Response(
          JSON.stringify([
            {
              id: "document-1",
              name: "合成サンプル.txt",
              kind: "shared",
              status: "ready",
              owned: true,
            },
          ]),
        );
      return new Response(JSON.stringify([]));
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "共有資料" }));
    const remove = await screen.findByRole("button", { name: "削除" });
    const described = remove.getAttribute("aria-describedby");
    expect(described).toBeTruthy();
    expect(document.getElementById(described!)).toHaveTextContent(
      "合成サンプル.txt",
    );
  });

  it("closes the overlay sidebar with Escape and returns focus to its control", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "資料を調べる" });
    const toggle = screen.getByRole("button", { name: "サイドバーを閉じる" });
    setViewportWidth(375);
    const sidebar = document.querySelector("#workspace-sidebar")!;
    fireEvent.keyDown(sidebar, { key: "Escape" });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "サイドバーを開く" }),
      ).toHaveAttribute("aria-expanded", "false"),
    );
    expect(toggle).toHaveFocus();
  });

  it("keeps watching and allows cancelling a document while it is indexing", async () => {
    let reads = 0;
    const indexingDocument = {
      id: "doc-1",
      status: "indexing",
      name: "indexing.txt",
      project_id: "project",
      kind: "personal",
      reason: "",
      conversation_id: null,
      created: 1,
      owned: true,
    };
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      if (path.includes("/documents?project_id=")) {
        reads++;
        requests.push({ path, options });
        return new Response(JSON.stringify([indexingDocument]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return originalFetch(input, options);
    });
    render(<App />);
    await screen.findByRole("button", { name: "取り込み状況" });
    fireEvent.click(screen.getByRole("button", { name: "取り込み状況" }));
    expect(await screen.findByText("索引中")).toBeVisible();
    const cancel = screen.getByRole("button", { name: "取消" });
    expect(cancel).toBeVisible();
    // The indexing stage is still progressing, so the view keeps polling.
    const before = reads;
    vi.useFakeTimers();
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(reads).toBeGreaterThan(before);
    vi.useRealTimers();
    fireEvent.click(cancel);
    await waitFor(() =>
      expect(
        requests.some((request) => request.path.endsWith("/doc-1/cancel")),
      ).toBe(true),
    );
  });

  it("keeps the desktop sidebar open when Escape is pressed inside it", async () => {
    render(<App />);
    await screen.findByRole("heading", { name: "資料を調べる" });
    setViewportWidth(1280);
    const sidebar = document.querySelector("#workspace-sidebar")!;
    fireEvent.keyDown(sidebar, { key: "Escape" });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "サイドバーを閉じる" }),
      ).toHaveAttribute("aria-expanded", "true"),
    );
  });
});

// The owner asked on 2026-11-17 for one standing line above the conversation:
// whether or not an answer cites a source, the product can be wrong and the
// reader should check. The exact wording is the requirement, so it is repeated
// here rather than imported.
const FALLIBILITY_NOTICE =
  "Locusは間違えることがあります。重要な情報は確認してください。";

describe("chat fallibility notice", () => {
  it("shows the exact notice above the conversation", async () => {
    render(<App />);
    await screen.findByRole("textbox", { name: "メッセージ" });
    const notice = screen.getByText(FALLIBILITY_NOTICE);
    expect(notice).toBeVisible();
    expect(notice).toHaveClass("chat-notice");
    // The message list is what scrolls once the composer is fixed, so the
    // notice has to sit outside it or the conversation would carry it away.
    const messages = document.querySelector(".messages")!;
    expect(messages).not.toContainElement(notice);
    expect(
      notice.compareDocumentPosition(messages) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // A static caution: no repeated announcement and no warning icon.
    expect(notice).not.toHaveAttribute("aria-live");
    expect(notice.closest("[aria-live]")).toBeNull();
    expect(notice.querySelector("svg, [role='img']")).toBeNull();
  });

  it("keeps the notice while the conversation grows", async () => {
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    let posted = 0;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      if (String(input).endsWith("/messages") && options?.method === "POST")
        return new Response(
          JSON.stringify({
            id: `message-${++posted}`,
            text: "成膜",
            scope: "all",
            citations: [],
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      return originalFetch(input, options);
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    for (let turn = 1; turn <= 4; turn++) {
      await waitFor(() => expect(field).toBeEnabled());
      fireEvent.change(field, { target: { value: `質問${turn}` } });
      fireEvent.click(screen.getByRole("button", { name: "送信" }));
      await waitFor(() =>
        expect(document.querySelectorAll(".messages .exchange")).toHaveLength(
          turn,
        ),
      );
    }
    expect(screen.getByText(FALLIBILITY_NOTICE)).toBeVisible();
  });

  it("keeps the per-answer footnote beside the notice", async () => {
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/auth/me"))
        return new Response(
          JSON.stringify({
            id: "alice",
            username: "alice",
            system_admin: false,
            must_rotate: false,
          }),
        );
      if (path.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            {
              id: "project",
              org_id: "org",
              name: "検証",
              role: "researcher",
              permissions: ["read", "retrieve"],
            },
          ]),
        );
      if (path.endsWith("/messages"))
        return new Response(
          JSON.stringify({
            id: "message-1",
            text: "成膜",
            scope: "all",
            citations: [
              {
                id: "citation-1",
                document_id: "document-1",
                page: 1,
                ordinal: 2,
                name: "合成資料.md",
                text: "成膜温度は180°Cです。",
              },
            ],
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      return new Response(JSON.stringify([]));
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    // This is the per-answer provenance note, not the standing caution: the
    // two have different jobs and both have to stay.
    expect(
      await screen.findByText(
        "検索で抽出した原文です。AI生成の回答ではありません。判断には元資料を確認してください。",
      ),
    ).toBeVisible();
    expect(screen.getByText(FALLIBILITY_NOTICE)).toBeVisible();
  });
});
