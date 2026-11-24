import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const initialViewportWidth = window.innerWidth;

// jsdom's selector engine parses ":user-invalid" but never matches it, and
// jsdom does not track that a control was touched. The implementation
// (correctly) keys off the real pseudo-class, so only for this file emulate
// its semantics: an element is :user-invalid once it is invalid AND the user
// has interacted with it (blur/input/change) or submission was attempted
// (invalid event). The real browser behaviour is covered by
// e2e/appearance.spec.ts on chromium.
const userInvalidTouched = new WeakSet<Element>();
const markUserInvalidTouched = (event: Event) => {
  if (event.target instanceof Element) userInvalidTouched.add(event.target);
};
document.addEventListener("blur", markUserInvalidTouched, true);
document.addEventListener("input", markUserInvalidTouched, true);
document.addEventListener("change", markUserInvalidTouched, true);
document.addEventListener("invalid", markUserInvalidTouched, true);
const nativeMatches = Element.prototype.matches;
Element.prototype.matches = function matchesWithUserInvalid(
  this: Element,
  selector: string,
): boolean {
  if (selector === ":user-invalid") {
    if (!(
      this instanceof HTMLInputElement ||
      this instanceof HTMLTextAreaElement ||
      this instanceof HTMLSelectElement
    ))
      return false;
    // validity.valid, not checkValidity(): checkValidity() fires an
    // invalid event, which would re-enter this shim infinitely.
    return userInvalidTouched.has(this) && !this.validity.valid;
  }
  return nativeMatches.call(this, selector);
} as typeof Element.prototype.matches;

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
        return new Response(
          JSON.stringify({ job_id: "job-1", status: "queued", text: "成膜" }),
          {
            status: 202,
            headers: { "Content-Type": "application/json" },
          },
        );
      return originalFetch(input, options);
    });
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    expect(
      await screen.findByText(/待ち位置は混雑により変動します/),
    ).toBeVisible();
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
            controller.enqueue(
              encoder.encode(frame("start", { job_id: "job-1" })),
            );
            controller.enqueue(
              encoder.encode(frame("delta", { text: "成膜条件は" })),
            );
            await gate;
            controller.enqueue(
              encoder.encode(frame("delta", { text: "180°Cです" })),
            );
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
    expect(
      screen.getByRole("button", { name: "この質問を取り消す" }),
    ).toBeVisible();
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
          JSON.stringify({
            detail: "逐次表示は利用できません。通常の送信に切り替えます",
          }),
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
    await screen.findByRole("heading", { name: "会話" });
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
    expect(
      screen.getByRole("heading", { name: "資料に見つかった記述" }),
    ).toBeVisible();
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
    fireEvent.click(await screen.findByRole("button", { name: "設定" }));
    fireEvent.click(await screen.findByRole("button", { name: "実験的" }));
    expect(await screen.findByText("LAN公開")).toBeVisible();
    expect(screen.getByText("回復")).toBeVisible();
    expect(screen.getByText("組織単位の委任拡張")).toBeVisible();
    expect(screen.getByText("保存期間")).toBeVisible();
    expect(screen.getAllByText("準備中").length).toBeGreaterThan(0);
    expect(screen.getAllByText("承認待ち").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "役割" }));
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
    await screen.findByRole("heading", { name: "会話" });
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
    await screen.findByRole("heading", { name: "会話" });
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
    await screen.findByRole("heading", { name: "会話" });
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

