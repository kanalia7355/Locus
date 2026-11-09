import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText, json } from "./api";

interface ProjectMember {
  user_id: string;
  username: string;
  role: string;
  roles?: string[];
  denied_permissions?: string[];
  effective_permissions?: string[];
}
interface ProjectRole {
  id: string;
  name: string;
}
interface AdminProject {
  id: string;
  org_id: string;
  name: string;
  members: ProjectMember[];
  roles: ProjectRole[];
}
interface AdminUser {
  id: string;
  username: string;
  enabled: boolean;
  system_admin: boolean;
}

const permissionLabels: Record<string, string> = {
  read: "閲覧",
  retrieve: "チャット参照",
  upload: "資料追加",
  publish: "資料公開",
  manage_roles: "役割管理",
  manage_members: "所属管理",
};
const membershipPermissions = Object.keys(permissionLabels);

const roleLabels: Record<string, string> = {
  organization_admin: "組織管理者",
  assistant_admin: "アシスタント管理者",
  project_lead: "プロジェクト責任者",
  researcher: "研究者",
  research_assistant: "研究補助者",
  general_user: "一般利用者",
  viewer: "閲覧者",
  guest: "ゲスト",
  auditor: "監査担当者",
};

export function AdminProjects() {
  const [projects, setProjects] = useState<AdminProject[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [projectId, setProjectId] = useState("");
  const [orgId, setOrgId] = useState("");
  const [name, setName] = useState("");
  const [memberUsers, setMemberUsers] = useState<Record<string, string>>({});
  const [memberRoles, setMemberRoles] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [membershipConfirmation, setMembershipConfirmation] = useState<{
    projectId: string;
    userId: string;
    username: string;
    projectName: string;
  } | null>(null);
  const mutationPending = useRef(false);

  const reload = useCallback(async () => {
    const [items, userItems] = await Promise.all([
      api<AdminProject[]>("/admin/projects"),
      api<AdminUser[]>("/admin/users"),
    ]);
    setProjects(items);
    setUsers(userItems);
    const enabledUsers = userItems.filter(
      (user) => user.enabled && !user.system_admin,
    );
    setMemberUsers((current) => {
      const next = { ...current };
      for (const project of items)
        if (!enabledUsers.some((user) => user.id === next[project.id]))
          next[project.id] = enabledUsers[0]?.id ?? "";
      return next;
    });
    setMemberRoles((current) => {
      const next = { ...current };
      for (const project of items)
        if (!project.roles.some((role) => role.id === next[project.id]))
          next[project.id] =
            project.roles.find((role) => role.id === "viewer")?.id ??
            project.roles[0]?.id ??
            "";
      return next;
    });
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active)
        void reload().catch((reason) => {
          if (active) setError(errorText(reason));
        });
    });
    return () => {
      active = false;
    };
  }, [reload]);

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await api<AdminProject>(
        "/admin/projects",
        json("POST", { project_id: projectId, org_id: orgId, name }),
      );
      setProjectId("");
      setOrgId("");
      setName("");
      setNotice("プロジェクトを作成しました。");
      await reload();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  async function changeRoleHolding(
    project: AdminProject,
    username: string,
    roleId: string,
  ) {
    if (mutationPending.current) return;
    mutationPending.current = true;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await api(
        `/projects/${encodeURIComponent(project.id)}/members/${encodeURIComponent(username)}/roles/${encodeURIComponent(roleId)}`,
        json("DELETE"),
      );
      await reload();
      setNotice("ロールの所属を更新しました。");
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }

  async function changeMember(
    project: AdminProject,
    userId: string,
    role: string | null,
  ) {
    if (mutationPending.current) return;
    mutationPending.current = true;
    setError("");
    setNotice("");
    setBusy(true);
    try {
      if (role === null) {
        await api(
          `/admin/projects/${encodeURIComponent(project.id)}/members/${encodeURIComponent(userId)}`,
          json("DELETE"),
        );
        setProjects((current) =>
          current.map((item) =>
            item.id === project.id
              ? {
                  ...item,
                  members: item.members.filter(
                    (member) => member.user_id !== userId,
                  ),
                }
              : item,
          ),
        );
        setMembershipConfirmation(null);
      } else {
        const username = users.find((user) => user.id === userId)?.username;
        if (!username) throw new Error("利用者を確認できません。更新してください。");
        await api(
          `/projects/${encodeURIComponent(project.id)}/members/${encodeURIComponent(username)}/roles/${encodeURIComponent(role)}`,
          json("POST"),
        );
        await reload();
      }
      setNotice("プロジェクトの所属を更新しました。");
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      mutationPending.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="admin-projects" aria-label="プロジェクト設定">
      <p className="muted">
        プロジェクトと所属を管理します。所属変更は既存の権限と監査規則に従います。
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <form
        className="admin-project-form"
        onSubmit={(event) => void createProject(event)}
      >
        <h2>プロジェクトを作成</h2>
        <label>
          プロジェクトID
          <input
            aria-label="新しいプロジェクトID"
            required
            maxLength={64}
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
          />
        </label>
        <label>
          組織ID
          <input
            aria-label="組織ID"
            required
            maxLength={64}
            value={orgId}
            onChange={(event) => setOrgId(event.target.value)}
          />
        </label>
        <label>
          プロジェクト名
          <input
            aria-label="新しいプロジェクト名"
            required
            maxLength={128}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <button type="submit" disabled={busy}>
          プロジェクトを作成
        </button>
      </form>
      <h2>プロジェクト一覧</h2>
      {projects.length === 0 ? (
        <p className="empty">プロジェクトはありません。</p>
      ) : (
        projects.map((project) => (
          <article className="admin-project-row" key={project.id}>
            <h3>{project.name}</h3>
            <p className="muted">
              {project.id} · {project.org_id}
            </p>
            <ul className="admin-project-members">
              {project.members.length ? (
                project.members.map((member) => (
                  <li key={member.user_id}>
                    <span>
                      {member.username} ·{" "}
                      {(member.roles?.length ? member.roles : [member.role])
                        .map(
                          (roleId) =>
                            roleLabels[roleId] ??
                            project.roles.find((role) => role.id === roleId)
                              ?.name ??
                            roleId,
                        )
                        .join("・")}
                    </span>
                    <p>
                      実効権限（各ロールの和集合、拒否を適用後）:{" "}
                      {(member.effective_permissions ?? [])
                        .map((permission) => permissionLabels[permission] ?? permission)
                        .join("・") || "なし"}
                    </p>
                    <p>
                      明示的な拒否: {(member.denied_permissions ?? [])
                        .map((permission) => permissionLabels[permission] ?? permission)
                        .join("・") || "なし"}
                    </p>
                    {(member.roles?.length ? member.roles : [member.role]).map((roleId) => (
                      <button
                        key={roleId}
                        type="button"
                        disabled={busy || (member.roles?.length ?? 1) <= 1}
                        aria-label={`${member.username}の${roleLabels[roleId] ?? roleId}ロールを外す`}
                        onClick={() => void changeRoleHolding(project, member.username, roleId)}
                      >
                        {roleLabels[roleId] ?? project.roles.find((role) => role.id === roleId)?.name ?? roleId}を外す
                      </button>
                    ))}
                    <MembershipDenials
                      projectId={project.id}
                      projectName={project.name}
                      member={member}
                      onError={setError}
                      onSaved={reload}
                      disabled={busy}
                    />
                    <button
                      type="button"
                      disabled={busy}
                      aria-label={`${member.username}を${project.name}から外す`}
                      onClick={() => {
                        setError("");
                        setNotice("");
                        setMembershipConfirmation({
                          projectId: project.id,
                          userId: member.user_id,
                          username: member.username,
                          projectName: project.name,
                        });
                      }}
                    >
                      所属を外す
                    </button>
                    {membershipConfirmation?.projectId === project.id &&
                      membershipConfirmation.userId === member.user_id && (
                        <div
                          role="group"
                          aria-label={`${member.username}の所属削除確認`}
                        >
                          <p>
                            「{member.username}」（利用者ID: {member.user_id}）を、
                            「{project.name}」（プロジェクトID: {project.id}）から外します。
                            このプロジェクトへのアクセスが失われます。
                          </p>
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={`${member.username}を${project.name}から外す（確認）`}
                            onClick={() =>
                              void changeMember(project, member.user_id, null)
                            }
                          >
                            所属を外す
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            aria-label={`${member.username}の所属削除を取り消す`}
                            onClick={() => setMembershipConfirmation(null)}
                          >
                            取り消す
                          </button>
                        </div>
                      )}
                  </li>
                ))
              ) : (
                <li className="muted">所属している利用者はいません。</li>
              )}
            </ul>
            <div className="admin-project-controls">
              <label>
                利用者
                <select
                  aria-label={`${project.name}の利用者`}
                  value={memberUsers[project.id] ?? ""}
                  onChange={(event) =>
                    setMemberUsers((current) => ({
                      ...current,
                      [project.id]: event.target.value,
                    }))
                  }
                >
                  {users
                    .filter((user) => user.enabled && !user.system_admin)
                    .map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.username}
                      </option>
                    ))}
                  {!users.some(
                    (user) => user.enabled && !user.system_admin,
                  ) && <option value="">割り当て可能な利用者はいません</option>}
                </select>
              </label>
              <label>
                役割
                <select
                  aria-label={`${project.name}の役割`}
                  value={memberRoles[project.id] ?? ""}
                  onChange={(event) =>
                    setMemberRoles((current) => ({
                      ...current,
                      [project.id]: event.target.value,
                    }))
                  }
                >
                  {project.roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {roleLabels[role.id] ?? role.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                disabled={
                  busy ||
                  !memberUsers[project.id] ||
                  !memberRoles[project.id] ||
                  !!project.members.find(
                    (member) =>
                      member.user_id === memberUsers[project.id] &&
                      (member.roles ?? [member.role]).includes(memberRoles[project.id]),
                  )
                }
                onClick={() =>
                  void changeMember(
                    project,
                    memberUsers[project.id],
                    memberRoles[project.id],
                  )
                }
              >
                利用者にロールを追加
              </button>
            </div>
          </article>
        ))
      )}
    </section>
  );
}

