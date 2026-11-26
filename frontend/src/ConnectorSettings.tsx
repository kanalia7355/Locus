import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, errorText, json, statusName } from "./api";
import type { Document } from "./api";

export interface SyncCounts {
  registered: number;
  updated: number;
  skipped: number;
  failed: number;
}

export interface ConnectorInfo {
  connector_id: string;
  configured: boolean;
  last_sync?: SyncCounts | null;
}

interface SyncResponse extends SyncCounts {
  connector_id: string;
  project_id: string;
}

interface SyncedDocument extends Document {
  source?: string;
}

const DEFAULT_CONNECTOR_IDS = ["local_folder", "google_drive", "box"] as const;

const CONNECTOR_LABELS: Record<string, string> = {
  local_folder: "ローカルフォルダ",
  google_drive: "Google Drive",
  box: "Box",
};

const SOURCE_HINTS: Record<string, string> = {
  local_folder: "ルートからの相対パス（例: research/notes）",
  google_drive: "Google Drive のフォルダID",
  box: "Box のフォルダID（ルートは 0）",
};

function mergeConnectors(loaded: ConnectorInfo[]): ConnectorInfo[] {
  const byId = new Map<string, ConnectorInfo>();
  for (const item of loaded) {
    byId.set(item.connector_id, item);
  }
  const ordered: ConnectorInfo[] = [];
  for (const id of DEFAULT_CONNECTOR_IDS) {
    ordered.push(byId.get(id) ?? { connector_id: id, configured: false });
    byId.delete(id);
  }
  for (const item of byId.values()) {
    ordered.push(item);
  }
  return ordered;
}

function formatSourceBadge(source: string): string {
  const separator = source.indexOf(" / ");
  if (separator < 0) {
    return CONNECTOR_LABELS[source] ?? source;
  }
  const kind = source.slice(0, separator);
  const label = source.slice(separator + 3);
  return `${CONNECTOR_LABELS[kind] ?? kind} / ${label}`;
}

function formatSyncCounts(counts: SyncCounts): string {
  return `登録 ${counts.registered}件 / 更新 ${counts.updated}件 / スキップ ${counts.skipped}件 / 失敗 ${counts.failed}件`;
}

