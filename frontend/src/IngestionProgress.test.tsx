import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { IngestionProgress } from "./IngestionProgress";
import { App } from "./App";
import type { Document } from "./api";

const doc = (status: string, id = status): Document => ({
  id,
  status,
  name: `${id}.txt`,
  project_id: "one",
  kind: "personal",
  reason: "",
  conversation_id: null,
  created: 1,
  owned: true,
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("keeps quarantine and unknown states separate from usable documents on refresh", () => {
  const view = render(
    <IngestionProgress
      documents={[doc("ready"), doc("quarantined"), doc("new-state")]}
    />,
  );
  const region = screen.getByRole("region", { name: "表示中の資料の処理状況" });
  expect(within(region).getByRole("heading")).toHaveTextContent("3件");
  expect(
    within(region).getByText("状態不明").nextElementSibling,
  ).toHaveTextContent("1件");
  expect(
    within(region).getByText("参照可能").nextElementSibling,
  ).toHaveTextContent("1件");
  view.rerender(<IngestionProgress documents={[]} />);
  expect(screen.queryByText("状態不明")).toBeNull();
  expect(within(region).getByRole("heading")).toHaveTextContent("0件");
});

async function setup() {
  localStorage.clear();
  let reads = 0;
  let release!: (response: Response) => void;
  let pollingSignal: AbortSignal | null | undefined;
  const pending = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const fetcher = vi.fn(async (input: string, options?: RequestInit) => {
    const path = String(input);
    let value: unknown = [];
    if (path.endsWith("/auth/me"))
      value = {
        id: "owner",
        username: "owner",
        system_admin: false,
        must_rotate: false,
      };
    if (path.endsWith("/projects"))
      value = ["one", "two"].map((id) => ({
        id,
        name: id,
        org_id: "org",
        permissions: ["read", "upload"],
        role: "researcher",
      }));
    if (path.endsWith("/documents?project_id=one")) {
      reads++;
      if (reads > 1) {
        pollingSignal = options?.signal;
        return pending;
      }
      value = [doc("queued")];
    }
    return new Response(JSON.stringify(value));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<App />);
  await screen.findByRole("button", { name: "取り込み状況" });
  fireEvent.click(screen.getByRole("button", { name: "個人資料" }));
  await screen.findByText("queued.txt");
  vi.useFakeTimers();
  fireEvent.click(screen.getByRole("button", { name: "取り込み状況" }));
  return { fetcher, release, signal: () => pollingSignal, reads: () => reads };
}

it("polls one request at a time and stops after the last job finishes", async () => {
  const state = await setup();
  await act(() => vi.advanceTimersByTimeAsync(2000));
  expect(state.reads()).toBe(2);
  await act(() => vi.advanceTimersByTimeAsync(6000));
  expect(state.reads()).toBe(2);
  await act(async () =>
    state.release(new Response(JSON.stringify([doc("ready")]))),
  );
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(state.reads()).toBe(2);
  expect(screen.getByRole("region").textContent).toContain("参照可能");
});

it("aborts discarded project polling and rejects its late reply", async () => {
  const state = await setup();
  await act(() => vi.advanceTimersByTimeAsync(2000));
  fireEvent.change(screen.getByRole("combobox", { name: "プロジェクト" }), {
    target: { value: "two" },
  });
  expect(state.signal()?.aborted).toBe(true);
  await act(async () =>
    state.release(new Response(JSON.stringify([doc("ready", "old-secret")]))),
  );
  expect(screen.queryByText("old-secret.txt")).toBeNull();
  expect(screen.getByRole("combobox", { name: "プロジェクト" })).toHaveValue(
    "two",
  );
});

it("stops polling on an error until an explicit refresh", async () => {
  const state = await setup();
  await act(() => vi.advanceTimersByTimeAsync(2000));
  await act(async () =>
    state.release(
      new Response(JSON.stringify({ detail: "synthetic failure" }), {
        status: 503,
      }),
    ),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("自動更新を停止");
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(state.reads()).toBe(2);
});

it("expires a hung status GET without replay and labels counts as stale", async () => {
  const state = await setup();
  await act(() => vi.advanceTimersByTimeAsync(12000));
  expect(state.signal()?.aborted).toBe(true);
  expect(screen.getByRole("alert")).toHaveTextContent("10秒");
  expect(screen.getByRole("region")).toHaveTextContent("自動更新は停止");
  await act(() => vi.advanceTimersByTimeAsync(10000));
  expect(state.reads()).toBe(2);
});
