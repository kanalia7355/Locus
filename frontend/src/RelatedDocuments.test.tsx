import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RelatedDocuments } from "./RelatedDocuments";

afterEach(() => vi.unstubAllGlobals());

it("loads only on demand, shows provenance, and opens the authorized target", async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify([
        {
          document: { id: "target", name: "関連する合成資料" },
          method: "lexical-common-terms",
          shared_term_count: 2,
          evidence: [
            {
              term: "成膜",
              source_page: 1,
              target_page: 3,
              source_chunk_id: "a",
              target_chunk_id: "b",
            },
          ],
        },
      ]),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", fetcher);
  const onOpen = vi.fn().mockResolvedValue(undefined);
  render(
    <RelatedDocuments
      documentId="source"
      conversationId="conversation"
      onOpen={onOpen}
    />,
  );
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "関連資料を確認" }));
  const target = await screen.findByRole("button", {
    name: "関連する合成資料",
  });
  expect(fetcher.mock.calls[0][0]).toBe(
    "/api/documents/source/related?conversation_id=conversation",
  );
  expect(screen.getByText(/この資料 p.1 → 関連資料 p.3/)).toBeVisible();
  fireEvent.click(target);
  expect(onOpen).toHaveBeenCalledWith("target");
});

it("distinguishes an empty authorized result from a denied request", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response("[]", { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "資料が見つかりません" }), {
          status: 404,
        }),
      ),
  );
  render(
    <RelatedDocuments
      documentId="source"
      conversationId={null}
      onOpen={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "関連資料を確認" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "現在参照できる関連資料はありません",
  );
  fireEvent.click(screen.getByRole("button", { name: "関連資料を確認" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "資料が見つかりません",
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("cancels pending retrieval when the source view is discarded", () => {
  const fetcher = vi.fn().mockImplementation(() => new Promise(() => {}));
  vi.stubGlobal("fetch", fetcher);
  const view = render(
    <RelatedDocuments
      documentId="source"
      conversationId={null}
      onOpen={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "関連資料を確認" }));
  const loading = screen.getByRole("button", { name: "関連資料を確認中" });
  expect(loading).toHaveAttribute("aria-disabled", "true");
  fireEvent.click(loading);
  expect(fetcher).toHaveBeenCalledTimes(1);
  const signal = fetcher.mock.calls[0][1].signal as AbortSignal;
  expect(signal.aborted).toBe(false);
  view.unmount();
  expect(signal.aborted).toBe(true);
});
