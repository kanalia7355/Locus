import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AdminLoad, AdminProjects, AdminStorage } from "./AdminSettings";

const project = {
  id: "project-a",
  org_id: "org-a",
  name: "合成プロジェクト",
  members: [{
    user_id: "user-a",
    username: "alice",
    role: "researcher",
    roles: ["researcher", "viewer"],
    denied_permissions: ["retrieve"],
    effective_permissions: ["read", "upload"],
  }],
  roles: [
    { id: "researcher", name: "researcher" },
    { id: "viewer", name: "viewer" },
  ],
};
const users = [
  { id: "user-a", username: "alice", enabled: true, system_admin: false },
  { id: "user-b", username: "bob", enabled: true, system_admin: false },
  { id: "user-c", username: "disabled", enabled: false, system_admin: false },
];
const requests: { path: string; options?: RequestInit }[] = [];
const respond = (data: unknown, status = 200) =>
  new Response(data === undefined ? null : JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });

afterEach(() => {
  vi.unstubAllGlobals();
  requests.length = 0;
});

it("lists projects, creates them and retains invalid form input", async () => {
  let failCreate = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/admin/projects") && options?.method === "POST") {
        if (failCreate)
          return respond({ detail: "プロジェクトIDを確認してください" }, 422);
        return respond(
          { id: "project-b", org_id: "org-b", name: "新しい合成案件" },
          201,
        );
      }
      if (path.endsWith("/admin/projects"))
        return respond([
          project,
          ...(failCreate
            ? []
            : [
                {
                  ...project,
                  id: "project-b",
                  members: [],
                  name: "新しい合成案件",
                },
              ]),
        ]);
      if (path.endsWith("/admin/users")) return respond(users);
      return respond({});
    }),
  );
  render(<AdminProjects />);
  expect(
    await screen.findByRole("heading", { name: "合成プロジェクト" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("option", { name: "disabled" }),
  ).not.toBeInTheDocument();
  const id = screen.getByLabelText("新しいプロジェクトID");
  const org = screen.getByLabelText("組織ID");
  const name = screen.getByLabelText("新しいプロジェクト名");
  fireEvent.change(id, { target: { value: "invalid/project" } });
  fireEvent.change(org, { target: { value: "org-b" } });
  fireEvent.change(name, { target: { value: "新しい合成案件" } });
  fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "プロジェクトIDを確認してください",
  );
  expect(id).toHaveValue("invalid/project");
  expect(org).toHaveValue("org-b");
  expect(name).toHaveValue("新しい合成案件");
  failCreate = false;
  fireEvent.click(screen.getByRole("button", { name: "プロジェクトを作成" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "プロジェクトを作成しました",
  );
  expect(
    await screen.findByRole("heading", { name: "新しい合成案件" }),
  ).toBeVisible();
  expect(id).toHaveValue("");
});

it("assigns/removes project members through role-holding endpoints", async () => {
  let members = project.members;
  let failAssignment = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/members/bob/roles/viewer") && options?.method === "POST") {
        if (failAssignment)
          return respond({ detail: "ロールの委任上限を超えています" }, 422);
        members = [
          ...project.members,
          {
            user_id: "user-b",
            username: "bob",
            role: "viewer",
            roles: ["viewer"],
            denied_permissions: [],
            effective_permissions: ["read", "retrieve"],
          },
        ];
        return respond(undefined, 204);
      }
      if (path.includes("/members/user-a") && options?.method === "DELETE") {
        members = [];
        return respond(undefined, 204);
      }
      if (path.endsWith("/admin/projects"))
        return respond([{ ...project, members }]);
      if (path.endsWith("/admin/users")) return respond(users);
      return respond({});
    }),
  );
  render(<AdminProjects />);
  await screen.findByRole("heading", { name: "合成プロジェクト" });
  expect(screen.getByText(/実効権限（各ロールの和集合、拒否を適用後）: 閲覧・資料追加/)).toBeVisible();
  expect(screen.getByText("明示的な拒否: チャット参照")).toBeVisible();
  await screen.findByRole("option", { name: "bob" });
  fireEvent.change(screen.getByLabelText("合成プロジェクトの利用者"), {
    target: { value: "user-b" },
  });
  fireEvent.change(screen.getByLabelText("合成プロジェクトの役割"), {
    target: { value: "viewer" },
  });
  fireEvent.click(screen.getByRole("button", { name: "利用者にロールを追加" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("ロールの委任上限を超えています");
  expect(screen.getByLabelText("合成プロジェクトの役割")).toHaveValue("viewer");
  expect(screen.queryByText("bob · 閲覧者")).not.toBeInTheDocument();
  failAssignment = false;
  fireEvent.click(screen.getByRole("button", { name: "利用者にロールを追加" }));
  await screen.findByText("bob · 閲覧者");
  expect(
    requests.some(
      ({ path, options }) =>
        path.endsWith("/projects/project-a/members/bob/roles/viewer") &&
        options?.method === "POST",
    ),
  ).toBe(true);
  const remove = screen.getByRole("button", {
    name: "aliceを合成プロジェクトから外す",
  });
  fireEvent.click(remove);
  expect(
    requests.some(
      ({ path, options }) =>
        path.endsWith("/members/user-a") && options?.method === "DELETE",
    ),
  ).toBe(false);
  expect(
    screen.getByRole("group", { name: "aliceの所属削除確認" }),
  ).toHaveTextContent("利用者ID: user-a");
  expect(
    screen.getByRole("group", { name: "aliceの所属削除確認" }),
  ).toHaveTextContent("プロジェクトID: project-a");
  fireEvent.click(screen.getByRole("button", { name: "aliceの所属削除を取り消す" }));
  expect(
    screen.queryByRole("group", { name: "aliceの所属削除確認" }),
  ).not.toBeInTheDocument();
  fireEvent.click(remove);
  fireEvent.click(
    screen.getByRole("button", {
      name: "aliceを合成プロジェクトから外す（確認）",
    }),
  );
  await waitFor(() =>
    expect(
      requests.some(
        ({ path, options }) =>
          path.endsWith("/members/user-a") && options?.method === "DELETE",
      ),
    ).toBe(true),
  );
  expect(
    screen.queryByRole("group", { name: "aliceの所属削除確認" }),
  ).not.toBeInTheDocument();
});

it("retains membership and confirmation on removal failure and prevents double submit", async () => {
  let finish!: (response: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/members/user-a") && options?.method === "DELETE")
        return new Promise<Response>((resolve) => { finish = resolve; });
      if (path.endsWith("/admin/projects")) return respond([project]);
      if (path.endsWith("/admin/users")) return respond(users);
      return respond({});
    }),
  );
  render(<AdminProjects />);
  await screen.findByRole("heading", { name: "合成プロジェクト" });
  fireEvent.click(
    screen.getByRole("button", { name: "aliceを合成プロジェクトから外す" }),
  );
  const confirm = screen.getByRole("button", {
    name: "aliceを合成プロジェクトから外す（確認）",
  });
  fireEvent.click(confirm);
  fireEvent.click(confirm);
  expect(confirm).toBeDisabled();
  expect(
    requests.filter(
      ({ path, options }) =>
        path.endsWith("/members/user-a") && options?.method === "DELETE",
    ),
  ).toHaveLength(1);
  finish(respond({ detail: "所属を変更できません" }, 503));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "所属を変更できません",
  );
  expect(screen.getByText(/alice · 研究者・閲覧者/)).toBeVisible();
  expect(
    screen.getByRole("group", { name: "aliceの所属削除確認" }),
  ).toBeVisible();
  expect(screen.getByRole("button", {
    name: "aliceを合成プロジェクトから外す（確認）",
  })).toBeEnabled();
});

