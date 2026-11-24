import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { UserCheck, UserX } from "lucide-react";
import { api, errorText, json } from "./api";
import type { Role, Roles } from "./api";
import { IconButton } from "./IconButton";
import { ProvisionUser } from "./ProvisionUser";

const permissionLabels: Record<string, string> = {
  read: "閲覧",
  retrieve: "チャット参照",
  upload: "資料追加",
  publish: "資料公開",
  manage_roles: "役割管理",
  manage_members: "所属管理",
};

export function RoleEditor({
  projectId,
  onError,
}: {
  projectId: string;
  onError: (error: string) => void;
}) {
  const [roles, setRoles] = useState<Roles | null>(null);
  const [name, setName] = useState("");
  const [permissions, setPermissions] = useState<string[]>([
    "read",
    "retrieve",
  ]);
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const alive = useRef(true);
  useEffect(() => {
    let active = true;
    alive.current = true;
    onError("");
    void api<Roles>(`/projects/${projectId}/roles`)
      .then((data) => {
        if (active) setRoles(data);
      })
      .catch((error) => {
        if (active) onError(errorText(error));
      });
    return () => {
      active = false;
      alive.current = false;
    };
  }, [projectId, onError]);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (
      pending ||
      !roles ||
      permissions.some((item) => !roles.allowed_permissions.includes(item))
    )
      return;
    setPending(true);
    setNotice("");
    onError("");
    try {
      const updated = await api<Role>(
        `/projects/${encodeURIComponent(projectId)}/roles${editing ? `/${encodeURIComponent(editing)}` : ""}`,
        json(editing ? "PUT" : "POST", { name, permissions }),
      );
      if (!alive.current) return;
      setRoles({
        ...roles,
        custom: editing
          ? roles.custom.map((item) => (item.id === editing ? updated : item))
          : [...roles.custom, updated],
      });
      setName("");
      setEditing(null);
      setPermissions(
        ["read", "retrieve"].filter((item) =>
          roles.allowed_permissions.includes(item),
        ),
      );
      setNotice(
        editing
          ? "ロールを更新しました。割り当て済みの利用者に反映されます。"
          : "ロールを作成しました。利用者への割り当てはローカル管理者が行います。",
      );
    } catch (error) {
      if (alive.current) onError(errorText(error));
    } finally {
      if (alive.current) setPending(false);
    }
  }
  return (
    <div className="role-editor">
      <p className="muted">
        ロールは現在のプロジェクト内で有効です。管理操作の権限は委任できません。
      </p>
      {notice && <p role="status">{notice}</p>}
      <label>
        テンプレート
        <select
          aria-label="ロールテンプレート"
          disabled={pending || !roles || !!editing}
          onChange={(event) => {
            const template = roles?.templates.find(
              (role) => role.id === event.target.value,
            );
            if (template)
              setPermissions(
                template.permissions.filter((permission) =>
                  roles?.allowed_permissions.includes(permission),
                ),
              );
          }}
        >
          <option value="">テンプレートを選択</option>
          {roles?.templates.map((role) => (
            <option value={role.id} key={role.id}>
              {role.name}
            </option>
          ))}
        </select>
      </label>
      <form onSubmit={save}>
        <label>
          {editing ? "ロール名" : "新しいロール名"}
          <input
            disabled={pending || !roles}
            value={name}
            maxLength={64}
            required
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <p className="field-label">許可する操作</p>
        <div className="permission-chips">
          {[
            ...new Set([...(roles?.allowed_permissions ?? []), ...permissions]),
          ].map((permission) => (
            <button
              type="button"
              disabled={pending || !roles}
              key={permission}
              aria-pressed={permissions.includes(permission)}
              onClick={() =>
                setPermissions((items) =>
                  items.includes(permission)
                    ? items.filter((item) => item !== permission)
                    : [...items, permission],
                )
              }
            >
              {permissionLabels[permission] ?? permission}
            </button>
          ))}
        </div>
        <p className="permission-preview">
          現在のプロジェクトで「{name || "新しいロール"}」に、
          {permissions
            .map((permission) => permissionLabels[permission] ?? permission)
            .join("・") || "操作なし"}
          を許可します。
        </p>
        {editing && (
          <p>
            保存すると、このプロジェクトで割り当て済みの利用者の操作権限に即時反映されます。
          </p>
        )}
        {roles &&
          permissions.some(
            (item) => !roles.allowed_permissions.includes(item),
          ) && (
            <p role="alert">
              本人の許可範囲外の操作があります。該当する操作を外してから保存してください。
            </p>
          )}
        <button
          type="submit"
          disabled={
            !name.trim() ||
            pending ||
            !roles ||
            permissions.some(
              (item) => !roles.allowed_permissions.includes(item),
            )
          }
        >
          {editing ? "ロールの変更を保存" : "ロールを作成"}
        </button>
        {editing && (
          <button
            type="button"
            disabled={pending}
            onClick={() => {
              setEditing(null);
              setName("");
              setNotice("");
              onError("");
              setPermissions(
                ["read", "retrieve"].filter((item) =>
                  roles?.allowed_permissions.includes(item),
                ),
              );
            }}
          >
            編集を取り消す
          </button>
        )}
      </form>
      <h2>作成済みロール</h2>
      {roles?.custom.length ? (
        roles.custom.map((role) => (
          <div className="list-row" key={role.id}>
            <strong>{role.name}</strong>
            <span>
              {role.permissions
                .map((permission) => permissionLabels[permission] ?? permission)
                .join("・")}
            </span>
            <button
              type="button"
              disabled={pending}
              aria-label={`${role.name}を編集`}
              onClick={() => {
                setEditing(role.id);
                setName(role.name);
                setPermissions([...role.permissions]);
                setNotice("");
                onError("");
              }}
            >
              編集
            </button>
          </div>
        ))
      ) : (
        <p className="empty">追加のロールはありません。</p>
      )}
    </div>
  );
}

