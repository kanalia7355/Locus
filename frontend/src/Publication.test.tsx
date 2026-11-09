import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";

afterEach(() => vi.unstubAllGlobals());

it("previews selected operations, preserves rejected input, and submits only the selected grant", async () => {
  localStorage.clear();
  const writes: unknown[] = [];
  let reject = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      let data: unknown = [];
      if (path === "/api/auth/me")
        data = {
          id: "owner",
          username: "owner",
          system_admin: true,
          must_rotate: false,
        };
      if (path === "/api/projects")
        data = [
          {
            id: "project",
            name: "検証",
            org_id: "org",
            role: "project_lead",
            permissions: [
              "read",
              "retrieve",
              "upload",
              "publish",
              "manage_roles",
            ],
          },
        ];
      if (path === "/api/projects/project/roles")
        data = {
          templates: [],
          custom: [
            {
              id: "custom-reader",
              name: "独自の閲覧担当",
              permissions: ["read"],
            },
          ],
          allowed_permissions: ["read", "retrieve"],
        };
      if (path.startsWith("/api/documents?"))
        data = [
          {
            id: "document",
            name: "合成資料.txt",
            kind: "personal",
            status: "ready",
            project_id: "project",
            owned: true,
          },
        ];
      if (path === "/api/documents/document/publication") {
        writes.push(JSON.parse(options?.body as string));
        if (reject)
          return new Response(
            JSON.stringify({ detail: "公開を保存できません" }),
            { status: 403 },
          );
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify(data), { status: 200 });
    }),
  );
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "個人資料" }));
  fireEvent.click(await screen.findByRole("button", { name: "公開先" }));
  const operations = screen.getByLabelText("許可する操作");
  expect(operations).toHaveValue("read");
  fireEvent.change(screen.getByLabelText("ロール", { exact: true }), {
    target: { value: "viewer" },
  });
  expect(
    screen.getByText(/このプロジェクトの「閲覧者」に閲覧のみ/),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "公開設定を保存" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "公開を保存できません",
  );
  expect(operations).toBeVisible();
  expect(operations).toHaveValue("read");
  expect(writes).toEqual([
    { grants: [{ role: "viewer", operations: ["read"] }] },
  ]);
  fireEvent.change(operations, { target: { value: "retrieve" } });
  expect(
    screen.getByText(/このプロジェクトの「閲覧者」に閲覧・チャット参照/),
  ).toBeVisible();
  reject = false;
  fireEvent.click(screen.getByRole("button", { name: "公開設定を保存" }));
  await waitFor(() =>
    expect(screen.queryByLabelText("許可する操作")).not.toBeInTheDocument(),
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(writes[1]).toEqual({
    grants: [{ role: "viewer", operations: ["read", "retrieve"] }],
  });
  fireEvent.click(screen.getByRole("button", { name: "公開先" }));
  await screen.findByRole("option", { name: "独自の閲覧担当" });
  fireEvent.change(screen.getByLabelText("ロール", { exact: true }), {
    target: { value: "custom-reader" },
  });
  expect(
    screen.getByText(/このプロジェクトの「独自の閲覧担当」に閲覧のみ/),
  ).toBeVisible();
  expect(
    screen.getByRole("option", { name: "閲覧・チャット参照" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "公開設定を保存" }));
  await waitFor(() => expect(writes).toHaveLength(3));
  expect(writes[2]).toEqual({
    grants: [{ role: "custom-reader", operations: ["read"] }],
  });
});