type ScannerOutcome = "clean" | "rejected" | "unavailable" | null;

interface StorageStatus {
  backend: string;
  mode: string;
  external_enabled: boolean;
  accepted_formats: string[];
  max_file_bytes: number;
  ingestion_queue_limit: number;
  per_user_ingestion_queue_limit: number;
  scanner_configured: boolean;
  scanner_last_outcome: ScannerOutcome;
  ingestion_status_counts: Record<string, number>;
  configuration_available: boolean;
}

// Adapter configuration and the operational scan outcome are reported
// separately: 有効 (running), 検査不能 (configured but the check could not
// run), 拒否 (the check ran and explicitly rejected the content).
function scannerStatusText(status: StorageStatus): string {
  if (!status.scanner_configured) {
    return "未接続（既定拒否）・安全検査を実行できない資料は隔離され、検索には使われません";
  }
  if (status.scanner_last_outcome === "unavailable") {
    return "検査不能・安全検査は設定されていますが直近の検査を実行できず、該当資料は隔離されます（既定拒否）";
  }
  if (status.scanner_last_outcome === "rejected") {
    return "有効（拒否あり）・直近の検査で資料を拒否して隔離しました";
  }
  return "有効・安全検査を通過した資料のみ取り込みます";
}

function MembershipDenials({
  projectId,
  projectName,
  member,
  onError,
  onSaved,
  disabled,
}: {
  projectId: string;
  projectName: string;
  member: ProjectMember;
  onError: (error: string) => void;
  onSaved: () => Promise<void>;
  disabled: boolean;
}) {
  const [permission, setPermission] = useState("");
  const [pending, setPending] = useState(false);
  const denied = member.denied_permissions ?? [];
  const available = membershipPermissions.filter((item) => !denied.includes(item));
  async function save(next: string[]) {
    setPending(true);
    onError("");
    try {
      const username = encodeURIComponent(member.username);
      await api(
        `/projects/${encodeURIComponent(projectId)}/members/${username}/denials`,
        json("PUT", { denied_permissions: next }),
      );
      await onSaved();
      setPermission("");
    } catch (reason) {
      onError(errorText(reason));
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="membership-denials" aria-label={`${member.username}の拒否権限`}>
      <label>
        {projectName}・{member.username}に追加する拒否権限
        <select
          aria-label={`${member.username}に追加する拒否権限`}
          value={permission}
          disabled={disabled || pending || available.length === 0}
          onChange={(event) => setPermission(event.target.value)}
        >
          <option value="">権限を選択</option>
          {available.map((item) => (
            <option key={item} value={item}>{permissionLabels[item]}</option>
          ))}
        </select>
      </label>
      <button
        type="button"
        disabled={disabled || pending || !permission}
        onClick={() => void save([...denied, permission])}
      >
        拒否を追加
      </button>
      {denied.map((item) => (
        <button
          key={item}
          type="button"
          disabled={disabled || pending}
          aria-label={`${member.username}の${permissionLabels[item] ?? item}拒否を解除`}
          onClick={() => void save(denied.filter((entry) => entry !== item))}
        >
          {permissionLabels[item] ?? item}の拒否を解除
        </button>
      ))}
    </div>
  );
}

export function AdminStorage() {
  const [status, setStatus] = useState<StorageStatus | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void api<StorageStatus>("/admin/storage", { signal: controller.signal })
      .then((value) => setStatus(value))
      .catch((reason) => {
        if (!controller.signal.aborted) setError(errorText(reason));
      });
    return () => controller.abort();
  }, []);
  return (
    <section className="settings" aria-label="保存先設定">
      {error && <p role="alert">{error}</p>}
      <h2>現在の保存先</h2>
      {status ? (
        <dl className="admin-settings-list">
          <dt>バックエンド</dt>
          <dd>{status.backend}</dd>
          <dt>動作範囲</dt>
          <dd>
            {status.mode} · 外部保存 {status.external_enabled ? "有効" : "無効"}
          </dd>
          <dt>対応形式</dt>
          <dd>{status.accepted_formats.join("、")}</dd>
          <dt>1件あたりの上限</dt>
          <dd>{(status.max_file_bytes / 1024).toLocaleString("ja-JP")} KiB</dd>
          <dt>安全検査</dt>
          <dd>{scannerStatusText(status)}</dd>
          <dt>取り込み待ち上限</dt>
          <dd>
            全体 {status.ingestion_queue_limit}件 · 一人{" "}
            {status.per_user_ingestion_queue_limit}件
          </dd>
          <dt>資料の処理状態</dt>
          <dd>
            {Object.entries(status.ingestion_status_counts)
              .map(([key, count]) => `${key} ${count}件`)
              .join("、") || "登録済み資料なし"}
          </dd>
        </dl>
      ) : !error ? (
        <p role="status">保存先の状態を確認しています。</p>
      ) : null}
      <p className="muted">
        このプロトタイプではローカルのSQLite管理下に保存します。保存先の変更設定は存在しないため、ここでは変更できません。
      </p>
      <h2>外部保存先</h2>
      <p>
        未実装・無効（既定拒否）。外部保存を有効にする変更は、別途オーナー承認とセキュリティ審査を経るまで行いません。接続情報や資格情報は設定・収集しません。
      </p>
    </section>
  );
}

