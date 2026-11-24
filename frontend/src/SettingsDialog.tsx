import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";
import { AdminList, AdminUsers, RoleEditor } from "./AdminPanels";
import { AdminLoad, AdminProjects, AdminStorage } from "./AdminSettings";
import { AdminDelegations } from "./Delegations";
import { IconButton } from "./IconButton";
import { ModelSettings } from "./ModelSettings";
import { dialogControls } from "./dialog";
import {
  parseThemePreference,
  type ThemePreference,
} from "./theme";
import type { Project, User } from "./api";

type TabId =
  | "appearance"
  | "model"
  | "users"
  | "roles"
  | "projects"
  | "delegations"
  | "storage"
  | "load"
  | "audit"
  | "experimental";

type TabDef = {
  id: TabId;
  label: string;
  icon: ReactNode;
  admin?: boolean;
};

function TabIcon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="settings-tab-icon"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const tabs: TabDef[] = [
  {
    id: "appearance",
    label: "外観",
    icon: (
      <TabIcon>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
      </TabIcon>
    ),
  },
  {
    id: "model",
    label: "モデル",
    icon: (
      <TabIcon>
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <rect x="9" y="9" width="6" height="6" />
        <path d="M9 2v2M15 2v2M9 20v2M15 20v2M20 9h2M20 15h2M2 9h2M2 15h2" />
      </TabIcon>
    ),
  },
  {
    id: "users",
    label: "利用者",
    admin: true,
    icon: (
      <TabIcon>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </TabIcon>
    ),
  },
  {
    id: "roles",
    label: "役割",
    admin: true,
    icon: (
      <TabIcon>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </TabIcon>
    ),
  },
  {
    id: "projects",
    label: "プロジェクト",
    admin: true,
    icon: (
      <TabIcon>
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
      </TabIcon>
    ),
  },
  {
    id: "delegations",
    label: "委任",
    admin: true,
    icon: (
      <TabIcon>
        <circle cx="18" cy="5" r="3" />
        <circle cx="6" cy="12" r="3" />
        <circle cx="18" cy="19" r="3" />
        <path d="M8.59 13.51l6.83 3.98M15.41 6.51L8.59 10.49" />
      </TabIcon>
    ),
  },
  {
    id: "storage",
    label: "保存先",
    admin: true,
    icon: (
      <TabIcon>
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
        <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
      </TabIcon>
    ),
  },
  {
    id: "load",
    label: "実行状況",
    admin: true,
    icon: (
      <TabIcon>
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
      </TabIcon>
    ),
  },
  {
    id: "audit",
    label: "操作記録",
    admin: true,
    icon: (
      <TabIcon>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
      </TabIcon>
    ),
  },
  {
    id: "experimental",
    label: "実験的",
    icon: (
      <TabIcon>
        <path d="M9 3h6M10 3v6.4a2 2 0 0 1-.4 1.2L4.5 17.6A2 2 0 0 0 6.1 21h11.8a2 2 0 0 0 1.6-3.4l-5.1-7A2 2 0 0 1 14 9.4V3" />
      </TabIcon>
    ),
  },
];

