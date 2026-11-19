import { describe, expect, it } from "vitest";
import type { Citation, Message } from "./api";
import { chatRows } from "./chatRows";

function citation(): Citation {
  return {
    id: "citation-1",
    document_id: "document-1",
    page: 2,
    ordinal: 3,
    name: "合成資料.md",
    text: "成膜温度は180°Cです。",
  };
}

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: "message-1",
    text: "成膜条件を教えて",
    scope: "all",
    citations: [],
    ...overrides,
  };
}

describe("chatRows", () => {
  it("returns an empty row list for an empty conversation", () => {
    expect(chatRows([])).toEqual([]);
  });

  it("keeps the same key sequence for the same messages", () => {
    const first = chatRows([
      message({ id: "message-1", text: "成膜条件を教えて" }),
      message({ id: "message-2", text: "仕上げ温度は？" }),
    ]);
    const second = chatRows([
      message({ id: "message-1", text: "成膜条件を教えて" }),
      message({ id: "message-2", text: "仕上げ温度は？" }),
    ]);
    expect(first.map((row) => row.key)).toEqual(["message-1", "message-2"]);
    expect(second.map((row) => row.key)).toEqual(["message-1", "message-2"]);
    expect(first).toEqual(second);
  });

  it("keeps the same row key while an answer is confirmed", () => {
    const unconfirmed = chatRows([message({ id: "message-1", answer: null })]);
    const confirmed = chatRows([
      message({
        id: "message-1",
        answer: "成膜条件は180°Cです",
        model: "fixture:latest",
        citations: [citation()],
      }),
    ]);
    expect(confirmed).toHaveLength(1);
    expect(confirmed[0].key).toBe(unconfirmed[0].key);
  });

  it("omits the answer body, model and sources when the answer is hidden", () => {
    const rows = chatRows([
      message({
        id: "message-2",
        answer: "生成したくない回答",
        model: "fixture:latest",
        citations: [citation()],
        answer_hidden: true,
      }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].answerHidden).toBe(true);
    expect(rows[0].answer).toBeNull();
    expect(rows[0].model).toBeNull();
    expect(rows[0].citations).toEqual([]);
  });

  it("keeps the sources reachable from a cited answer row", () => {
    const rows = chatRows([
      message({
        id: "message-3",
        answer: "成膜条件は180°Cです",
        model: "fixture:latest",
        citations: [citation()],
      }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].answer).toBe("成膜条件は180°Cです");
    expect(rows[0].citations).toHaveLength(1);
    expect(rows[0].citations[0].id).toBe("citation-1");
    expect(rows[0].citations[0].document_id).toBe("document-1");
    expect(rows[0].citations[0].page).toBe(2);
    expect(rows[0].citations[0].ordinal).toBe(3);
    expect(rows[0].citations[0].name).toBe("合成資料.md");
    expect(rows[0].citations[0].text).toBe("成膜温度は180°Cです。");
  });

  it("projects a question whose answer has not been generated as an open row", () => {
    const rows = chatRows([message({ id: "message-4", answer: null })]);
    expect(rows).toHaveLength(1);
    expect(rows[0].answer).toBeNull();
    expect(rows[0].answerHidden).toBe(false);
    expect(rows[0].citations).toEqual([]);
  });
});
