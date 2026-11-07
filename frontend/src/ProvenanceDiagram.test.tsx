import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ProvenanceDiagram } from "./ProvenanceDiagram";
import type { RelatedDocument } from "./api";

const item = (index: number): RelatedDocument => ({
  document: {
    id: String(index),
    name: index === 0 ? "<script>not code</script>" : `関連資料${index}`,
    project_id: "project",
    kind: "personal",
    status: "ready",
    reason: "",
    conversation_id: null,
    created: 0,
    owned: true,
  },
  method: "lexical-common-terms",
  shared_term_count: index + 1,
  evidence: [],
});

it("shows only fetched source-to-target edges, bounded to ten and collapsed by default", () => {
  const { container } = render(
    <ProvenanceDiagram items={Array.from({ length: 12 }, (_, i) => item(i))} />,
  );
  expect(screen.queryByRole("img")).toBeNull();
  const button = screen.getByRole("button", { name: "資料の関係図を表示" });
  expect(button).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(button);
  expect(screen.getByRole("img")).toHaveAccessibleName(
    "共通語句による資料の関係図：表示中の資料と関連資料10件",
  );
  expect(container.querySelectorAll("path")).toHaveLength(10);
  expect(container.querySelectorAll("rect")).toHaveLength(11);
  expect(container.querySelector("script")).toBeNull();
  expect(screen.queryByText("関連資料10")).toBeNull();
  expect(screen.getByText(/資料間の意味や因果関係を示しません/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "資料の関係図を閉じる" }));
  expect(screen.queryByRole("img")).toBeNull();
});

it("does not offer a diagram for an empty authorized result", () => {
  render(<ProvenanceDiagram items={[]} />);
  expect(screen.queryByRole("button")).toBeNull();
});
