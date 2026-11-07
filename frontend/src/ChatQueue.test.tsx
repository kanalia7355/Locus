import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";

let route: ((path: string, method?: string) => Response | undefined) | null =
  null;

beforeEach(() => {
  route = null;
  localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, options?: RequestInit) => {
      const method = options?.method;
      if (path.endsWith("/auth/me"))
        return new Response(
          JSON.stringify({
            id: "alice",
            username: "alice",
            system_admin: false,
            must_rotate: false,
          }),
        );
      if (path.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            {
              id: "project",
              org_id: "org",
              name: "検証",
              role: "researcher",
              permissions: ["read", "retrieve", "upload"],
            },
          ]),
        );
      const matched = route?.(path, method);
      if (matched) return matched;
      return new Response(JSON.stringify([]));
    }),
  );
});

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function askQuestion() {
  render(<App />);
  await screen.findByRole("heading", { name: "資料を調べる" });
  const field = await screen.findByRole("textbox", { name: "メッセージ" });
  fireEvent.change(field, { target: { value: "薄膜の成膜条件は？" } });
  fireEvent.submit(
    screen.getByRole("button", { name: "送信" }).closest("form")!,
  );
}

function conversationWithAnswer(answer: string | null): Response {
  return jsonResponse({
    id: "conversation",
    project_id: "project",
    created: 0,
    messages: [
      {
        id: "message-1",
        text: "薄膜の成膜条件は？",
        scope: "all",
        citations: [],
        answer,
        model: answer ? "fixture:latest" : null,
      },
    ],
    attachments: [],
  });
}

function accepted(jobId: string): Response {
  return jsonResponse(
    { job_id: jobId, status: "queued", text: "薄膜の成膜条件は？" },
    202,
  );
}

function jobStatus(status: string, messageId: string | null): Response {
  return jsonResponse({
    id: "job-1",
    conversation_id: "conversation",
    status,
    detail: status === "failed" ? "ログイン状態が変わりました" : "",
    message_id: messageId,
    cancel_requested: false,
    created: 0,
  });
}

it("queues the question while the model slot is busy and shows the answer", async () => {
  route = (path, method) => {
    if (path.endsWith("/api/conversations") && method === "POST")
      return jsonResponse({ id: "conversation", project_id: "project" });
    if (path.endsWith("/conversation/messages") && method === "POST")
      return accepted("job-1");
    if (path.endsWith("/api/chat-jobs/job-1")) return jobStatus("done", "m1");
    if (path.endsWith("/api/conversations/conversation"))
      return conversationWithAnswer("完成した回答です。");
    return undefined;
  };
  await askQuestion();
  await screen.findByText(/回答の生成は順番待ち/);
  // Sending a second question is blocked while one waits.
  expect(screen.getByRole("button", { name: "送信" })).toBeDisabled();
  await waitFor(
    () => expect(screen.getByText("完成した回答です。")).toBeInTheDocument(),
    { timeout: 6000 },
  );
  expect(screen.queryByText(/回答の生成は順番待ち/)).toBeNull();
  expect(screen.getByRole("textbox", { name: "メッセージ" })).toBeEnabled();
});

it("cancels a waiting question and reports the cancellation", async () => {
  let cancelled = false;
  route = (path, method) => {
    if (path.endsWith("/api/conversations") && method === "POST")
      return jsonResponse({ id: "conversation", project_id: "project" });
    if (path.endsWith("/conversation/messages") && method === "POST")
      return accepted("job-1");
    if (path.endsWith("/api/chat-jobs/job-1")) {
      if (method === "DELETE") {
        cancelled = true;
        return new Response(undefined, { status: 204 });
      }
      return jobStatus(cancelled ? "cancelled" : "queued", null);
    }
    return undefined;
  };
  await askQuestion();
  await screen.findByText(/回答の生成は順番待ち/);
  fireEvent.click(screen.getByRole("button", { name: "この質問を取り消す" }));
  await screen.findByText("質問を取り消しました。", undefined, { timeout: 6000 });
  expect(screen.queryByText(/回答の生成は順番待ち/)).toBeNull();
  expect(screen.getByRole("textbox", { name: "メッセージ" })).toBeEnabled();
});

it("offers cancellation while running and shows accepted cooperative cancellation", async () => {
  route = (path, method) => {
    if (path.endsWith("/api/conversations") && method === "POST")
      return jsonResponse({ id: "conversation", project_id: "project" });
    if (path.endsWith("/conversation/messages") && method === "POST")
      return accepted("job-1");
    if (path.endsWith("/api/chat-jobs/job-1")) {
      if (method === "DELETE") return new Response(undefined, { status: 204 });
      return jsonResponse({
        ...jobStatus("running", null),
        cancel_requested: true,
      });
    }
    return undefined;
  };
  await askQuestion();
  fireEvent.click(await screen.findByRole("button", { name: "この質問を取り消す" }));
  await waitFor(() =>
    expect(screen.getAllByText(/取り消しを受け付けました/).length).toBeGreaterThan(0),
  );
  expect(screen.queryByRole("button", { name: "この質問を取り消す" })).toBeNull();
});

it("shows a terminal cancelled job without displaying an answer", async () => {
  route = (path, method) => {
    if (path.endsWith("/api/conversations") && method === "POST")
      return jsonResponse({ id: "conversation", project_id: "project" });
    if (path.endsWith("/conversation/messages") && method === "POST")
      return accepted("job-1");
    if (path.endsWith("/api/chat-jobs/job-1"))
      return jobStatus("cancelled", null);
    return undefined;
  };
  await askQuestion();
  await screen.findByText("質問を取り消しました。回答は表示されません。", undefined, {
    timeout: 6000,
  });
  expect(screen.queryByText("完成した回答です。")).toBeNull();
});

it("keeps the running state and reports a failed cancellation", async () => {
  route = (path, method) => {
    if (path.endsWith("/api/conversations") && method === "POST")
      return jsonResponse({ id: "conversation", project_id: "project" });
    if (path.endsWith("/conversation/messages") && method === "POST")
      return accepted("job-1");
    if (path.endsWith("/api/chat-jobs/job-1")) {
      if (method === "DELETE")
        return jsonResponse({ detail: "取り消せません" }, 409);
      return jobStatus("running", null);
    }
    return undefined;
  };
  await askQuestion();
  await screen.findByText(/回答の生成は順番待ち/);
  fireEvent.click(screen.getByRole("button", { name: "この質問を取り消す" }));
  await screen.findByText("取り消せません");
  expect(screen.getByText(/回答の生成は順番待ち/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "この質問を取り消す" })).toBeInTheDocument();
});

it("reports a failed queued question with the recorded reason", async () => {
  route = (path, method) => {
    if (path.endsWith("/api/conversations") && method === "POST")
      return jsonResponse({ id: "conversation", project_id: "project" });
    if (path.endsWith("/conversation/messages") && method === "POST")
      return accepted("job-1");
    if (path.endsWith("/api/chat-jobs/job-1"))
      return jobStatus("failed", null);
    return undefined;
  };
  await askQuestion();
  await waitFor(
    () =>
      expect(screen.getByText(/回答を生成できませんでした。/)).toBeInTheDocument(),
    { timeout: 6000 },
  );
  expect(screen.getByText(/ログイン状態が変わりました/)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "メッセージ" })).toBeEnabled();
});
