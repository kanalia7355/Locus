import { afterEach, expect, it, vi } from "vitest";
import { api, json } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("credential errors leave rotation sessions available, while data 401 expires the workspace", async () => {
  const expired = vi.fn();
  window.addEventListener("locus-session-expired", expired);
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "確認してください" }), {
          status: 401,
        }),
    ),
  );
  await expect(api("/auth/password", json("POST", {}))).rejects.toThrow(
    "確認してください",
  );
  expect(expired).not.toHaveBeenCalled();
  await expect(api("/projects")).rejects.toThrow("確認してください");
  expect(expired).toHaveBeenCalledOnce();
  window.removeEventListener("locus-session-expired", expired);
});
