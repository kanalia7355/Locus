import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ModelRuntime } from "./ModelRuntime";

afterEach(() => vi.unstubAllGlobals());

it("requires local-only confirmation and sends the selected opaque id; can disable", async () => {
  const fetch = vi.fn(async (_: string, options?: RequestInit) => {
    if (!options?.method)
      return new Response(
        JSON.stringify({ enabled: false, model: null, timeout_seconds: 30 }),
      );
    const body = JSON.parse(options.body as string);
    return new Response(
      JSON.stringify({
        enabled: body.candidate_id !== null,
        model: "fixture",
        timeout_seconds: body.timeout_seconds,
      }),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<ModelRuntime candidate="candidate" />);
  const enable = screen.getByRole("button", {
    name: "選択モデルをチャットに使用",
  });
  expect(enable).toBeDisabled();
  await screen.findByText("現在：原文検索");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][1]?.method).toBeUndefined();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(enable);
  expect(await screen.findByRole("status")).toHaveTextContent(
    "fixture を使用します",
  );
  expect(JSON.parse(fetch.mock.calls[1][1]?.body as string)).toEqual({
    candidate_id: "candidate",
    local_only_confirmed: true,
    timeout_seconds: 30,
  });
  fireEvent.click(screen.getByRole("button", { name: "原文検索に戻す" }));
  expect(await screen.findByText("原文検索に戻しました。")).toBeVisible();
  expect(JSON.parse(fetch.mock.calls[2][1]?.body as string)).toEqual({
    candidate_id: null,
    local_only_confirmed: false,
    timeout_seconds: 30,
  });
});

it("cannot enable a folder candidate and reports server errors without retry", async () => {
  const fetch = vi.fn(async (_: string, options?: RequestInit) =>
    !options?.method
      ? new Response(
          JSON.stringify({ enabled: false, model: null, timeout_seconds: 30 }),
        )
      : new Response(JSON.stringify({ detail: "設定が失効しました" }), {
          status: 409,
        }),
  );
  vi.stubGlobal("fetch", fetch);
  render(<ModelRuntime candidate={null} />);
  await screen.findByText("現在：原文検索");
  fireEvent.click(screen.getByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "選択モデルをチャットに使用" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "原文検索に戻す" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "設定が失効しました",
  );
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("reads an already enabled model on reopening without changing configuration", async () => {
  const fetch = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          enabled: true,
          model: "existing-model",
          timeout_seconds: 30,
        }),
      ),
  );
  vi.stubGlobal("fetch", fetch);
  const first = render(<ModelRuntime candidate={null} />);
  await screen.findByText("現在：existing-model による生成");
  first.unmount();
  render(<ModelRuntime candidate="new-candidate" />);
  await screen.findByText("現在：existing-model による生成");
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(
    fetch.mock.calls.every(
      (call) => !((call as unknown[])[1] as RequestInit)?.method,
    ),
  ).toBe(true);
  expect(
    screen.getByRole("button", { name: "選択モデルをチャットに使用" }),
  ).toBeDisabled();
});

it("blocks activation until status is known and aborts an obsolete status request", async () => {
  let release!: (response: Response) => void;
  let signal: AbortSignal | null | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((_: string, options?: RequestInit) => {
      signal = options?.signal;
      return new Promise<Response>((resolve) => {
        release = resolve;
      });
    }),
  );
  const view = render(<ModelRuntime candidate="candidate" />);
  expect(
    screen.getByRole("button", { name: "選択モデルをチャットに使用" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "原文検索に戻す" })).toBeDisabled();
  view.unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () =>
    release(
      new Response(
        JSON.stringify({ enabled: true, model: "late", timeout_seconds: 30 }),
      ),
    ),
  );
  expect(screen.queryByText(/late/)).toBeNull();
});

it("keeps activation blocked on status failure but allows an explicit disable", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_: string, options?: RequestInit) =>
      options?.method
        ? new Response(
            JSON.stringify({
              enabled: false,
              model: null,
              timeout_seconds: 30,
            }),
          )
        : new Response(JSON.stringify({ detail: "状態取得に失敗しました" }), {
            status: 503,
          }),
    ),
  );
  render(<ModelRuntime candidate="candidate" />);
  await screen.findByText("現在の設定を確認できません。");
  fireEvent.click(screen.getByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "選択モデルをチャットに使用" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "原文検索に戻す" }));
  await screen.findByText("現在：原文検索");
});

it("requires explicit save for 120 seconds and shows the saved deadline", async () => {
  const fetch = vi.fn(async (_: string, options?: RequestInit) => {
    if (!options?.method)
      return new Response(
        JSON.stringify({
          enabled: true,
          model: "fixture",
          timeout_seconds: 30,
        }),
      );
    const body = JSON.parse(options.body as string);
    return new Response(
      JSON.stringify({
        enabled: body.candidate_id !== null,
        model: body.candidate_id ? "fixture" : null,
        timeout_seconds: body.candidate_id ? body.timeout_seconds : 30,
      }),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<ModelRuntime candidate="candidate" />);
  await screen.findByText("待機上限：30秒");
  fireEvent.change(screen.getByLabelText("モデル応答の待機時間"), {
    target: { value: "120" },
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(screen.getByText("待機上限：30秒")).toBeVisible();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(
    screen.getByRole("button", { name: "選択モデルをチャットに使用" }),
  );
  await screen.findByText("待機上限：120秒");
  expect(
    JSON.parse(fetch.mock.calls[1][1]?.body as string).timeout_seconds,
  ).toBe(120);
  fireEvent.click(screen.getByRole("button", { name: "原文検索に戻す" }));
  await screen.findByText("待機上限：30秒");
  expect(screen.getByLabelText("モデル応答の待機時間")).toHaveValue("30");
});