it("adds membership denials through PH2-B and retains selection after an error", async () => {
  let denied = ["retrieve"];
  let failSave = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/members/alice/denials") && options?.method === "PUT") {
        if (failSave)
          return respond({ detail: "拒否権限を更新できません" }, 422);
        denied = JSON.parse(String(options.body)).denied_permissions;
        return respond({ username: "alice", project_id: "project-a", denied_permissions: denied });
      }
      if (path.endsWith("/admin/projects"))
        return respond([{
          ...project,
          members: project.members.map((member) => ({
            ...member,
            denied_permissions: denied,
            effective_permissions: ["read", "upload"].filter((item) => !denied.includes(item)),
          })),
        }]);
      if (path.endsWith("/admin/users")) return respond(users);
      return respond(undefined, 204);
    }),
  );
  render(<AdminProjects />);
  await screen.findByRole("heading", { name: "合成プロジェクト" });
  expect(screen.getByText("明示的な拒否: チャット参照")).toBeVisible();
  const permission = screen.getByLabelText("aliceに追加する拒否権限");
  fireEvent.change(permission, { target: { value: "upload" } });
  fireEvent.click(screen.getByRole("button", { name: "拒否を追加" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("拒否権限を更新できません");
  expect(permission).toHaveValue("upload");
  expect(requests.some(({ path, options }) => path.endsWith("/projects/project-a/members/alice/denials") && options?.method === "PUT")).toBe(true);
  failSave = false;
  fireEvent.click(screen.getByRole("button", { name: "拒否を追加" }));
  expect(await screen.findByText("明示的な拒否: チャット参照・資料追加")).toBeVisible();
  expect(permission).toHaveValue("");
});

it("shows local storage status and keeps external storage explicitly denied", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      requests.push({ path: String(input) });
      return respond({
        backend: "sqlite",
        mode: "local-only",
        external_enabled: false,
        accepted_formats: ["txt", "md", "csv"],
        max_file_bytes: 262144,
        ingestion_queue_limit: 32,
        per_user_ingestion_queue_limit: 4,
        scanner_configured: false,
        ingestion_status_counts: { ready: 2 },
        configuration_available: false,
      });
    }),
  );
  render(<AdminStorage />);
  expect(await screen.findByText("sqlite")).toBeVisible();
  expect(screen.getByText(/外部保存先/)).toBeVisible();
  expect(
    screen.getByText(/未接続（既定拒否）・安全検査を実行できない資料は隔離され、検索には使われません/),
  ).toBeVisible();
  expect(screen.getByText(/未実装・無効（既定拒否）/)).toBeVisible();
  expect(requests).toHaveLength(1);
  expect(requests[0].path).toContain("/admin/storage");
});

