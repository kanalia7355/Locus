import { describe, expect, it, vi } from "vitest";
import type { Message } from "./api";
import {
  createAttachmentKey,
  projectChatRows,
  type ChatJobNotice,
  type PendingChatJob,
} from "./chatProjection";

const message: Message = {
  id: "message-1",
  text: "質問",
  scope: "all",
  citations: [],
};

const pending: PendingChatJob = {
  id: "job-1",
  conversation: "conversation-1",
  text: "待機中の質問",
  status: "queued",
  cancelRequested: false,
};

const terminal: ChatJobNotice = {
  conversation: "conversation-1",
  text: "取り消した質問",
  status: "cancelled",
};

describe("projectChatRows", () => {
  it("uses stable message ids and only includes job rows for the current conversation", () => {
    const rows = projectChatRows(
      [message],
      pending,
      terminal,
      "conversation-1",
    );
    expect(rows.map((row) => row.key)).toEqual([
      "message-1",
      "job:cancelled:conversation-1",
      "job:job-1",
    ]);
    expect(rows[1]).toMatchObject({ kind: "job", status: "cancelled" });
    expect(rows[2]).toMatchObject({ kind: "job", status: "queued" });

    expect(projectChatRows([message], pending, terminal, "other")).toEqual([
      { kind: "message", key: "message-1", message },
    ]);
  });

  it("projects terminal backend statuses and keeps failure detail", () => {
    const rows = projectChatRows(
      [],
      null,
      { ...terminal, status: "failed", detail: "処理に失敗しました。" },
      "conversation-1",
    );
    expect(rows[0]).toMatchObject({
      kind: "job",
      status: "failed",
      detail: "処理に失敗しました。",
    });
  });

  it("preserves existing running and cancellation-requested states without inventing completion", () => {
    const rows = projectChatRows(
      [],
      { ...pending, status: "running", cancelRequested: true },
      null,
      "conversation-1",
    );
    expect(rows).toEqual([
      {
        kind: "job",
        key: "job:job-1",
        text: "待機中の質問",
        status: "running",
        cancelRequested: true,
      },
    ]);
  });
});

describe("createAttachmentKey", () => {
  it("uses randomUUID when available", () => {
    const randomUUID = vi.fn(() => "secure-key");
    vi.stubGlobal("crypto", { randomUUID });
    expect(createAttachmentKey()).toBe("secure-key");
    expect(randomUUID).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("creates a UUID-shaped key when randomUUID is unavailable", () => {
    const values = new Uint8Array(16).fill(7);
    const getRandomValues = vi.fn((buffer: Uint8Array) => {
      buffer.set(values);
      return buffer;
    });
    vi.stubGlobal("crypto", { getRandomValues });
    const key = createAttachmentKey();
    expect(key).toMatch(/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/);
    expect(key[14]).toBe("4");
    expect("89ab").toContain(key[19]);
    expect(getRandomValues).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });

  it("remains usable if no Web Crypto API exists", () => {
    vi.stubGlobal("crypto", undefined);
    expect(createAttachmentKey()).toMatch(
      /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/,
    );
    vi.unstubAllGlobals();
  });
});
