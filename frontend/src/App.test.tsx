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
});
