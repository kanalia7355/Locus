import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import type { Role } from "./api";

afterEach(() => vi.unstubAllGlobals());

async function setup(permissions = ["read", "retrieve"]) {
  localStorage.clear();
  const catalog: Record<string, Role> = {
    one: { id: "role-one", name: "既存の担当", permissions },
    two: {
      id: "role-two",
      name: "別プロジェクトの担当",
      permissions: ["read"],
    },
  };
  const writes: { path: string; body: unknown }[] = [];
  const state = { reject: false };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      let data: unknown = [];
      if (path === "/api/auth/me")
        data = {
          id: "admin",
          username: "admin",
          system_admin: true,
          must_rotate: false,
        };
      if (path === "/api/projects")
        data = ["one", "two"].map((id) => ({
          id,
          org_id: "org",
          name: id,
          role: "assistant_admin",
          permissions: ["read", "retrieve", "manage_roles"],
        }));
      const match =
        /^\/api\/projects\/(one|two)\/roles(?:\/(role-one|role-two))?$/.exec(
          path,
        );
      if (match) {
        const project = match[1];
        if (options?.method === "PUT") {
          writes.push({ path, body: JSON.parse(options.body as string) });
          if (state.reject)
            return new Response(
              JSON.stringify({ detail: "現在の権限では変更できません" }),
              { status: 422 },
            );
          catalog[project] = {
            ...catalog[project],
            ...JSON.parse(options.body as string),
          };
          data = catalog[project];
        } else
          data = {
            templates: [],
            custom: [catalog[project]],
            allowed_permissions: ["read", "retrieve"],
          };
      }
      return new Response(JSON.stringify(data), { status: 200 });
    }),
  );
  render(<App />);
  fireEvent.click(
    await screen.findByRole("button", { name: "役割・管理権限" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "既存の担当を編集" }),
  );
  return { writes, state };
}

it("retains rejected edits and updates the same role ID on explicit save", async () => {
  const { writes, state } = await setup();
  fireEvent.change(screen.getByLabelText("ロール名", { exact: true }), {
    target: { value: "変更した担当" },
  });
  fireEvent.click(screen.getByRole("button", { name: "チャット参照" }));
  state.reject = true;
  fireEvent.click(screen.getByRole("button", { name: "ロールの変更を保存" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "現在の権限では変更できません",
  );
  expect(screen.getByLabelText("ロール名", { exact: true })).toHaveValue(
    "変更した担当",
  );
  state.reject = false;
  fireEvent.click(screen.getByRole("button", { name: "ロールの変更を保存" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "ロールを更新しました",
  );
  expect(writes).toEqual(
    Array(2).fill({
      path: "/api/projects/one/roles/role-one",
      body: { name: "変更した担当", permissions: ["read"] },
    }),
  );
  expect(
    screen.getByRole("button", { name: "変更した担当を編集" }),
  ).toBeVisible();
  expect(screen.getByLabelText("新しいロール名")).toHaveValue("");
});

it("requires explicit removal of operations outside the editor's ceiling", async () => {
  const { writes } = await setup(["read", "upload"]);
  expect(screen.getByRole("alert")).toHaveTextContent("本人の許可範囲外");
  expect(
    screen.getByRole("button", { name: "ロールの変更を保存" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "資料追加" }));
  expect(
    screen.queryByRole("button", { name: "資料追加" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "ロールの変更を保存" }));
  await screen.findByRole("status");
  expect(writes[0].body).toEqual({ name: "既存の担当", permissions: ["read"] });
});

it("cancel and project switching discard the old edit target", async () => {
  const { writes } = await setup();
  fireEvent.click(screen.getByRole("button", { name: "編集を取り消す" }));
  expect(screen.getByLabelText("新しいロール名")).toHaveValue("");
  fireEvent.click(screen.getByRole("button", { name: "既存の担当を編集" }));
  fireEvent.change(screen.getByLabelText("プロジェクト"), {
    target: { value: "two" },
  });
  fireEvent.click(
    await screen.findByRole("button", { name: "役割・管理権限" }),
  );
  await screen.findByRole("button", { name: "別プロジェクトの担当を編集" });
  await waitFor(() =>
    expect(
      screen.queryByLabelText("ロール名", { exact: true }),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByLabelText("新しいロール名")).toHaveValue("");
  expect(writes).toEqual([]);
});
