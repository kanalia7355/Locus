import { Settings, SquarePen, Trash2 } from "lucide-react";
import type { Conversation, User } from "./api";

type NavPage = "shared" | "personal" | "ingestion";

const navItems: { key: NavPage; label: string }[] = [
  { key: "shared", label: "共有資料" },
  { key: "personal", label: "個人資料" },
  { key: "ingestion", label: "取り込み状況" },
];

export function Sidebar({
  open,
  onClose,
  onNewChat,
  conversations,
  activeConversationId,
  onOpenConversation,
  onDeleteConversation,
  page,
  onNavigate,
  user,
  onOpenSettings,
  busy,
}: {
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
  conversations: Conversation[];
  activeConversationId: string | null;
  onOpenConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  page: string;
  onNavigate: (page: NavPage) => void;
  user: User;
  onOpenSettings: () => void;
  busy: boolean;
}) {
  return (
    <aside
      id="workspace-sidebar"
      className="sidebar"
      inert={!open}
      aria-hidden={!open}
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open || window.innerWidth >= 768) return;
        event.stopPropagation();
        onClose();
      }}
    >
      <div className="sidebar-top">
        <div className="sidebar-new-chat">
          <button
            type="button"
            className="new-chat-button"
            onClick={onNewChat}
            disabled={busy}
          >
            <SquarePen size={18} strokeWidth={1.8} aria-hidden="true" />
            <span>新しいチャット</span>
          </button>
        </div>

        <div className="sidebar-section">
          <p className="nav-heading">会話</p>
          {conversations.length ? (
            <ul className="conversation-list">
              {conversations.map((conv) => {
                const active = activeConversationId === conv.id && page === "chat";
                return (
                  <li key={conv.id} className="conversation-item">
                    <button
                      type="button"
                      className={active ? "conversation-link selected" : "conversation-link"}
                      aria-current={active ? "page" : undefined}
                      onClick={() => onOpenConversation(conv.id)}
                      disabled={busy}
                    >
                      <span className="conversation-preview">
                        {conv.preview?.trim() || "調査"}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="conversation-delete"
                      aria-label={`${conv.preview?.trim() || "調査"}を削除`}
                      onClick={() => onDeleteConversation(conv.id)}
                      disabled={busy}
                    >
                      <Trash2 size={14} strokeWidth={1.8} aria-hidden="true" />
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="sidebar-empty">会話はまだありません。</p>
          )}
        </div>

        <div className="sidebar-section">
          <p className="nav-heading">資料</p>
          <nav aria-label="資料メニュー">
            {navItems.map((item) => (
              <button
                key={item.key}
                type="button"
                disabled={busy}
                className={page === item.key ? "nav-item selected" : "nav-item"}
                aria-current={page === item.key ? "page" : undefined}
                onClick={() => onNavigate(item.key)}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </div>

      <div className="sidebar-account">
        <div className="sidebar-account-user">
          <span className="sidebar-avatar" aria-hidden="true">
            {user.username.slice(0, 1).toUpperCase()}
          </span>
          <span className="sidebar-account-name">{user.username}</span>
        </div>
        <button
          type="button"
          className="sidebar-gear"
          aria-label="設定"
          title="設定"
          onClick={onOpenSettings}
        >
          <Settings size={18} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
    </aside>
  );
}
