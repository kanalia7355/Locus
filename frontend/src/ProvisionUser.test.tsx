import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const requests: { path: string; options?: RequestInit }[] = [];
const temporaryPassword = "Synthetic-test-password-01!";
let failProvisioning = false;

const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

function stubClipboard(value: unknown) {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value });
}

function removeClipboard() {
  Reflect.deleteProperty(navigator, "clipboard");
}

beforeEach(() => {
  requests.length = 0;
  failProvisioning = false;
  localStorage.clear();
  stubClipboard({ writeText: vi.fn().mockResolvedValue(undefined) });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path === "/api/auth/me")
        return new Response(
          JSON.stringify({
            id: "admin-id",
            username: "admin",
            system_admin: true,
            must_rotate: false,
          }),
          { status: 200 },
        );
      if (path === "/api/projects")
        return new Response(
          JSON.stringify([
            {
              id: "project",
              org_id: "org",
              name: "検証",
              role: "system_admin",
              permissions: [],
            },
          ]),
          { status: 200 },
        );
      if (path === "/api/admin/users" && options?.method === "POST") {
        if (failProvisioning)
          return new Response(
            JSON.stringify({ detail: "利用者IDは使用済みです" }),
            { status: 409 },
          );
        return new Response(
          JSON.stringify({
            id: "created-id",
            username: "new-user",
            temporary_password: temporaryPassword,
            must_rotate: true,
          }),
          { status: 201 },
        );
      }
      if (path === "/api/admin/users")
        return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
});

afterEach(() => {
  if (originalClipboard) {
    Object.defineProperty(navigator, "clipboard", originalClipboard);
  } else {
    removeClipboard();
  }
});

describe("administrator web user provisioning", () => {
  async function openUsersPage() {
    render(<App />);
    await screen.findByRole("heading", { name: "会話" });
    fireEvent.click(screen.getByRole("button", { name: "設定" }));
    fireEvent.click(await screen.findByRole("button", { name: "利用者" }));
    await screen.findByRole("heading", { name: "利用者の追加" });
  }

  it("creates a user and shows a copyable password only until dismissed", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard({ writeText });
    await openUsersPage();
    fireEvent.click(screen.getByRole("button", { name: "追加" }));
    fireEvent.change(screen.getByRole("textbox", { name: "利用者ID" }), {
      target: { value: "new-user" },
    });
    fireEvent.click(screen.getByRole("button", { name: "作成" }));

    const passwordRegion = await screen.findByRole("region", {
      name: "一度だけ表示される仮パスワード",
    });
    expect(passwordRegion).toHaveTextContent("一度だけ表示されます。");
    expect(screen.getByLabelText("仮パスワード")).toHaveTextContent(
      temporaryPassword,
    );
    const request = requests.find(
      (item) => item.path === "/api/admin/users" && item.options?.method === "POST",
    );
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.options?.body))).toEqual({
      username: "new-user",
    });

    fireEvent.click(screen.getByRole("button", { name: "コピー" }));
    expect(writeText).toHaveBeenCalledWith(temporaryPassword);
    expect(await screen.findByText("コピーしました。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "閉じる" }));
    expect(
      screen.queryByRole("region", {
        name: "一度だけ表示される仮パスワード",
      }),
    ).not.toBeInTheDocument();
    expect(localStorage.getItem("locus-sidebar") ?? "").not.toContain(
      temporaryPassword,
    );
  });

  it("retains the username and displays errors after a failed submission", async () => {
    failProvisioning = true;
    await openUsersPage();
    fireEvent.click(screen.getByRole("button", { name: "追加" }));
    const username = screen.getByRole("textbox", { name: "利用者ID" });
    fireEvent.change(username, { target: { value: "existing-user" } });
    fireEvent.click(screen.getByRole("button", { name: "作成" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "利用者IDは使用済みです",
    );
    expect(username).toHaveValue("existing-user");
    expect(
      screen.queryByRole("region", {
        name: "一度だけ表示される仮パスワード",
      }),
    ).not.toBeInTheDocument();
  });

  it("does not show a copy button when clipboard is unavailable, but shows the password", async () => {
    // Plain-HTTP LAN pages are not secure contexts: the property is absent,
    // not merely undefined.
    removeClipboard();
    expect("clipboard" in navigator).toBe(false);
    await openUsersPage();
    fireEvent.click(screen.getByRole("button", { name: "追加" }));
    fireEvent.change(screen.getByRole("textbox", { name: "利用者ID" }), {
      target: { value: "new-user" },
    });
    fireEvent.click(screen.getByRole("button", { name: "作成" }));

    const passwordRegion = await screen.findByRole("region", {
      name: "一度だけ表示される仮パスワード",
    });
    expect(passwordRegion).toHaveTextContent("一度だけ表示されます。");
    expect(screen.getByLabelText("仮パスワード")).toHaveTextContent(
      temporaryPassword,
    );
    // Copy button should NOT be present when clipboard is unavailable
    expect(screen.queryByRole("button", { name: "コピー" })).not.toBeInTheDocument();
    // Instead, the password is selectable and the screen says how to copy it
    expect(
      screen.getByText("コピーできません。パスワードを選択してコピーしてください。"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "閉じる" }));
    expect(
      screen.queryByRole("region", {
        name: "一度だけ表示される仮パスワード",
      }),
    ).not.toBeInTheDocument();
    expect(localStorage.getItem("locus-sidebar") ?? "").not.toContain(
      temporaryPassword,
    );
  });

  it("does not discard a prior one-time password when a later request fails", async () => {
    await openUsersPage();
    fireEvent.click(screen.getByRole("button", { name: "追加" }));
    fireEvent.change(screen.getByRole("textbox", { name: "利用者ID" }), {
      target: { value: "new-user" },
    });
    fireEvent.click(screen.getByRole("button", { name: "作成" }));
    const passwordRegion = await screen.findByRole("region", {
      name: "一度だけ表示される仮パスワード",
    });
    expect(passwordRegion).toHaveTextContent(temporaryPassword);

    failProvisioning = true;
    fireEvent.click(screen.getByRole("button", { name: "追加" }));
    const username = screen.getByRole("textbox", { name: "利用者ID" });
    fireEvent.change(username, { target: { value: "another-user" } });
    fireEvent.click(screen.getByRole("button", { name: "作成" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "利用者IDは使用済みです",
    );
    expect(username).toHaveValue("another-user");
    expect(passwordRegion).toHaveTextContent(temporaryPassword);
  });
});