export function SettingsDialog({
  open,
  onClose,
  user,
  project,
  can,
  themePreference,
  onThemePreferenceChange,
}: {
  open: boolean;
  onClose: () => void;
  user: User;
  project: Project | undefined;
  can: (permission: string) => boolean;
  themePreference: ThemePreference;
  onThemePreferenceChange: (preference: ThemePreference) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<TabId>("appearance");
  const [roleError, setRoleError] = useState("");

  const visibleTabs = tabs.filter((item) => {
    if (item.id === "users" || item.id === "projects" || item.id === "storage" || item.id === "load" || item.id === "audit")
      return user.system_admin;
    if (item.id === "roles") return can("manage_roles");
    if (item.id === "delegations") return !!project?.id;
    return true;
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      const close = dialog.querySelector<HTMLElement>(
        'form[method="dialog"] button',
      );
      close?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  const activeTab = visibleTabs.some((item) => item.id === tab)
    ? tab
    : (visibleTabs[0]?.id ?? "appearance");

  return (
    <dialog
      ref={dialogRef}
      className="settings-dialog"
      aria-label="設定"
      closedby="any"
      onClose={onClose}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const rect = event.currentTarget.getBoundingClientRect();
        if (
          event.clientX < rect.left ||
          event.clientX >= rect.right ||
          event.clientY < rect.top ||
          event.clientY >= rect.bottom
        ) {
          event.currentTarget.close();
        }
      }}
    >
      <span
        className="focus-guard"
        tabIndex={0}
        onFocus={() => dialogControls(dialogRef.current).at(-1)?.focus()}
      />
      <div className="settings-dialog-shell">
        <nav className="settings-tabs" aria-label="設定の項目">
          {visibleTabs.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeTab === item.id ? "settings-tab selected" : "settings-tab"}
              aria-current={activeTab === item.id ? "page" : undefined}
              onClick={() => setTab(item.id)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="settings-panel">
          <div className="settings-panel-header">
            <h2>{visibleTabs.find((item) => item.id === activeTab)?.label ?? "設定"}</h2>
            <form method="dialog">
              <IconButton label="設定を閉じる" type="submit">
                <X size={18} />
              </IconButton>
            </form>
          </div>
          <div className="settings-panel-body">
            {activeTab === "appearance" && (
              <SettingsRows>
                <SettingsRow name="配色テーマ" description="画面の明るさを選びます。「システムに従う」は端末の設定に合わせ、このブラウザに保存されます。">
                  <select
                    aria-label="配色テーマ"
                    value={themePreference}
                    onChange={(event) =>
                      onThemePreferenceChange(
                        parseThemePreference(event.target.value),
                      )
                    }
                  >
                    <option value="light">ライト</option>
                    <option value="system">システムに従う</option>
                    <option value="dark">ダーク</option>
                  </select>
                </SettingsRow>
              </SettingsRows>
            )}
            {activeTab === "model" && (
              <div className="settings-tab-content">
                <SettingsRows>
                  <SettingsRow name="処理先" description="既定はローカルの原文検索です。管理者がOllamaモデルを明示的に有効化した場合は、参照資料に基づく回答を生成します。" />
                  <SettingsRow name="同時利用" description="取り込みは1件ずつ処理し、全体32件・一人4件まで受付します。安全のための開発上限であり、性能保証ではありません。" />
                </SettingsRows>
                {user.system_admin && <ModelSettings />}
              </div>
            )}
            {activeTab === "users" && user.system_admin && (
              <div className="settings-tab-content">
                <AdminUsers currentUserId={user.id} />
              </div>
            )}
            {activeTab === "roles" && can("manage_roles") && project?.id && (
              <div className="settings-tab-content">
                {roleError && <p role="alert">{roleError}</p>}
                <RoleEditor key={project.id} projectId={project.id} onError={setRoleError} />
              </div>
            )}
            {activeTab === "projects" && user.system_admin && (
              <div className="settings-tab-content"><AdminProjects /></div>
            )}
            {activeTab === "delegations" && project?.id && (
              <div className="settings-tab-content"><AdminDelegations /></div>
            )}
            {activeTab === "storage" && user.system_admin && (
              <div className="settings-tab-content"><AdminStorage /></div>
            )}
            {activeTab === "load" && user.system_admin && (
              <div className="settings-tab-content"><AdminLoad /></div>
            )}
            {activeTab === "audit" && user.system_admin && (
              <div className="settings-tab-content"><AdminList key="audit" kind="audit" /></div>
            )}
            {activeTab === "experimental" && (
              <SettingsRows>
                <SettingsRow name="LAN公開" description="社内ネットワークへの公開は準備中です。現在はローカル開発環境でのみ利用できます。" status="準備中" />
                <SettingsRow name="回復" description="障害時の復旧手順と自動回復は設計中です。" status="設計中" />
                <SettingsRow name="組織単位の委任拡張" description="プロジェクト単位の委任は利用できます。組織単位への拡張は承認待ちです。" status="承認待ち" />
                <SettingsRow name="保存期間" description="資料・記録の保存期間ポリシーは承認待ちです。" status="承認待ち" />
              </SettingsRows>
            )}
          </div>
        </div>
      </div>
      <span
        className="focus-guard"
        tabIndex={0}
        onFocus={() => dialogControls(dialogRef.current)[0]?.focus()}
      />
    </dialog>
  );
}

function SettingsRows({ children }: { children: ReactNode }) {
  return <div className="settings-rows">{children}</div>;
}

function SettingsRow({
  name,
  description,
  status,
  children,
}: {
  name: string;
  description: string;
  status?: string;
  children?: ReactNode;
}) {
  return (
    <div className="settings-row">
      <div className="settings-row-text">
        <p className="settings-row-name">{name}</p>
        <p className="settings-row-description">{description}</p>
        {status && <p className="settings-row-status">{status}</p>}
      </div>
      {children && <div className="settings-row-control">{children}</div>}
    </div>
  );
}