it("shows a configured fail-closed scanner without claiming production readiness", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      requests.push({ path: String(input) });
      return respond({
        backend: "sqlite",
        mode: "local-only",
        external_enabled: false,
        accepted_formats: ["txt", "md", "csv"],
        max_file_bytes: 262144,
        ingestion_queue_limit: 32,
        per_user_ingestion_queue_limit: 4,
        scanner_configured: true,
        ingestion_status_counts: {},
        configuration_available: false,
      });
    }),
  );
  render(<AdminStorage />);
  expect(
    await screen.findByText("有効・安全検査を通過した資料のみ取り込みます"),
  ).toBeVisible();
});

it("keeps a running job's displayed start time when refreshed cancellation metadata changes", async () => {
  let startedAt = 100;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      requests.push({ path: "/admin/load" });
      return respond({
        model_slot: { enabled: true, busy: true },
        chat_queue: {
          queued: 0,
          limit: 16,
          per_user_limit: 2,
          running_job: { id: "job-1", username: "alice", started_at: startedAt },
        },
      });
    }),
  );
  render(<AdminLoad />);
  const runningJob = await screen.findByText(/alice · job-1/);
  const originalDisplay = runningJob.textContent;
  startedAt = 200;
  fireEvent.click(screen.getByRole("button", { name: "更新" }));
  await waitFor(() => expect(requests).toHaveLength(2));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "更新" })).toBeEnabled(),
  );
  expect(screen.getByText(/alice · job-1/)).toHaveTextContent(originalDisplay!);
  expect(screen.getByText(/alice · job-1/)).not.toHaveTextContent(
    new Date(200 * 1000).toLocaleString("ja-JP"),
  );
});

it("displays only load metadata and reports refresh failures", async () => {
  let failRefresh = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      requests.push({ path: String(input) });
      if (failRefresh) return respond({ detail: "状態を確認できません" }, 503);
      return respond({
        model_slot: { enabled: true, busy: true },
        chat_queue: {
          queued: 2,
          limit: 16,
          per_user_limit: 2,
          running_job: { id: "job-1", username: "alice", started_at: 100 },
        },
      });
    }),
  );
  render(<AdminLoad />);
  expect(await screen.findByText(/alice · job-1/)).toBeVisible();
  expect(screen.getByText("2 / 16件")).toBeVisible();
  expect(
    screen.getByText("一人あたりの待ち上限").parentElement,
  ).not.toHaveTextContent("private question");
  failRefresh = true;
  fireEvent.click(screen.getByRole("button", { name: "更新" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "状態を確認できません",
  );
  expect(requests.every(({ path }) => !path.includes("messages"))).toBe(true);
});
