import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";

const admin = { id: "admin", username: "admin", system_admin: true, must_rotate: false, enabled: true };
const alice = { id: "alice", username: "alice", system_admin: false, must_rotate: true, enabled: true };
let change: (options?: RequestInit) => Promise<Response>;

beforeEach(() => {
  localStorage.clear();
  change = async () => new Response(JSON.stringify({ ...alice, enabled: false }));
  vi.stubGlobal("fetch", vi.fn(async (input: string, options?: RequestInit) => {
    if (input === "/api/auth/me") return new Response(JSON.stringify(admin));
    if (input === "/api/admin/users") return new Response(JSON.stringify([admin, alice]));
    if (input === "/api/admin/users/alice/enabled") return change(options);
    return new Response("[]");
  }));
});

async function openUsers() {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /^利用者$/ }));
  return screen.findByRole("button", { name: "aliceを無効にする" });
}

it("sends strict toggle payloads and updates the returned row only after success", async () => {
  const button = await openUsers();
  expect(screen.getByRole("button", { name: "adminを無効にする" })).toBeDisabled();
  expect(within(button.closest(".list-row") as HTMLElement).getByText(/有効 · 初回変更待ち/)).toBeVisible();
  fireEvent.click(button);
  const enable = await screen.findByRole("button", { name: "aliceを有効にする" });
  expect(fetch).toHaveBeenCalledWith("/api/admin/users/alice/enabled", expect.objectContaining({
    method: "PUT", body: JSON.stringify({ enabled: false }),
  }));
  expect(within(enable.closest(".list-row") as HTMLElement).getByText(/無効 · 初回変更待ち/)).toBeVisible();
  change = async () => new Response(JSON.stringify(alice));
  fireEvent.click(enable);
  await screen.findByRole("button", { name: "aliceを無効にする" });
  expect(fetch).toHaveBeenLastCalledWith("/api/admin/users/alice/enabled", expect.objectContaining({
    method: "PUT", body: JSON.stringify({ enabled: true }),
  }));
});

it("retains the row and shows errors without allowing duplicate pending requests", async () => {
  let finish!: (response: Response) => void;
  change = () => new Promise((resolve) => { finish = resolve; });
  const button = await openUsers();
  fireEvent.click(button);
  fireEvent.click(button);
  expect(button).toBeDisabled();
  expect(screen.queryByRole("button", { name: "aliceを有効にする" })).not.toBeInTheDocument();
  expect(vi.mocked(fetch).mock.calls.filter(([path]) => String(path).endsWith("/enabled"))).toHaveLength(1);
  finish(new Response(JSON.stringify({ detail: "変更できません" }), { status: 503 }));
  expect(await screen.findByRole("alert")).toHaveTextContent("変更できません");
  await waitFor(() => expect(button).not.toBeDisabled());
  expect(within(button.closest(".list-row") as HTMLElement).getByText(/有効 · 初回変更待ち/)).toBeVisible();
});

it("does not apply a late users response to the audit page", async () => {
  let finish!: (response: Response) => void;
  change = () => new Promise((resolve) => { finish = resolve; });
  const button = await openUsers();
  fireEvent.click(button);
  fireEvent.click(screen.getByText("運用・記録"));
  fireEvent.click(screen.getByRole("button", { name: /^操作記録$/ }));
  finish(new Response(JSON.stringify({ ...alice, enabled: false })));
  await screen.findByRole("heading", { name: "操作記録" });
  expect(screen.queryByText("alice")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