interface LoadStatus {
  model_slot: { enabled: boolean; busy: boolean };
  chat_queue: {
    queued: number;
    limit: number;
    per_user_limit: number;
    running_job: {
      id: string;
      username: string | null;
      started_at: number;
    } | null;
  };
}

export function AdminLoad() {
  const [status, setStatus] = useState<LoadStatus | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [version, setVersion] = useState(0);
  const [displayedRunningStart, setDisplayedRunningStart] = useState<{
    id: string;
    timestamp: number;
  } | null>(null);
  const runningJob = status?.chat_queue.running_job;
  const runningJobStartedAt =
    runningJob && displayedRunningStart?.id === runningJob.id
      ? displayedRunningStart.timestamp
      : runningJob?.started_at;
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setRefreshing(true);
      return api<LoadStatus>("/admin/load", { signal: controller.signal })
        .then((value) => {
          if (!controller.signal.aborted) {
            const runningJob = value.chat_queue.running_job;
            setDisplayedRunningStart((current) => {
              if (!runningJob) return null;
              return current?.id === runningJob.id
                ? current
                : { id: runningJob.id, timestamp: runningJob.started_at };
            });
            setStatus(value);
            setError("");
          }
        })
        .catch((reason) => {
          if (!controller.signal.aborted) setError(errorText(reason));
        })
        .finally(() => {
          if (!controller.signal.aborted) setRefreshing(false);
        });
    });
    return () => controller.abort();
  }, [version]);
  return (
    <section className="settings" aria-label="負荷・実行状況">
      <div className="section-toolbar">
        <p className="muted">
          現在のモデル枠と対話待ち行列を表示します。会話内容は表示しません。
        </p>
        <button
          type="button"
          disabled={refreshing}
          onClick={() => setVersion((current) => current + 1)}
        >
          更新
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {status ? (
        <dl className="admin-settings-list">
          <dt>モデル枠</dt>
          <dd>
            {status.model_slot.busy ? "実行中" : "空き"} · モデル{" "}
            {status.model_slot.enabled ? "有効" : "無効"}
          </dd>
          <dt>対話の待ち行列</dt>
          <dd>
            {status.chat_queue.queued} / {status.chat_queue.limit}件
          </dd>
          <dt>一人あたりの待ち上限</dt>
          <dd>{status.chat_queue.per_user_limit}件</dd>
          <dt>実行中の質問</dt>
          <dd>
            {runningJob
              ? `${runningJob.username ?? "利用者不明"} · ${runningJob.id} · ${new Date((runningJobStartedAt ?? runningJob.started_at) * 1000).toLocaleString("ja-JP")}`
              : "なし"}
          </dd>
        </dl>
      ) : !error ? (
        <p role="status">負荷状態を確認しています。</p>
      ) : null}
      <p className="muted">
        上限は開発用の安全上限であり、利用人数・処理能力の保証ではありません。
      </p>
    </section>
  );
}
