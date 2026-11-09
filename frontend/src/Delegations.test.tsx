import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AdminDelegations } from "./Delegations";

const project = {
  id: "project-a",
  name: "研究プロジェクト",
  recipients: [{ id: "recipient-id", username: "bob" }],
  permission_ceiling: ["read", "retrieve", "upload"],
};
type MockGrant = {
  id: string;
  version: number;
  project_id: string;
  grantor_id: string;
  grantor_username: string;
  recipient_id: string;
  recipient_username: string;
  permissions: string[];
  created: number;
  expires: number;
  status: "active" | "ended" | "expired";
  events: { type: string; at: number; actor_id: string }[];
};
const grant: MockGrant = {
  id: "grant-exact-123",
  version: 1,
  project_id: "project-a",
  grantor_id: "actor-id",
  grantor_username: "alice",
  recipient_id: "recipient-id",
  recipient_username: "bob",
  permissions: ["read"],
  created: 1_800_000_000,
  expires: 1_800_086_400,
  status: "active" as const,
  events: [],
};
const received = {
  ...grant,
  id: "grant-received-456",
  grantor_id: "other-id",
  grantor_username: "carol",
  recipient_id: "actor-id",
  recipient_username: "alice",
};
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

function mockApi({
  failCreate = false,
  failCreateStatus = 422,
  failOptions = false,
  initialGrants = [grant, received],
}: {
  failCreate?: boolean;
  failCreateStatus?: number;
  failOptions?: boolean;
  initialGrants?: MockGrant[];
} = {}) {
  let grants: MockGrant[] = initialGrants;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/auth/me")) return respond({ id: "actor-id" });
      if (path.endsWith("/admin/delegations/options"))
        return failOptions
          ? respond({ detail: "委任管理の権限がありません（403）" }, 403)
          : respond({ projects: [project] });
      if (path.endsWith("/admin/delegations") && options?.method === "POST") {
        if (failCreate)
          return failCreateStatus === 403
            ? respond({ detail: "委任する権限がありません（403）" }, 403)
            : respond({ detail: "有効期間は900〜604800秒です（422）" }, 422);
        grants = [
          ...grants,
          {
            ...grant,
            id: "grant-created-789",
            permissions: ["read", "retrieve"],
          },
        ];
        return respond(
          { id: "grant-created-789", expires: 1_800_086_400 },
          201,
        );
      }
      if (
        path.endsWith("/admin/delegations") &&
        (!options?.method || options.method === "GET")
      )
        return respond(grants);
      if (
        path.includes("/admin/delegations/") &&
        options?.method === "DELETE"
      ) {
        const id = path.includes("/cancel")
          ? "grant-received-456"
          : "grant-exact-123";
        grants = grants.map((item) =>
          item.id === id
            ? {
                ...item,
                status: "ended",
                events: [
                  {
                    type: path.includes("/cancel") ? "cancel" : "revoke",
                    at: 1_800_000_100,
                    actor_id: "actor-id",
                  },
                ],
              }
            : item,
        );
        return respond({ id, ended: true, changed: true });
      }
      return respond({});
    }),
  );
}