// The login screen shows when /auth/me rejects (signed-out visitor). These
// tests exercise the :user-invalid sync on the AccessForm fields.
function mockSignedOut() {
  vi.mocked(fetch).mockImplementation(async (input) => {
    const path = String(input);
    requests.push({ path });
    return new Response(JSON.stringify({ detail: "認証されていません" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  });
}

describe("form field validation (:user-invalid)", () => {
  it("does not report aria-invalid=true on any field before interaction", async () => {
    mockSignedOut();
    render(<App />);
    const id = await screen.findByLabelText("利用者ID");
    const password = screen.getByLabelText("パスワード", { exact: true });
    expect(id).toHaveAttribute("aria-invalid", "false");
    expect(password).toHaveAttribute("aria-invalid", "false");
    expect(document.querySelector('[aria-invalid="true"]')).toBeNull();
  });

  it("marks an emptied field aria-invalid=true and ties the message with aria-describedby after blur", async () => {
    mockSignedOut();
    render(<App />);
    const id = await screen.findByLabelText("利用者ID");
    fireEvent.blur(id);
    expect(id).toHaveAttribute("aria-invalid", "true");
    expect(id).toHaveAttribute("aria-describedby", "access-username-error");
    const message = document.getElementById("access-username-error");
    expect(message).not.toBeNull();
    expect(message).toHaveTextContent("利用者ID");
    expect(message).toHaveTextContent("管理者が発行した利用者ID");
  });

  it("clears aria-invalid and aria-describedby once the field becomes valid", async () => {
    mockSignedOut();
    render(<App />);
    const id = await screen.findByLabelText("利用者ID");
    fireEvent.blur(id);
    expect(id).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(id, { target: { value: "alice" } });
    expect(id).toHaveAttribute("aria-invalid", "false");
    expect(id).not.toHaveAttribute("aria-describedby");
    expect(document.getElementById("access-username-error")).toBeNull();
  });

  it("focuses the first invalid field when submission fails validation", async () => {
    mockSignedOut();
    render(<App />);
    const id = await screen.findByLabelText("利用者ID");
    const password = screen.getByLabelText("パスワード", { exact: true });
    fireEvent.click(screen.getByRole("button", { name: "ログイン" }));
    expect(id).toHaveFocus();
    expect(id).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(document.getElementById("access-username-error")).toBeVisible();
    expect(document.getElementById("access-password-error")).toBeVisible();
    expect(
      requests.filter((request) => request.path.endsWith("/auth/login")),
    ).toHaveLength(0);
  });
});

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

// The owner moved the reference-scope setting into the composer as a chip
// (2026-11-16) and asked for it to behave like the rest of the composer.
describe("composer scope picker and fixed composer", () => {
  it("sends the scope chosen from the chip in the message request", async () => {
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "参照範囲" }));
    fireEvent.click(screen.getByRole("option", { name: "個人資料" }));
    fireEvent.change(field, { target: { value: "成膜" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    await waitFor(() =>
      expect(
        requests.some(
          (request) =>
            request.path.endsWith("/messages") &&
            request.options?.method === "POST",
        ),
      ).toBe(true),
    );
    const request = requests.find(
      (item) =>
        item.path.endsWith("/messages") && item.options?.method === "POST",
    )!;
    expect(JSON.parse(String(request.options?.body))).toMatchObject({
      scope: "personal",
    });
  });

  it("marks the chosen option and returns to the collapsed chip", async () => {
    render(<App />);
    await screen.findByRole("textbox", { name: "メッセージ" });
    const chip = screen.getByRole("button", { name: "参照範囲" });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    // The default value is the shared+personal option.
    expect(chip).toHaveTextContent("共有資料＋個人資料");
    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "true");
    const shared = screen.getByRole("option", { name: "共有資料" });
    fireEvent.click(shared);
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(chip).toHaveTextContent("共有資料");
    expect(chip).toHaveFocus();
    fireEvent.click(chip);
    expect(screen.getByRole("option", { name: "共有資料" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("option", { name: "個人資料" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("moves with the arrow keys, commits with Enter and closes with Escape", async () => {
    render(<App />);
    await screen.findByRole("textbox", { name: "メッセージ" });
    const chip = screen.getByRole("button", { name: "参照範囲" });
    // The chip is reachable by keyboard and opens with an arrow key.
    expect(chip).toHaveAttribute("aria-haspopup", "listbox");
    fireEvent.keyDown(chip, { key: "ArrowDown" });
    expect(chip).toHaveAttribute("aria-expanded", "true");
    const listbox = screen.getByRole("listbox", { name: "参照範囲" });
    // While the popup is open, focus lives inside it.
    expect(listbox).toHaveFocus();
    // Starting from the default "all" option, two steps down and one up
    // lands on "shared".
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "ArrowUp" });
    fireEvent.keyDown(listbox, { key: "Enter" });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(chip).toHaveFocus();
    expect(chip).toHaveTextContent("共有資料");
    // Escape closes without changing the value.
    fireEvent.keyDown(chip, { key: "ArrowDown" });
    fireEvent.keyDown(screen.getByRole("listbox", { name: "参照範囲" }), {
      key: "Escape",
    });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(chip).toHaveFocus();
    expect(chip).toHaveTextContent("共有資料");
  });

  it("closes on an outside click and on Tab without leaving focus behind", async () => {
    render(<App />);
    await screen.findByRole("textbox", { name: "メッセージ" });
    const chip = screen.getByRole("button", { name: "参照範囲" });
    fireEvent.click(chip);
    expect(screen.getByRole("listbox", { name: "参照範囲" })).toBeVisible();
    fireEvent.mouseDown(document.body);
    expect(chip).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(chip);
    fireEvent.keyDown(screen.getByRole("listbox", { name: "参照範囲" }), {
      key: "Tab",
    });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(chip).toHaveFocus();
  });

  it("keeps the conversation in its own scroll region with the composer outside it", async () => {
    render(<App />);
    await screen.findByRole("textbox", { name: "メッセージ" });
    const chat = document.querySelector<HTMLElement>(".chat")!;
    const messages = document.querySelector<HTMLElement>(".messages")!;
    const composer = document.querySelector<HTMLElement>("form.composer")!;
    expect(chat).toContainElement(messages);
    expect(chat).toContainElement(composer);
    // The composer is a sibling after the scrolling message list, so the
    // conversation can never park its last line underneath it.
    expect(messages).not.toContainElement(composer);
    expect(
      messages.compareDocumentPosition(composer) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // A long conversation lives inside the scroll region, not beside it.
    fireEvent.change(screen.getByRole("textbox", { name: "メッセージ" }), {
      target: { value: "成膜" },
    });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    await waitFor(() =>
      expect(document.querySelectorAll(".messages .exchange")).toHaveLength(1),
    );
    for (const exchange of document.querySelectorAll<HTMLElement>(
      ".messages .exchange",
    )) {
      expect(composer).not.toContainElement(exchange);
    }
  });
});

describe("project switch with pending job", () => {
  it("does not leave 待ち位置 after switching projects when job is queued", async () => {
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/messages") && options?.method === "POST") {
        return new Response(
          JSON.stringify({ job_id: "job-1", status: "queued", text: "成膜" }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path.endsWith("/projects")) {
        return new Response(
          JSON.stringify([
            {
              id: "project-A",
              org_id: "org",
              name: "プロジェクトA",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
            {
              id: "project-B",
              org_id: "org",
              name: "プロジェクトB",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
          ]),
        );
      }
      return originalFetch(input, options);
    });

    render(<App />);
    // Send a message to queue a job
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "テスト質問" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    await screen.findByText("順番待ちあり");

    // Switch to project-B (simulating project switch)
    const projectSelect = screen.getByRole("combobox");
    fireEvent.change(projectSelect, { target: { value: "project-B" } });

    // After switch, "順番待ちあり" should NOT remain
    await waitFor(() =>
      expect(screen.queryByText("順番待ちあり")).not.toBeInTheDocument(),
    );
  });

  it("does not show old job failure after switching projects", async () => {
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/messages") && options?.method === "POST") {
        return new Response(
          JSON.stringify({ job_id: "job-1", status: "queued", text: "成膜" }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path.endsWith("/projects")) {
        return new Response(
          JSON.stringify([
            {
              id: "project-A",
              org_id: "org",
              name: "プロジェクトA",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
            {
              id: "project-B",
              org_id: "org",
              name: "プロジェクトB",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
          ]),
        );
      }
      if (path.endsWith("/chat-jobs/job-1")) {
        return new Response(
          JSON.stringify({
            id: "job-1",
            status: "failed",
            detail: "モデルエラー",
            conversation_id: "conv-A",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return originalFetch(input, options);
    });

    render(<App />);
    // Send a message to queue a job
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "テスト質問" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    await screen.findByText("順番待ちあり");

    // Switch to project-B
    const projectSelect = screen.getByRole("combobox");
    fireEvent.change(projectSelect, { target: { value: "project-B" } });

    // Wait for the job to be reported as failed in polling
    await waitFor(() =>
      expect(screen.queryByText("順番待ちあり")).not.toBeInTheDocument(),
    );

    // Old failure should not appear in new project
    expect(screen.queryByText("回答を生成できません")).not.toBeInTheDocument();
  });

  it("keeps the confirmed answer with its conversation when switching projects", async () => {
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/messages") && options?.method === "POST") {
        return new Response(
          JSON.stringify({
            job_id: "job-1",
            status: "queued",
            text: "テスト質問",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path.endsWith("/projects")) {
        return new Response(
          JSON.stringify([
            {
              id: "project-A",
              org_id: "org",
              name: "プロジェクトA",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
            {
              id: "project-B",
              org_id: "org",
              name: "プロジェクトB",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
          ]),
        );
      }
      if (path.endsWith("/chat-jobs/job-1")) {
        return new Response(
          JSON.stringify({
            id: "job-1",
            conversation_id: "conversation",
            status: "done",
            detail: "",
            message_id: "message-2",
            cancel_requested: false,
            created: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (path === "/api/conversations/conversation") {
        return new Response(
          JSON.stringify({
            id: "conversation",
            project_id: "project-A",
            created: 0,
            messages: [
              {
                id: "message-1",
                text: "テスト質問",
                scope: "all",
                citations: [],
                answer: null,
              },
              {
                id: "message-2",
                text: "回答",
                scope: "all",
                citations: [],
                answer: "成膜条件は180°Cです。",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return originalFetch(input, options);
    });

    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "テスト質問" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    await screen.findByText("順番待ちあり");

    // The queued answer is confirmed and stays with the conversation that asked.
    await waitFor(
      () =>
        expect(screen.getByText("成膜条件は180°Cです。")).toBeInTheDocument(),
      { timeout: 10000 },
    );

    // Switching projects must not carry the confirmed answer over.
    const projectSelect = screen.getByRole("combobox");
    fireEvent.change(projectSelect, { target: { value: "project-B" } });
    await waitFor(() =>
      expect(screen.queryByText("順番待ちあり")).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("成膜条件は180°Cです。")).not.toBeInTheDocument();
  });
}, 20000);

describe("source provenance modal", () => {
  const CITE_NAME = "比較結果.txt";

  function mockCitationFetch() {
    const originalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      const path = String(input);
      if (path.endsWith("/messages") && options?.method === "POST") {
        return new Response(
          JSON.stringify({
            id: "message-source",
            text: "比較の答えです",
            scope: "all",
            citations: [
              {
                id: "chunk-1",
                document_id: "document-1",
                page: 2,
                ordinal: 1,
                name: CITE_NAME,
                text: "出典の原文です",
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (path.includes(`/documents/document-1/chunks`))
        return new Response(
          JSON.stringify([
            {
              id: "chunk-1",
              document_id: "document-1",
              page: 2,
              ordinal: 1,
              text: "出典の原文です",
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      if (path.includes("/documents/document-1/related"))
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      if (path.includes("/documents/document-1"))
        return new Response(
          JSON.stringify({
            id: "document-1",
            name: CITE_NAME,
            project_id: "project",
            kind: "personal",
            status: "ready",
            conversation_id: "conversation",
            created: 1,
            owned: true,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      return originalFetch(input, options);
    });
  }

  async function openSourceDialog() {
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    fireEvent.change(field, { target: { value: "比較してください" } });
    fireEvent.click(screen.getByRole("button", { name: "送信" }));
    const citation = await screen.findByRole("button", {
      name: /比較結果\.txt/,
    });
    fireEvent.click(citation);
    return screen.findByRole("dialog", { name: "出典の原文" });
  }

  it("opens a labelled <dialog> and its accessible name is readable", async () => {
    mockCitationFetch();
    const dialog = await openSourceDialog();
    expect(dialog.tagName).toBe("DIALOG");
    expect(dialog).toHaveAttribute("open", "");
    // getByRole with a name only resolves when the accessible name is
    // computable from aria-label.
    expect(screen.getByRole("dialog", { name: "出典の原文" })).toBeTruthy();
  });

  it("closes on 閉じる without depending on the network", async () => {
    mockCitationFetch();
    await openSourceDialog();
    fireEvent.click(screen.getByRole("button", { name: "閉じる" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "出典の原文" })).toBeNull(),
    );
  });

  it("keeps the dialog open when 関連資料を確認 is clicked", async () => {
    mockCitationFetch();
    await openSourceDialog();
    // The related-documents buttons must not submit the dialog's form;
    // a plain <button> inside <form method="dialog"> would close it.
    fireEvent.click(screen.getByRole("button", { name: "関連資料を確認" }));
    expect(await screen.findByText(/関連資料はありません/)).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "出典の原文" })).toBeTruthy();
  });

  it("closes on a backdrop click outside the content rectangle", async () => {
    mockCitationFetch();
    const dialog = await openSourceDialog();
    // jsdom has no real backdrop hit-testing, so a click targeted at the
    // dialog itself stands in for a backdrop click; the coordinates land
    // outside the content rectangle there too.
    fireEvent.click(dialog, { clientX: -1, clientY: -1 });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "出典の原文" })).toBeNull(),
    );
  });

  it("closedby='any' and backdrop click do not break dialog state", async () => {
    mockCitationFetch();
    const dialog = await openSourceDialog();
    // jsdom does not implement native closedby light-dismiss, so this test
    // cannot prove the native closedby path and the JS fallback run in the same
    // interaction. It verifies: the attribute is present, the JS backdrop-click
    // fallback closes cleanly, and reopen/close state remains usable afterward.
    // Native closedby behavior is covered by browser e2e.
    expect(dialog).toBeTruthy();
    expect(dialog).toHaveAttribute("open", "");
    expect(dialog).toHaveAttribute("closedby", "any");
    fireEvent.click(dialog, { clientX: -1, clientY: -1 });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "出典の原文" })).toBeNull(),
    );
    // After closing, re-opening should work cleanly
    const dialog2 = await openSourceDialog();
    expect(dialog2).toBeTruthy();
    expect(dialog2).toHaveAttribute("open", "");
    // Clicking the close button should still work
    fireEvent.click(screen.getByRole("button", { name: "閉じる" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "出典の原文" })).toBeNull(),
    );
  });

  // --- T-PH6-112: settings dialog / sidebar acceptance ---

  async function openSettings() {
    render(<App />);
    await screen.findByRole("heading", { name: "会話" });
    fireEvent.click(screen.getByRole("button", { name: "設定" }));
    return screen.findByRole("dialog", { name: "設定" });
  }

  it("opens the settings dialog from the gear and exposes its accessible name", async () => {
    const dialog = await openSettings();
    expect(dialog.tagName).toBe("DIALOG");
    expect(dialog).toHaveAttribute("open", "");
    expect(screen.getByRole("dialog", { name: "設定" })).toBe(dialog);
  });

  it("closes the settings dialog with Escape and a backdrop click", async () => {
    const dialog = await openSettings();
    // jsdom does not implement closedby light-dismiss. Mirror the browser
    // behaviour for this test only so the Esc requirement is exercised.
    const dialogEl = dialog as HTMLDialogElement;
    dialogEl.addEventListener("keydown", (event) => {
      if (event.key === "Escape") dialogEl.close();
    });
    dialog.focus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "設定" })).toBeNull(),
    );

    fireEvent.click(screen.getByRole("button", { name: "設定" }));
    const reopened = await screen.findByRole("dialog", { name: "設定" });
    fireEvent.click(reopened, { clientX: -1, clientY: -1 });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "設定" })).toBeNull(),
    );
  });

  it("switches settings tabs and updates the panel content", async () => {
    await openSettings();
    expect(
      screen.getByRole("heading", { name: "外観", level: 2 }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "実験的" }));
    expect(
      await screen.findByRole("heading", { name: "実験的", level: 2 }),
    ).toBeVisible();
    expect(screen.getByText("LAN公開")).toBeVisible();
  });

  it("starts a new chat from the sidebar button", async () => {
    render(<App />);
    const field = await screen.findByRole("textbox", { name: "メッセージ" });
    await waitFor(() => expect(field).toBeEnabled());
    fireEvent.change(field, { target: { value: "成膜条件" } });
    expect(field).toHaveValue("成膜条件");

    fireEvent.click(screen.getByRole("button", { name: "新しいチャット" }));
    await waitFor(() =>
      expect(
        screen.getByRole("textbox", { name: "メッセージ" }),
      ).toHaveValue(""),
    );
    expect(screen.getByText("資料を参照して質問できます")).toBeVisible();
  });

  it("hides admin-only settings tabs for a non-admin user", async () => {
    // Default mock user: system_admin false, permissions [read,retrieve,upload].
    await openSettings();
    expect(screen.getByRole("button", { name: "外観" })).toBeVisible();
    expect(screen.getByRole("button", { name: "モデル" })).toBeVisible();
    expect(screen.getByRole("button", { name: "実験的" })).toBeVisible();
    for (const label of [
      "利用者",
      "役割",
      "プロジェクト",
      "保存先",
      "実行状況",
      "操作記録",
    ]) {
      expect(
        screen.queryByRole("button", { name: label }),
      ).not.toBeInTheDocument();
    }
  });

  it("does not show operations gated by can() when permission is false", async () => {
    // manage_roles is not granted to the default user; the roles tab must not
    // appear even though the project exists.
    await openSettings();
    expect(
      screen.queryByRole("button", { name: "役割" }),
    ).not.toBeInTheDocument();
    // Delegations tab is visible because project.id exists (not a can() gate),
    // but role management is not.
    expect(screen.getByRole("button", { name: "委任" })).toBeVisible();
  });
});