export function AdminUsers({ currentUserId }: { currentUserId?: string }) {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <>
      <ProvisionUser onCreated={() => setRefreshKey((key) => key + 1)} />
      <AdminList key={refreshKey} kind="users" currentUserId={currentUserId} />
    </>
  );
}

export function AdminList({
  kind,
  currentUserId,
}: {
  kind: "users" | "audit";
  currentUserId?: string;
}) {
  const [rows, setRows] = useState<Record<string, string | number | boolean>[]>(
    [],
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [disableConfirmation, setDisableConfirmation] = useState<string | null>(
    null,
  );
  const pending = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    let active = true;
    mounted.current = true;
    void api<Record<string, string | number | boolean>[]>(`/admin/${kind}`)
      .then((data) => {
        if (active) setRows(data);
      })
      .catch((error) => {
        if (active) setError(errorText(error));
      });
    return () => {
      active = false;
    };
  }, [kind]);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  async function toggle(row: Record<string, string | number | boolean>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      const updated = await api<Record<string, string | number | boolean>>(
        `/admin/users/${encodeURIComponent(String(row.id))}/enabled`,
        json("PUT", { enabled: !row.enabled }),
      );
      if (mounted.current) {
        setRows((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        );
        if (!updated.enabled) setDisableConfirmation(null);
      }
    } catch (error) {
      if (mounted.current) setError(errorText(error));
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return (
    <>
      <p className="muted">
        {kind === "users"
          ? "利用者はWeb画面から追加できます。所属・ロール・明示的な拒否はプロジェクト画面で管理します。管理者に個人会話の閲覧権限は付与されません。"
          : "操作のメタデータのみを記録します。会話・資料の本文や資格情報は表示しません。"}
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="list">
        {rows.map((row) => (
          <div className="list-row" key={String(row.id)}>
            {kind === "users" ? (
              <>
                <strong>{row.username}</strong>
                <span>
                  {row.system_admin ? "システム管理者" : "利用者"} ·{" "}
                  {row.enabled ? "有効" : "無効"}
                  {row.must_rotate ? " · 初回変更待ち" : ""}
                </span>
                {row.enabled ? (
                  <>
                    <IconButton
                      label={`${row.username}を無効にする`}
                      disabled={busy || row.id === currentUserId}
                      onClick={() => {
                        setError("");
                        setDisableConfirmation(String(row.id));
                      }}
                    >
                      <UserX size={18} />
                    </IconButton>
                    {disableConfirmation === String(row.id) && (
                      <div
                        role="group"
                        aria-label={`${row.username}のアカウント無効化確認`}
                      >
                        <p>
                          「{row.username}」（利用者ID: {row.id}
                          ）のアカウントを無効にします。
                          この利用者のすべてのログインセッションが取り消され、再有効化するまでログインできなくなります。
                        </p>
                        <button
                          type="button"
                          disabled={busy}
                          aria-label={`${row.username}を無効にする（確認）`}
                          onClick={() => void toggle(row)}
                        >
                          アカウントを無効にする
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          aria-label={`${row.username}の無効化を取り消す`}
                          onClick={() => setDisableConfirmation(null)}
                        >
                          取り消す
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <IconButton
                    label={`${row.username}を有効にする`}
                    disabled={busy || row.id === currentUserId}
                    onClick={() => void toggle(row)}
                  >
                    <UserCheck size={18} />
                  </IconButton>
                )}
              </>
            ) : (
              <>
                <span>
                  {new Date(Number(row.at) * 1000).toLocaleString("ja-JP")}
                </span>
                <code>{row.operation}</code>
                <span>{row.outcome}</span>
              </>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
