import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const requests: { path: string; options?: RequestInit }[] = [];
beforeEach(() => {
  requests.length = 0;
  localStorage.clear();
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
});