it("creates a grant with a permission subset and TTL, and retains fields on server validation failure", async () => {
  mockApi({ failCreate: true });
  render(<AdminDelegations />);
  await screen.findByLabelText("委任の受領者");
  fireEvent.change(screen.getByLabelText("委任の受領者"), {
    target: { value: "recipient-id" },
  });
  fireEvent.click(screen.getByRole("button", { name: "閲覧" }));
  fireEvent.click(screen.getByRole("button", { name: "チャット参照" }));
  fireEvent.change(screen.getByLabelText("委任の有効期間"), {
    target: { value: "604800" },
  });
  fireEvent.click(screen.getByRole("button", { name: "管理委任を作成" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "有効期間は900〜604800秒です（422）",
  );
  expect(screen.getByLabelText("委任の受領者")).toHaveValue("recipient-id");
  expect(screen.getByRole("button", { name: "閲覧" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "チャット参照" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByLabelText("委任の有効期間")).toHaveValue("604800");
  expect(
    requests.some(
      ({ path, options }) =>
        path.endsWith("/admin/delegations") &&
        options?.method === "POST" &&
        JSON.stringify(JSON.parse(String(options.body))) ===
          JSON.stringify({
            project_id: "project-a",
            recipient_id: "recipient-id",
            permissions: ["read", "retrieve"],
            ttl_seconds: 604800,
          }),
    ),
  ).toBe(true);
});

it("confirms an exact grantor revoke and displays the ended status", async () => {
  mockApi();
  render(<AdminDelegations />);
  const target = await screen.findByRole("article", {
    name: "管理委任 grant-exact-123",
  });
  fireEvent.click(
    within(target).getByRole("button", {
      name: "bobへの委任 grant-exact-123 を取り消し",
    }),
  );
  const confirmation = within(target).getByRole("group", {
    name: "grant-exact-123の取り消し確認",
  });
  expect(confirmation).toHaveTextContent("grant-exact-123");
  expect(confirmation).toHaveTextContent("bob");
  expect(confirmation).toHaveTextContent("利用者ID: recipient-id");
  expect(
    requests.some(
      ({ path, options }) =>
        path.includes("grant-exact-123") && options?.method === "DELETE",
    ),
  ).toBe(false);
  fireEvent.click(
    within(confirmation).getByRole("button", {
      name: "grant-exact-123の取り消しを確認",
    }),
  );
  await waitFor(() =>
    expect(
      requests.some(
        ({ path, options }) =>
          path.endsWith("/admin/delegations/grant-exact-123") &&
          options?.method === "DELETE",
      ),
    ).toBe(true),
  );
  expect(await within(target).findByText("付与者が取り消し")).toBeVisible();
});

it("lets the recipient cancel a received grant with an explicit target", async () => {
  mockApi();
  render(<AdminDelegations />);
  const target = await screen.findByRole("article", {
    name: "管理委任 grant-received-456",
  });
  fireEvent.click(
    within(target).getByRole("button", {
      name: "carolへの委任 grant-received-456 を受領した委任を取り消す",
    }),
  );
  const confirmation = within(target).getByRole("group", {
    name: "grant-received-456の受領委任の取り消し確認",
  });
  expect(confirmation).toHaveTextContent("carol");
  expect(confirmation).toHaveTextContent("付与者ID: other-id");
  fireEvent.click(
    within(confirmation).getByRole("button", {
      name: "grant-received-456の受領委任の取り消しを確認",
    }),
  );
  await waitFor(() =>
    expect(
      requests.some(
        ({ path, options }) =>
          path.endsWith("/grant-received-456/cancel") &&
          options?.method === "DELETE",
      ),
    ).toBe(true),
  );
  expect(await within(target).findByText("受領者が取り消し")).toBeVisible();
});

it("rejects an out-of-range TTL before sending and surfaces forbidden and validation errors", async () => {
  mockApi({ failCreate: true });
  render(<AdminDelegations />);
  await screen.findByLabelText("委任の受領者");
  fireEvent.change(screen.getByLabelText("委任の受領者"), {
    target: { value: "recipient-id" },
  });
  fireEvent.click(screen.getByRole("button", { name: "閲覧" }));
  fireEvent.change(screen.getByLabelText("委任の有効期間"), {
    target: { value: "899" },
  });
  fireEvent.click(screen.getByRole("button", { name: "管理委任を作成" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("15分〜7日");
  expect(
    requests.some(
      ({ path, options }) =>
        path.endsWith("/admin/delegations") && options?.method === "POST",
    ),
  ).toBe(false);
  expect(screen.getByLabelText("委任の受領者")).toHaveValue("recipient-id");

  fireEvent.change(screen.getByLabelText("委任の有効期間"), {
    target: { value: "900" },
  });
  fireEvent.click(screen.getByRole("button", { name: "管理委任を作成" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "有効期間は900〜604800秒です（422）",
  );
  expect(screen.getByLabelText("委任の有効期間")).toHaveValue("900");
  expect(screen.getByRole("button", { name: "閲覧" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

it("surfaces a forbidden grant response without losing the form", async () => {
  mockApi({ failCreate: true, failCreateStatus: 403 });
  render(<AdminDelegations />);
  await screen.findByLabelText("委任の受領者");
  fireEvent.change(screen.getByLabelText("委任の受領者"), {
    target: { value: "recipient-id" },
  });
  fireEvent.click(screen.getByRole("button", { name: "閲覧" }));
  fireEvent.click(screen.getByRole("button", { name: "管理委任を作成" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "委任する権限がありません（403）",
  );
  expect(screen.getByLabelText("委任の受領者")).toHaveValue("recipient-id");
  expect(screen.getByRole("button", { name: "閲覧" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

it("shows expired grants as unavailable and keeps them in the history", async () => {
  mockApi({
    initialGrants: [
      {
        ...grant,
        id: "expired-grant",
        status: "ended",
        events: [{ type: "expire", at: 1_800_000_001, actor_id: "system" }],
      },
    ],
  });
  render(<AdminDelegations />);
  const expired = await screen.findByRole("article", {
    name: "管理委任 expired-grant",
  });
  expect(within(expired).getByText("期限切れ")).toBeVisible();
  expect(
    within(expired).queryByRole("button", { name: /取り消し/ }),
  ).not.toBeInTheDocument();
});

it("surfaces forbidden options as an accessible error", async () => {
  mockApi({ failOptions: true });
  render(<AdminDelegations />);
  expect(await screen.findByRole("alert")).toHaveTextContent("（403）");
});
