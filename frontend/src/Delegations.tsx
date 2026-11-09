import { useEffect, useMemo, useRef, useState } from "react";
import { api, errorText, json } from "./api";

interface DelegationProject {
  id: string;
  name: string;
  recipients: { id: string; username: string }[];
  permission_ceiling: string[];
}
interface DelegationEvent {
  type: string;
  at: number;
  actor_id: string;
}
interface Delegation {
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
  status: "active" | "expired" | "ended" | "superseded";
  events: DelegationEvent[];
}
interface DelegationOptions {
  projects: DelegationProject[];
}

const permissionNames: Record<string, string> = {
  read: "閲覧",
  retrieve: "チャット参照",
  upload: "資料追加",
  publish: "資料公開",
};
const ttlChoices = [
  { seconds: 900, label: "15分" },
  { seconds: 3600, label: "1時間" },
  { seconds: 86400, label: "1日" },
  { seconds: 604800, label: "7日" },
];
const eventNames: Record<string, string> = {
  revoke: "付与者が取り消し",
  cancel: "受領者が取り消し",
  expire: "期限切れ",
  invalidate: "権限変更により無効",
  supersede: "新しい委任に置き換え",
};

function delegationState(grant: Delegation): string {
  if (grant.status === "active") return "有効";
  if (grant.status === "expired") return "期限切れ";
  const latestEvent = grant.events.at(-1);
  if (latestEvent) return eventNames[latestEvent.type] ?? "終了";
  return grant.status === "superseded" ? "置き換え済み" : "終了";
}

