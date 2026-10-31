import { afterEach, expect, it, vi } from "vitest";
import { api, json } from "./api";

afterEach(() => vi.unstubAllGlobals());

const headerForms: [string, (contentType?: string) => HeadersInit][] = [
  [
    "Headers",
    (contentType) => {
      const headers = new Headers({ "X-Request-ID": "request-123" });
      if (contentType !== undefined) headers.set("cOnTeNt-TyPe", contentType);
      return headers;
    },
  ],
  [
    "tuple array",
    (contentType) => {
      const headers: [string, string][] = [["X-Request-ID", "request-123"]];
      if (contentType !== undefined)
        headers.push(["cOnTeNt-TyPe", contentType]);
      return headers;
    },
  ],
  [
    "record",
    (contentType) => ({
      "X-Request-ID": "request-123",
      ...(contentType === undefined ? {} : { "cOnTeNt-TyPe": contentType }),
    }),
  ],
];

it.each(headerForms)(
  "preserves custom headers and defaults to JSON for %s",
  async (_name, makeHeaders) => {
    const inputHeaders = makeHeaders();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/projects", {
      headers: inputHeaders,
      credentials: "include",
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/projects");
    expect(options?.credentials).toBe("same-origin");
    const headers = new Headers(options?.headers);
    expect(headers.get("X-Request-ID")).toBe("request-123");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(new Headers(inputHeaders).has("Content-Type")).toBe(false);
  },
);

it.each(headerForms)(
  "preserves case-insensitive Content-Type overrides for %s",
  async (_name, makeHeaders) => {
    const inputHeaders = makeHeaders("text/plain");
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/projects", { headers: inputHeaders });

    expect(fetchMock).toHaveBeenCalledOnce();
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("X-Request-ID")).toBe("request-123");
    expect(headers.get("Content-Type")).toBe("text/plain");
    expect(new Headers(inputHeaders).get("Content-Type")).toBe("text/plain");
  },
);

it("defaults to JSON Content-Type when headers are omitted", async () => {
  const fetchMock = vi
    .fn<typeof fetch>()
    .mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);

  await api("/projects");

  expect(fetchMock).toHaveBeenCalledOnce();
  const options = fetchMock.mock.calls[0][1];
  expect(new Headers(options?.headers).get("Content-Type")).toBe(
    "application/json",
  );
  expect(options?.credentials).toBe("same-origin");
});

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
