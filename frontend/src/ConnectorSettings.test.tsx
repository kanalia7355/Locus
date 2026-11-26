import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConnectorSettings } from "./ConnectorSettings";

const connectors = [
  {
    connector_id: "google_drive",
    configured: true,
    last_sync: {
      registered: 2,
      updated: 1,
      skipped: 3,
      failed: 0,
    },
  },
  { connector_id: "box", configured: false },
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

it("lists connector presence and last sync aggregates without credential inputs", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/admin/connectors")) return respond(connectors);
      return respond({});
    }),
  );
  render(<ConnectorSettings />);
  expect(await screen.findByText("google_drive")).toBeVisible();
  expect(screen.getByText("設定済み")).toBeVisible();
  expect(screen.getByText("box")).toBeVisible();
  expect(screen.getAllByText("サーバ側で未設定").length).toBeGreaterThanOrEqual(1);

  // Credentials are environment-managed: no credential input may exist.
  expect(document.querySelector('input[type="password"]')).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/資格情報|APIキー|シークレット|secret|token/i)).not.toBeInTheDocument();

  // Unconfigured connectors cannot be synced.
  const connectorSelect = screen.getByLabelText("コネクタ種別") as HTMLSelectElement;
  const boxOption = Array.from(connectorSelect.options).find((opt) => opt.value === "box");
  expect(boxOption?.disabled).toBe(true);

  // Only aggregate counts are surfaced, never document content or external ids.
  expect(
    screen.getByText(/最終同期: 登録 2件 \/ 更新 1件 \/ スキップ 3件 \/ 失敗 0件/),
  ).toBeVisible();
});

it("disables sync when selected connector is unconfigured and renders imported document origin", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/admin/connectors")) {
        return respond([
          { connector_id: "local_folder", configured: false },
          { connector_id: "google_drive", configured: false },
          { connector_id: "box", configured: true },
        ]);
      }
      if (path.includes("/documents?project_id=project-a")) {
        return respond([
          {
            id: "doc-1",
            name: "spec.txt",
            project_id: "project-a",
            kind: "personal",
            status: "ready",
            reason: "",
            conversation_id: null,
            created: 1,
            owned: true,
            source: "box / 研究資料",
          },
        ]);
      }
      if (path.endsWith("/admin/connectors/box/sync") && options?.method === "POST") {
        return respond({
          connector_id: "box",
          project_id: "project-a",
          registered: 1,
          updated: 0,
          skipped: 0,
          failed: 0,
        });
      }
      return respond({});
    }),
  );
  render(<ConnectorSettings />);
  await screen.findByText("設定済み");
  expect(screen.getAllByText("同期不可")).toHaveLength(2);
  fireEvent.change(screen.getByLabelText("同期先プロジェクトID"), {
    target: { value: "project-a" },
  });
  fireEvent.change(screen.getByLabelText("同期元ソース"), {
    target: { value: "研究資料" },
  });
  fireEvent.click(screen.getByRole("button", { name: "同期を実行" }));
  expect(await screen.findByText(/同期結果: 登録 1件/)).toBeVisible();
  expect(await screen.findByText(/Box \/ 研究資料/)).toBeVisible();
});

it("runs a manual sync and shows aggregate counts only", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith("/admin/connectors")) return respond([]);
      if (path.endsWith("/admin/connectors/box/sync") && options?.method === "POST") {
        return respond({
          connector_id: "box",
          project_id: "project-a",
          registered: 0,
          updated: 0,
          skipped: 1,
          failed: 0,
        });
      }
      return respond({});
    }),
  );
  render(<ConnectorSettings />);
  expect(await screen.findByText("box")).toBeVisible();
  fireEvent.change(screen.getByLabelText("同期先プロジェクトID"), {
    target: { value: "project-a" },
  });
  fireEvent.change(screen.getByLabelText("同期元ソース"), {
    target: { value: "research" },
  });
  fireEvent.click(screen.getByRole("button", { name: "同期を実行" }));
  expect(await screen.findByText(/スキップ 1件/)).toBeVisible();
});