export function AdminDelegations() {
  const [options, setOptions] = useState<DelegationOptions | null>(null);
  const [grants, setGrants] = useState<Delegation[]>([]);
  const [actorId, setActorId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [recipientId, setRecipientId] = useState("");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [ttl, setTtl] = useState("86400");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState<{
    grant: Delegation;
    action: "revoke" | "cancel";
  } | null>(null);
  const mutationPending = useRef(false);
  const selectedProject = useMemo(
    () => options?.projects.find((project) => project.id === projectId),
    [options, projectId],
  );

  async function reload(signal?: AbortSignal) {
    const [user, available, listed] = await Promise.all([
      api<{ id: string }>("/auth/me", { signal }),
      api<DelegationOptions>("/admin/delegations/options", { signal }),
      api<Delegation[]>("/admin/delegations", { signal }),
    ]);
    if (signal?.aborted) return;
    setActorId(user.id);
    setOptions(available);
    setGrants(listed);
    setProjectId((current) => {
      if (available.projects.some((project) => project.id === current))
        return current;
      return available.projects[0]?.id ?? "";
    });
  }

  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve()
      .then(() => {
        if (!controller.signal.aborted) return reload(controller.signal);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorText(reason));
      });
    return () => controller.abort();
  }, []);

  async function createGrant(event: React.FormEvent) {
    event.preventDefault();
    if (mutationPending.current) return;
    setError("");
    setNotice("");
    const seconds = Number(ttl);
    if (!Number.isInteger(seconds) || seconds < 900 || seconds > 604800) {
      setError("委任の有効期間は15分〜7日で指定してください。");
      return;
    }
    if (!selectedProject || !recipientId || !permissions.length) {
      setError("プロジェクト・受領者・委任する権限を指定してください。");
      return;
    }
    if (
      permissions.some(
        (permission) =>
          !selectedProject.permission_ceiling.includes(permission),
      )
    ) {
      setError("委任する権限が本人の委任上限を超えています。");
      return;
    }
    if (permissions.includes("retrieve") && !permissions.includes("read")) {
      setError("チャット参照を委任するには閲覧権限も必要です。");
      return;
    }
    mutationPending.current = true;
    setBusy(true);
    try {
      await api<Delegation>(
        "/admin/delegations",
        json("POST", {
          project_id: projectId,
          recipient_id: recipientId,
          permissions,
          ttl_seconds: seconds,
        }),
      );
      await reload();
      setRecipientId("");
      setPermissions([]);
      setTtl("86400");
      setNotice("管理委任を作成しました。");
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }

  async function endGrant() {
    if (!confirmation || mutationPending.current) return;
    mutationPending.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    const { grant, action } = confirmation;
    try {
      await api(
        `/admin/delegations/${encodeURIComponent(grant.id)}${action === "cancel" ? "/cancel" : ""}`,
        json("DELETE"),
      );
      await reload();
      setConfirmation(null);
      setNotice(
        action === "revoke"
          ? "管理委任を取り消しました。"
          : "受領した管理委任を取り消しました。",
      );
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }

  function togglePermission(permission: string) {
    setPermissions((current) => {
      if (current.includes(permission)) {
        const next = current.filter((item) => item !== permission);
        return permission === "read"
          ? next.filter((item) => item !== "retrieve")
          : next;
      }
      return permission === "retrieve"
        ? Array.from(new Set([...current, "read", permission]))
        : [...current, permission];
    });
  }

  return (
    <section className="admin-delegations" aria-label="管理委任">
      <p className="muted">
        プロジェクトの委任可能な権限を、選択した受領者へ15分〜7日間付与します。最終的な権限と有効期間はサーバーで確認されます。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <form
        className="admin-delegation-form"
        onSubmit={(event) => void createGrant(event)}
      >
        <h2>管理委任を作成</h2>
        <label>
          プロジェクト
          <select
            aria-label="委任するプロジェクト"
            value={projectId}
            disabled={busy || !options?.projects.length}
            onChange={(event) => {
              setProjectId(event.target.value);
              setRecipientId("");
              setPermissions([]);
            }}
          >
            {options?.projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
            {!options?.projects.length && (
              <option value="">委任可能なプロジェクトはありません</option>
            )}
          </select>
        </label>
        <label>
          受領者
          <select
            aria-label="委任の受領者"
            required
            value={recipientId}
            disabled={busy || !selectedProject?.recipients.length}
            onChange={(event) => setRecipientId(event.target.value)}
          >
            <option value="">受領者を選択</option>
            {selectedProject?.recipients.map((recipient) => (
              <option key={recipient.id} value={recipient.id}>
                {recipient.username}
              </option>
            ))}
          </select>
        </label>
        <fieldset
          className="delegation-permissions"
          disabled={busy || !selectedProject}
        >
          <legend>委任する権限（本人の委任上限内）</legend>
          {Object.entries(permissionNames)
            .filter(([permission]) =>
              selectedProject?.permission_ceiling.includes(permission),
            )
            .map(([permission, label]) => (
              <button
                key={permission}
                type="button"
                aria-pressed={permissions.includes(permission)}
                onClick={() => togglePermission(permission)}
              >
                {label}
              </button>
            ))}
          {!selectedProject?.permission_ceiling.length && (
            <p>委任できる権限はありません。</p>
          )}
        </fieldset>
        <label>
          有効期間
          <select
            aria-label="委任の有効期間"
            value={ttl}
            disabled={busy}
            onChange={(event) => setTtl(event.target.value)}
          >
            {ttlChoices.map((choice) => (
              <option key={choice.seconds} value={choice.seconds}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        <p className="muted">
          最短15分、最長7日です。チャット参照には閲覧権限も必要です。
        </p>
        <button
          type="submit"
          disabled={
            busy || !selectedProject || !selectedProject.recipients.length
          }
        >
          管理委任を作成
        </button>
      </form>

      <div className="section-toolbar">
        <h2>自分に関係する委任</h2>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setError("");
            setBusy(true);
            void reload()
              .catch((reason) => setError(errorText(reason)))
              .finally(() => setBusy(false));
          }}
        >
          更新
        </button>
      </div>
      {!options && !error ? (
        <p role="status">管理委任を読み込んでいます。</p>
      ) : null}
      {grants.length === 0 ? (
        <p className="empty">表示できる管理委任はありません。</p>
      ) : (
        <ul className="admin-delegation-list">
          {grants.map((grant) => {
            const asGrantor = grant.grantor_id === actorId;
            const target = asGrantor
              ? grant.recipient_username
              : grant.grantor_username;
            const action = asGrantor ? "revoke" : "cancel";
            const actionLabel = asGrantor
              ? "取り消し"
              : "受領した委任を取り消す";
            return (
              <li key={grant.id} className="admin-delegation-row">
                <article aria-label={`管理委任 ${grant.id}`}>
                  <h3>
                    {options?.projects.find(
                      (project) => project.id === grant.project_id,
                    )?.name ?? grant.project_id}{" "}
                    · {asGrantor ? `受領者 ${target}` : `付与者 ${target}`}
                  </h3>
                  <dl>
                    <dt>状態</dt>
                    <dd>{delegationState(grant)}</dd>
                    <dt>権限</dt>
                    <dd>
                      {grant.permissions
                        .map(
                          (permission) =>
                            permissionNames[permission] ?? permission,
                        )
                        .join("・")}
                    </dd>
                    <dt>有効期限</dt>
                    <dd>
                      {new Date(grant.expires * 1000).toLocaleString("ja-JP")}
                    </dd>
                    <dt>委任ID</dt>
                    <dd>{grant.id}</dd>
                    <dt>プロジェクトID</dt>
                    <dd>{grant.project_id}</dd>
                  </dl>
                  {grant.status === "active" && (
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={`${target}への委任 ${grant.id} を${actionLabel}`}
                      onClick={() => {
                        setError("");
                        setNotice("");
                        setConfirmation({ grant, action });
                      }}
                    >
                      {actionLabel}
                    </button>
                  )}
                  {confirmation?.grant.id === grant.id && (
                    <div
                      role="group"
                      aria-label={`${grant.id}の${action === "revoke" ? "取り消し" : "受領委任の取り消し"}確認`}
                    >
                      <p>
                        委任ID「{grant.id}」を
                        {action === "revoke"
                          ? `「${target}」（利用者ID: ${grant.recipient_id}）への付与者として`
                          : `「${target}」（付与者ID: ${grant.grantor_id}）から受領した権限として`}
                        取り消します。プロジェクト「{grant.project_id}
                        」の権限が失われます。
                      </p>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={`${grant.id}の${action === "revoke" ? "取り消し" : "受領委任の取り消し"}を確認`}
                        onClick={() => void endGrant()}
                      >
                        {action === "revoke"
                          ? "この委任を取り消す"
                          : "受領した委任を取り消す"}
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        aria-label={`${grant.id}の委任取り消しをやめる`}
                        onClick={() => setConfirmation(null)}
                      >
                        取り消しをやめる
                      </button>
                    </div>
                  )}
                </article>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
