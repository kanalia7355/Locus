import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { FormEvent } from "react";
import type { Message } from "./api";
import { ChatComposer, ChatMessage, ChatView } from "./ChatView";

const message: Message = {
  id: "message-1",
  text: "条件を比較してください",
  scope: "all",
  answer: "条件Aと条件Bを比較しました。",
  model: "fixture:latest",
  citations: [
    {
      id: "citation-1",
      document_id: "document-1",
      page: 2,
      ordinal: 3,
      name: "合成資料.md",
      text: "処理温度は180°Cです。",
    },
  ],
};

it("renders the existing message presentation and model footnote", () => {
  const onOpenSource = vi.fn();
  render(<ChatMessage message={message} onOpenSource={onOpenSource} />);

  expect(screen.getByText("条件を比較してください")).toBeInTheDocument();
  expect(screen.getByText("条件Aと条件Bを比較しました。")).toBeInTheDocument();
  expect(
    screen.getByText(/fixture:latest による生成内容です/),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /合成資料.md · p.2/ }));
  expect(onOpenSource).toHaveBeenCalledWith("document-1", "citation-1");
});

it("shows attachment status and the existing failure reason in the composer", () => {
  render(
    <ChatComposer
      attachments={[
        {
          key: "attachment-1",
          name: "bad.txt",
          status: "failed",
          reason: "UTF-8として読み取れません。",
        },
      ]}
      busy={false}
      canRetrieve
      canUpload
      draft="下書き"
      pendingJob={null}
      onAddFiles={vi.fn()}
      onChangeDraft={vi.fn()}
      onRemoveAttachment={vi.fn()}
      onSubmit={(event) => event.preventDefault()}
    />,
  );

  expect(screen.getByText("bad.txt")).toBeInTheDocument();
  expect(screen.getByText("失敗")).toHaveClass("error");
  expect(screen.getByText("UTF-8として読み取れません。")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "メッセージ" })).toHaveValue(
    "下書き",
  );
});

it("keeps the chat composer accessibility labels and IME-safe submit behavior", () => {
  const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
  render(
    <ChatComposer
      attachments={[]}
      busy={false}
      canRetrieve
      canUpload
      draft="質問"
      pendingJob={null}
      onAddFiles={vi.fn()}
      onChangeDraft={vi.fn()}
      onRemoveAttachment={vi.fn()}
      onSubmit={onSubmit}
    />,
  );

  const field = screen.getByRole("textbox", { name: "メッセージ" });
  expect(
    screen.getByRole("button", { name: "ファイルを添付" }),
  ).toBeInTheDocument();
  fireEvent.keyDown(field, { key: "Enter", isComposing: true, keyCode: 229 });
  expect(onSubmit).not.toHaveBeenCalled();
});

it("renders terminal failure status and existing backend detail in the timeline", () => {
  render(
    <ChatView
      attachments={[]}
      busy={false}
      canRetrieve
      canUpload
      terminalJob={{
        conversation: "conversation-1",
        text: "失敗した質問",
        status: "failed",
        detail: "接続が拒否されました。",
      }}
      conversationId="conversation-1"
      draft=""
      messages={[]}
      pendingJob={null}
      scope="all"
      onAddFiles={vi.fn()}
      onCancelPendingJob={vi.fn()}
      onChangeDraft={vi.fn()}
      onOpenSource={vi.fn()}
      onRemoveAttachment={vi.fn()}
      onScopeChange={vi.fn()}
      onSubmit={(event) => event.preventDefault()}
    />,
  );

  const failedStatus = document.querySelector('[data-status="failed"]');
  expect(failedStatus).toHaveTextContent(
    "回答を生成できませんでした。接続が拒否されました。",
  );
  expect(failedStatus).toHaveAttribute("role", "status");
  expect(
    screen.queryByRole("button", { name: "この質問を取り消す" }),
  ).toBeNull();
});

it("renders projected pending processing status in the accessible chat timeline", () => {
  render(
    <ChatView
      attachments={[]}
      busy={false}
      canRetrieve
      canUpload
      terminalJob={null}
      conversationId="conversation-1"
      draft=""
      messages={[]}
      pendingJob={{
        id: "job-1",
        conversation: "conversation-1",
        text: "順番待ちの質問",
        status: "queued",
        cancelRequested: false,
      }}
      scope="all"
      onAddFiles={vi.fn()}
      onCancelPendingJob={vi.fn()}
      onChangeDraft={vi.fn()}
      onOpenSource={vi.fn()}
      onRemoveAttachment={vi.fn()}
      onScopeChange={vi.fn()}
      onSubmit={(event) => event.preventDefault()}
    />,
  );

  expect(screen.getByText(/回答の生成は順番待ち/)).toHaveAttribute(
    "data-status",
    "queued",
  );
  expect(
    screen.getByRole("button", { name: "この質問を取り消す" }),
  ).toBeVisible();
  expect(document.querySelector(".messages")).toHaveAttribute(
    "aria-live",
    "polite",
  );
});
