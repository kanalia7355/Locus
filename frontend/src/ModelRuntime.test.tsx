import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ModelRuntime } from "./ModelRuntime";

afterEach(() => vi.unstubAllGlobals());

it("requires local-only confirmation and sends the selected opaque id; can disable", async () => {
  const fetch = vi.fn(async (_: string, options: RequestInit) => {
    const body = JSON.parse(options.body as string);
    return new Response(
      JSON.stringify({ enabled: body.candidate_id !== null, model: "fixture" }),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<ModelRuntime candidate="candidate" />);
  const enable = screen.getByRole("button", {
    name: "選択モデルをチャットに使用",
  });
  expect(enable).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(enable);
  expect(await screen.findByRole("status")).toHaveTextContent(
    "fixture を使用します",
  );
  expect(JSON.parse(fetch.mock.calls[0][1].body as string)).toEqual({
    candidate_id: "candidate",
    local_only_confirmed: true,
  });
  fireEvent.click(screen.getByRole("button", { name: "原文検索に戻す" }));
  expect(await screen.findByText("原文検索に戻しました。")).toBeVisible();
  expect(JSON.parse(fetch.mock.calls[1][1].body as string)).toEqual({
    candidate_id: null,
    local_only_confirmed: false,
  });
});

it("cannot enable a folder candidate and reports server errors without retry", async () => {
  const fetch = vi.fn(
    async () =>
      new Response(JSON.stringify({ detail: "設定が失効しました" }), {
        status: 409,
      }),
  );
  vi.stubGlobal("fetch", fetch);
  render(<ModelRuntime candidate={null} />);
  fireEvent.click(screen.getByRole("checkbox"));
  expect(
    screen.getByRole("button", { name: "選択モデルをチャットに使用" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "原文検索に戻す" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "設定が失効しました",
  );
  expect(fetch).toHaveBeenCalledTimes(1);
});
