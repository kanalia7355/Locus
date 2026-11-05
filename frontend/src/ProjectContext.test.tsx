import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import { App } from "./App";

afterEach(() => vi.unstubAllGlobals());

async function setup(
  mode: "reload" | "source" | "publication" | "history",
  strict = false,
) {
  localStorage.clear();
  let release!: (response: Response) => void;
  const delayed = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const counts = { one: 0, pending: false };
  const doc = (project: string, name = `${project}.txt`) => ({
    id: `${project}-doc`,
    project_id: project,
    name,
    kind: "personal",
    status: "ready",
    owned: true,
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, options?: RequestInit) => {
      const path = String(input);
      let data: unknown = [];
      if (path === "/api/auth/me")
        data = {
          id: "owner",
          username: "owner",
          system_admin: false,
          must_rotate: false,
        };
      if (path === "/api/projects")
        data = ["one", "two"].map((id) => ({
          id,
          org_id: "org",
          name: id,
          role: "project_lead",
          permissions: ["read", "retrieve", "upload", "publish"],
        }));
      if (path === "/api/documents?project_id=one") {
        counts.one++;
        if (mode === "reload" && counts.one === 2) {
          counts.pending = true;
          return delayed;
        }
        data = [
          doc(
            "one",
            mode === "reload" && counts.one >= 3 ? "newest.txt" : "one.txt",
          ),
        ];
      }
      if (path === "/api/documents?project_id=two") data = [doc("two")];
      if (path === "/api/documents/one-doc") data = doc("one");
      if (path.startsWith("/api/documents/one-doc/chunks")) {
        counts.pending = true;
        return delayed;
      }
      if (
        path === "/api/documents/one-doc/publication" &&
        options?.method === "PUT"
      ) {
        counts.pending = true;
        return delayed;
      }
      if (mode === "history") {
        if (path === "/api/conversations?project_id=one")
          data = [
            { id: "old-conv", project_id: "one", created: 1000 },
            { id: "new-conv", project_id: "one", created: 2000 },
          ];
        if (
          path === "/api/conversations/old-conv" &&
          options?.method === "DELETE"
        ) {
          counts.pending = true;
          return delayed;
        }
        if (options?.method === "DELETE")
          return new Response(null, { status: 204 });
        if (
          path === "/api/conversations/old-conv" ||
          path === "/api/conversations/new-conv"
        )
          data = {
            id: path.split("/").pop(),
            project_id: "one",
            attachments: [],
            messages: path.endsWith("new-conv")
              ? [
                  {
                    id: "new-message",
                    text: "新しい会話の質問",
                    scope: "all",
                    citations: [],
                  },
                ]
              : [],
          };
      }
      return new Response(JSON.stringify(data), { status: 200 });
    }),
  );
  const view = render(
    strict ? (
      <StrictMode>
        <App />
      </StrictMode>
    ) : (
      <App />
    ),
  );
  fireEvent.click(await screen.findByRole("button", { name: "個人資料" }));
  await screen.findByRole("button", { name: "one.txt" });
  return { counts, release, doc, view };
}

async function switchProject() {
  fireEvent.change(screen.getByLabelText("プロジェクト"), {
    target: { value: "two" },
  });
  fireEvent.click(screen.getByRole("button", { name: "個人資料" }));
  await screen.findByRole("button", { name: "two.txt" });
}

it("does not start an obsolete mutation refresh after logout/unmount", async () => {
  const { counts, release, view } = await setup("publication");
  fireEvent.click(screen.getByRole("button", { name: "公開先" }));
  fireEvent.click(screen.getByRole("button", { name: "公開設定を保存" }));
  await waitFor(() => expect(counts.pending).toBe(true));
  view.unmount();
  await act(async () => {
    release(new Response(null, { status: 204 }));
  });
  expect(counts.one).toBe(1);
});

it("an old deletion cannot clear another conversation, but current deletion still clears it", async () => {
  const { counts, release } = await setup("history");
  fireEvent.click(screen.getByRole("button", { name: "調査履歴" }));
  fireEvent.click(screen.getAllByRole("button", { name: /^調査 ·/ })[0]);
  await waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: "メッセージ" }),
    ).not.toBeDisabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "調査履歴" }));
  fireEvent.click(screen.getAllByRole("button", { name: "削除" })[0]);
  await waitFor(() => expect(counts.pending).toBe(true));
  fireEvent.click(screen.getAllByRole("button", { name: /^調査 ·/ })[1]);
  await screen.findByText("新しい会話の質問");
  const draft = screen.getByRole("textbox", { name: "メッセージ" });
  fireEvent.change(draft, { target: { value: "保持する下書き" } });
  await act(async () => {
    release(new Response(null, { status: 204 }));
  });
  expect(draft).toHaveValue("保持する下書き");
  expect(screen.getByText("新しい会話の質問")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "調査履歴" }));
  fireEvent.click(screen.getAllByRole("button", { name: "削除" })[1]);
  await waitFor(() =>
    expect(screen.queryByText("新しい会話の質問")).not.toBeInTheDocument(),
  );
  expect(screen.getByRole("textbox", { name: "メッセージ" })).toHaveValue("");
});

it("does not apply an old project refresh after switching projects", async () => {
  const { counts, release, doc } = await setup("reload", true);
  fireEvent.click(screen.getByRole("button", { name: "更新" }));
  await waitFor(() => expect(counts.pending).toBe(true));
  await switchProject();
  await act(async () => {
    release(
      new Response(JSON.stringify([doc("one", "obsolete.txt")]), {
        status: 200,
      }),
    );
  });
  expect(screen.getByRole("button", { name: "two.txt" })).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "obsolete.txt" }),
  ).not.toBeInTheDocument();
});

it("does not reopen a previous project's source after navigation", async () => {
  const { counts, release } = await setup("source");
  fireEvent.click(screen.getByRole("button", { name: "one.txt" }));
  await waitFor(() => expect(counts.pending).toBe(true));
  await switchProject();
  await act(async () => {
    release(
      new Response(
        JSON.stringify([
          {
            id: "chunk",
            document_id: "one-doc",
            page: 1,
            ordinal: 1,
            text: "old source",
          },
        ]),
        { status: 200 },
      ),
    );
  });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "two.txt" })).toBeVisible();
});

it("retains a newer refresh when an older same-project request completes", async () => {
  const { counts, release, doc } = await setup("reload");
  fireEvent.click(screen.getByRole("button", { name: "更新" }));
  await waitFor(() => expect(counts.pending).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "更新" }));
  await screen.findByRole("button", { name: "newest.txt" });
  await act(async () => {
    release(
      new Response(JSON.stringify([doc("one", "obsolete.txt")]), {
        status: 200,
      }),
    );
  });
  expect(screen.getByRole("button", { name: "newest.txt" })).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "obsolete.txt" }),
  ).not.toBeInTheDocument();
});

it.each([false, true])(
  "ignores obsolete publication callbacks after switching (rejected=%s)",
  async (rejected) => {
    const { counts, release } = await setup("publication");
    fireEvent.click(screen.getByRole("button", { name: "公開先" }));
    fireEvent.click(screen.getByRole("button", { name: "公開設定を保存" }));
    await waitFor(() => expect(counts.pending).toBe(true));
    await switchProject();
    await act(async () => {
      release(
        rejected
          ? new Response(JSON.stringify({ detail: "old project error" }), {
              status: 403,
            })
          : new Response(null, { status: 204 }),
      );
    });
    expect(screen.getByRole("button", { name: "two.txt" })).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(counts.one).toBe(1);
  },
);
