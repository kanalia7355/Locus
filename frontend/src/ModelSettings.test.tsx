import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ModelSettings } from "./ModelSettings";

afterEach(() => vi.unstubAllGlobals());

it("requires explicit source selection and never enables inference on candidate selection", async () => {
  const requests: { path: string; options?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      requests.push({ path, options });
      return new Response(
        JSON.stringify(
          path.endsWith("/sources")
            ? [{ id: "ollama", label: "Ollama 登録モデル", kind: "ollama" }]
            : {
                inference_enabled: false,
                sources: [{ id: "ollama", status: "complete" }],
                models: [
                  {
                    id: "candidate",
                    source_id: "ollama",
                    name: "<script>synthetic</script>",
                    size_bytes: 123,
                    format: "ollama",
                    status: "registered-requires-runtime-validation",
                    inference_enabled: false,
                  },
                ],
              },
        ),
        { status: 200 },
      );
    }),
  );
  render(<ModelSettings />);
  const source = await screen.findByRole("checkbox", {
    name: "Ollama 登録モデル",
  });
  expect(requests).toHaveLength(1);
  expect(
    screen.getByRole("button", { name: "選択した場所でモデルを検出" }),
  ).toBeDisabled();
  fireEvent.click(source);
  fireEvent.click(
    screen.getByRole("button", { name: "選択した場所でモデルを検出" }),
  );
  await screen.findByText("<script>synthetic</script>");
  expect(document.querySelector("script")).toBeNull();
  expect(JSON.parse(requests[1].options?.body as string)).toEqual({
    sources: ["ollama"],
  });
  fireEvent.click(screen.getByRole("button", { name: "候補として選択" }));
  expect(screen.getByText(/推論の有効化とは別の操作です/)).toBeVisible();
  expect(requests).toHaveLength(2);
});

it("reports incomplete discovery and clears old candidates on a failed refresh", async () => {
  let refresh = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => {
      if (path.endsWith("/sources"))
        return new Response(
          JSON.stringify([
            { id: "folder", label: "モデルフォルダー", kind: "folder" },
          ]),
        );
      if (++refresh === 2)
        return new Response(
          JSON.stringify({ detail: "現在の権限では確認できません" }),
          { status: 403 },
        );
      return new Response(
        JSON.stringify({
          inference_enabled: false,
          sources: [{ id: "folder", status: "partial", truncated: true }],
          models: [
            {
              id: "file",
              name: "synthetic.gguf",
              size_bytes: 10,
              format: "gguf",
              status: "requires-import-validation",
            },
          ],
        }),
      );
    }),
  );
  render(<ModelSettings />);
  fireEvent.click(
    await screen.findByRole("checkbox", { name: "モデルフォルダー" }),
  );
  const discover = screen.getByRole("button", {
    name: "選択した場所でモデルを検出",
  });
  fireEvent.click(discover);
  expect(await screen.findByRole("status")).toHaveTextContent(
    "一部の場所・項目は未確認",
  );
  fireEvent.click(discover);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "現在の権限では確認できません",
  );
  expect(screen.queryByText("synthetic.gguf")).not.toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