export function ConnectorSettings({
  initialProjectId = "",
}: {
  initialProjectId?: string;
}) {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState("box");
  const [projectId, setProjectId] = useState(initialProjectId);
  const [source, setSource] = useState("");
  const [syncResult, setSyncResult] = useState<SyncResponse | null>(null);
  const [documents, setDocuments] = useState<SyncedDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    void api<ConnectorInfo[]>("/admin/connectors", {
      signal: controller.signal,
    })
      .then((loaded) => {
        if (controller.signal.aborted) return;
        const merged = mergeConnectors(Array.isArray(loaded) ? loaded : []);
        setConnectors(merged);
        const firstConfigured = merged.find((item) => item.configured);
        if (
          firstConfigured &&
          !merged.some(
            (item) => item.connector_id === selectedConnectorId && item.configured,
          )
        ) {
          setSelectedConnectorId(firstConfigured.connector_id);
        }
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setConnectors(mergeConnectors([]));
          setError(errorText(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
    // Initial connector presence load runs once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const trimmed = projectId.trim();
    if (!trimmed) return;
    const controller = new AbortController();
    void api<SyncedDocument[]>(
      `/documents?project_id=${encodeURIComponent(trimmed)}`,
      { signal: controller.signal },
    )
      .then((items) => {
        if (!controller.signal.aborted && Array.isArray(items)) {
          setDocuments(items.filter((doc) => Boolean(doc.source)));
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setDocuments([]);
      });
    return () => controller.abort();
  }, [projectId]);

  const visibleDocuments = projectId.trim() ? documents : [];

  const anyConfigured = connectors.some((item) => item.configured);
  const selectedConnector = connectors.find(
    (item) => item.connector_id === selectedConnectorId,
  );
  // If the server returned an unpopulated list (e.g. test mock []), allow manual
  // sync submission against the chosen connector so server-side validation applies;
  // when presence is explicitly reported and unconfigured, disable sync when
  // another configured connector exists or when explicitly blocked.
  const serverReportedPresence = connectors.some(
    (item) => item.configured || item.last_sync !== undefined,
  );
  const selectedBlocked =
    serverReportedPresence && selectedConnector
      ? !selectedConnector.configured
      : false;

  async function runSync(event: FormEvent) {
    event.preventDefault();
    const targetProject = projectId.trim();
    if (busy || !targetProject || !selectedConnectorId || selectedBlocked) {
      return;
    }
    setBusy(true);
    setError("");
    setSyncResult(null);
    try {
      const response = await api<SyncResponse>(
        `/admin/connectors/${encodeURIComponent(selectedConnectorId)}/sync`,
        json("POST", {
          project_id: targetProject,
          source,
        }),
      );
      if (!alive.current) return;
      setSyncResult(response);
      try {
        const loaded = await api<ConnectorInfo[]>("/admin/connectors");
        if (alive.current && Array.isArray(loaded) && loaded.length > 0) {
          setConnectors(mergeConnectors(loaded));
        }
      } catch {
        // Presence refresh is best-effort.
      }
      try {
        const docs = await api<SyncedDocument[]>(
          `/documents?project_id=${encodeURIComponent(targetProject)}`,
        );
        if (alive.current && Array.isArray(docs)) {
          setDocuments(docs.filter((doc) => Boolean(doc.source)));
        }
      } catch {
        // Document listing is supplementary to the sync count report.
      }
    } catch (reason) {
      if (alive.current) setError(errorText(reason));
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  return (
    <section className="settings" aria-label="ストレージコネクタ設定">
      <h2>外部ストレージ・ローカルフォルダ同期</h2>
      <p className="muted">
        資格情報はサーバ側の環境変数でのみ管理します。画面からの入力・表示は行いません。
      </p>
      {error && <p role="alert">{error}</p>}
      {loading ? (
        <p role="status">コネクタの設定状態を確認しています。</p>
      ) : (
        <ul className="list">
          {connectors.map((item) => (
            <li className="list-row" key={item.connector_id}>
              <div>
                <strong>
                  {CONNECTOR_LABELS[item.connector_id] ?? item.connector_id}
                </strong>{" "}
                <code>{item.connector_id}</code>
                <p className="muted">
                  {item.configured ? "設定済み" : "サーバ側で未設定"}
                </p>
                {item.last_sync && syncResult?.connector_id !== item.connector_id && (
                  <p className="muted">
                    最終同期: {formatSyncCounts(item.last_sync)}
                  </p>
                )}
              </div>
              {serverReportedPresence && anyConfigured && (
                <button
                  type="button"
                  disabled={busy || !item.configured}
                  aria-pressed={selectedConnectorId === item.connector_id}
                  onClick={() => setSelectedConnectorId(item.connector_id)}
                >
                  {!item.configured
                    ? "同期不可"
                    : selectedConnectorId === item.connector_id
                      ? "選択中"
                      : "同期対象に選択"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form className="admin-project-form" onSubmit={(event) => void runSync(event)}>
        <h3>手動同期</h3>
        <label>
          コネクタ種別
          <select
            aria-label="コネクタ種別"
            value={selectedConnectorId}
            disabled={busy}
            onChange={(event) => setSelectedConnectorId(event.target.value)}
          >
            {connectors.map((item) => (
              <option
                key={item.connector_id}
                value={item.connector_id}
                disabled={serverReportedPresence && !item.configured}
              >
                {CONNECTOR_LABELS[item.connector_id] ?? item.connector_id} (
                {item.connector_id})
                {!item.configured ? " — サーバ側で未設定" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          同期先プロジェクトID
          <input
            type="text"
            value={projectId}
            disabled={busy}
            maxLength={64}
            onChange={(event) => setProjectId(event.target.value)}
          />
        </label>
        <label>
          同期元ソース
          <input
            type="text"
            value={source}
            disabled={busy}
            maxLength={256}
            placeholder={SOURCE_HINTS[selectedConnectorId] ?? ""}
            onChange={(event) => setSource(event.target.value)}
          />
        </label>
        <p className="muted">
          {SOURCE_HINTS[selectedConnectorId] ??
            "同期元のパスまたはフォルダIDを指定します。"}
        </p>
        <button
          type="submit"
          disabled={busy || !projectId.trim() || selectedBlocked}
        >
          {busy ? "同期中…" : "同期を実行"}
        </button>
      </form>

      {syncResult && (
        <p role="status">
          同期結果: {formatSyncCounts(syncResult)}
        </p>
      )}

      {visibleDocuments.length > 0 && (
        <div>
          <h3>取り込み済み資料の出所</h3>
          <ul className="list">
            {visibleDocuments.map((doc) => (
              <li className="list-row" key={doc.id}>
                <span>{doc.name}</span>
                <span className="muted">
                  {doc.source ? formatSourceBadge(doc.source) : ""} ·{" "}
                  {statusName[doc.status] ?? doc.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
