import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ArrowUp,
  ChevronDown,
  FileText,
  LogOut,
  PanelLeft,
  Plus,
  SquarePen,
  X,
} from "lucide-react";
import { api, errorText, json, statusName } from "./api";
import type {
  Citation,
  Conversation,
  Document,
  Message,
  Project,
  Roles,
  User,
} from "./api";

type Page =
  | "chat"
  | "shared"
  | "personal"
  | "history"
  | "users"
  | "roles"
  | "ingestion"
  | "audit"
  | "settings";
type Attachment = {
  key: string;
  name: string;
  status: string;
  id?: string;
  reason?: string;
};
const labels: Record<Page, string> = {
  chat: "資料を調べる",
  shared: "共有資料",
  personal: "個人資料",
  history: "調査履歴",
  users: "利用者",
  roles: "役割・管理権限",
  ingestion: "取り込み状況",
  audit: "操作記録",
  settings: "モデル・同時利用",
};
const permissionLabels: Record<string, string> = {
  read: "閲覧",
  retrieve: "チャット参照",
  upload: "資料追加",
  publish: "資料公開",
};

function IconButton({
  label,
  onClick,
  children,
  disabled = false,
  ...rest
}: {
  label: string;
  onClick?: () => void;
  children: ReactNode;
  disabled?: boolean;
  type?: "button" | "submit";
  "aria-expanded"?: boolean;
  "aria-controls"?: string;
}) {
  return (
    <button
      className="icon-button"
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      {...rest}
    >
      {children}
      <span className="tooltip" role="tooltip">
        {label}
      </span>
    </button>
  );
}

function AccessForm({
  user,
  onUser,
}: {
  user: User | null;
  onUser: (user: User) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rotate = !!user?.must_rotate;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (rotate) {
        if (newPassword !== confirmation)
          throw new Error("新しいパスワードが一致しません。");
        await api(
          "/auth/password",
          json("POST", {
            current_password: password,
            new_password: newPassword,
          }),
        );
        onUser(await api<User>("/auth/me"));
      } else
        onUser(
          await api<User>("/auth/login", json("POST", { username, password })),
        );
      setPassword("");
      setNewPassword("");
      setConfirmation("");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="access">
      <div className="access-brand">
        研究資料室 <span>Locus</span>
      </div>
      <form onSubmit={submit} className="access-form">
        <p className="eyebrow">ローカル検証環境 · 合成データ専用</p>
        <h1>{rotate ? "仮パスワードの変更" : "ログイン"}</h1>
        {rotate ? (
          <p>資料を開く前に、仮パスワードを変更してください。</p>
        ) : (
          <p>管理者が発行した利用者IDでログインしてください。</p>
        )}
        {!rotate && (
          <label>
            利用者ID
            <input
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              maxLength={64}
            />
          </label>
        )}
        <label>
          {rotate ? "仮パスワード" : "パスワード"}
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            maxLength={128}
          />
        </label>
        {rotate && (
          <>
            <label>
              新しいパスワード
              <input
                type="password"
                autoComplete="new-password"
                minLength={14}
                maxLength={128}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
            </label>
            <label>
              新しいパスワード（確認）
              <input
                type="password"
                autoComplete="new-password"
                minLength={14}
                maxLength={128}
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                required
              />
            </label>
            <p className="muted">14〜128文字で設定してください。</p>
          </>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy}>
          {busy ? "確認中…" : rotate ? "変更して続ける" : "ログイン"}
        </button>
        <p className="muted">
          初回アカウント発行・回復はローカル管理者へ連絡してください。
        </p>
      </form>
    </main>
  );
}

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    void api<User>("/auth/me")
      .then((user) => {
        if (active) setUser(user);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoading(false);
      });
    const expired = () => setUser(null);
    window.addEventListener("locus-session-expired", expired);
    return () => {
      active = false;
      window.removeEventListener("locus-session-expired", expired);
    };
  }, []);
  if (loading)
    return (
      <p className="loading" role="status">
        接続を確認しています…
      </p>
    );
  if (!user || user.must_rotate)
    return <AccessForm user={user} onUser={setUser} />;
  return <Workspace key={user.id} user={user} onLogout={() => setUser(null)} />;
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [page, setPage] = useState<Page>("chat");
  const [sidebar, setSidebar] = useState(
    () =>
      localStorage.getItem("locus-sidebar") !== "closed" &&
      window.innerWidth >= 768,
  );
  const [documents, setDocuments] = useState<Document[]>([]);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [scope, setScope] = useState("all");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<Citation[] | null>(null);
  const conversationPromise = useRef<Promise<string> | null>(null);
  const conversationRef = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const personalInput = useRef<HTMLInputElement>(null);
  const sourceClose = useRef<HTMLButtonElement>(null);
  const sourceTrigger = useRef<HTMLElement | null>(null);
  const project = projects.find((project) => project.id === projectId);
  const can = (permission: string) =>
    project?.permissions.includes(permission) ?? false;

  useEffect(() => {
    let active = true;
    void api<Project[]>("/projects")
      .then((items) => {
        if (active) {
          setProjects(items);
          setProjectId(items[0]?.id ?? "");
        }
      })
      .catch((error) => {
        if (active) setError(errorText(error));
      });
    return () => {
      active = false;
    };
  }, []);

  const reload = useCallback(async () => {
    if (!projectId) return;
    const [docs, conversations] = await Promise.all([
      api<Document[]>(`/documents?project_id=${encodeURIComponent(projectId)}`),
      project?.permissions.includes("retrieve")
        ? api<Conversation[]>(
            `/conversations?project_id=${encodeURIComponent(projectId)}`,
          )
        : Promise.resolve([]),
    ]);
    setDocuments(docs);
    setHistory(conversations);
  }, [projectId, project]);

  useEffect(() => {
    let active = true;
    if (projectId) {
      void Promise.all([
        api<Document[]>(
          `/documents?project_id=${encodeURIComponent(projectId)}`,
        ),
        project?.permissions.includes("retrieve")
          ? api<Conversation[]>(
              `/conversations?project_id=${encodeURIComponent(projectId)}`,
            )
          : Promise.resolve([]),
      ])
        .then(([docs, conversations]) => {
          if (active) {
            setDocuments(docs);
            setHistory(conversations);
          }
        })
        .catch((error) => {
          if (active) setError(errorText(error));
        });
    }
    return () => {
      active = false;
    };
  }, [projectId, project]);

  useEffect(() => {
    if (
      !attachments.some((item) => ["queued", "scanning"].includes(item.status))
    )
      return;
    const timer = setInterval(() => {
      void Promise.all(
        attachments
          .filter(
            (item) => item.id && ["queued", "scanning"].includes(item.status),
          )
          .map(async (item) => {
            const doc = await api<Document>(
              `/documents/${item.id}?conversation_id=${conversationRef.current ?? ""}`,
            );
            setAttachments((items) =>
              items.map((existing) =>
                existing.key === item.key
                  ? { ...existing, status: doc.status, reason: doc.reason }
                  : existing,
              ),
            );
          }),
      ).catch((error) => setError(errorText(error)));
    }, 1000);
    return () => clearInterval(timer);
  }, [attachments]);

  useEffect(() => {
    if (source) sourceClose.current?.focus();
  }, [source]);

  function toggleSidebar() {
    setSidebar((open) => {
      localStorage.setItem("locus-sidebar", open ? "closed" : "open");
      return !open;
    });
  }
  function navigate(next: Page) {
    setPage(next);
    setError("");
    setNotice("");
    if (window.innerWidth < 768) setSidebar(false);
  }
  function newChat() {
    conversationRef.current = null;
    conversationPromise.current = null;
    setConversationId(null);
    setMessages([]);
    setDraft("");
    setAttachments([]);
    setError("");
    navigate("chat");
  }
  async function ensureConversation(): Promise<string> {
    if (conversationRef.current) return conversationRef.current;
    if (!conversationPromise.current)
      conversationPromise.current = api<Conversation>(
        "/conversations",
        json("POST", { project_id: projectId }),
      )
        .then((conv) => {
          conversationRef.current = conv.id;
          setConversationId(conv.id);
          return conv.id;
        })
        .finally(() => {
          conversationPromise.current = null;
        });
    return conversationPromise.current;
  }
  async function addFiles(
    files: File[],
    kind: "attachment" | "personal" = "attachment",
  ) {
    if (!files.length || busy) return;
    setError("");
    setBusy(true);
    try {
      if (files.length + (kind === "attachment" ? attachments.length : 0) > 10)
        throw new Error("一度に添付できる資料は10件までです。");
      const conversation =
        kind === "attachment" ? await ensureConversation() : null;
      for (const file of files) {
        const key = crypto.randomUUID();
        if (kind === "attachment")
          setAttachments((items) => [
            ...items,
            { key, name: file.name, status: "uploading" },
          ]);
        try {
          if (file.size > 262144 || !/\.(txt|md|csv)$/i.test(file.name))
            throw new Error(
              "対応形式はUTF-8のtxt・md・csv、1件256 KiBまでです。",
            );
          const content = new TextDecoder("utf-8", { fatal: true }).decode(
            await file.arrayBuffer(),
          );
          const doc = await api<Document>(
            "/documents",
            json("POST", {
              project_id: projectId,
              name: file.name,
              content,
              kind,
              conversation_id: conversation,
            }),
          );
          if (kind === "attachment")
            setAttachments((items) =>
              items.map((item) =>
                item.key === key
                  ? { ...item, id: doc.id, status: doc.status }
                  : item,
              ),
            );
        } catch (error) {
          if (kind === "attachment")
            setAttachments((items) =>
              items.map((item) =>
                item.key === key
                  ? { ...item, status: "failed", reason: errorText(error) }
                  : item,
              ),
            );
          else setError(errorText(error));
        }
      }
      await reload();
      if (kind === "personal")
        setNotice("登録を受け付けました。取り込み状況を確認してください。");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  async function removeAttachment(item: Attachment) {
    try {
      if (item.id) await api(`/documents/${item.id}`, json("DELETE"));
      setAttachments((items) =>
        items.filter((existing) => existing.key !== item.key),
      );
    } catch (error) {
      setError(errorText(error));
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy || !can("retrieve")) return;
    setError("");
    if (attachments.some((item) => item.status !== "ready")) {
      setError(
        "参照できない添付があります。状態を確認し、取り外してから送信してください。",
      );
      return;
    }
    setBusy(true);
    try {
      const id = await ensureConversation();
      const message = await api<Message>(
        `/conversations/${id}/messages`,
        json("POST", {
          text: draft,
          scope,
          attachment_ids: attachments.map((item) => item.id),
        }),
      );
      setMessages((items) => [...items, message]);
      setDraft("");
      await reload();
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  async function openConversation(id: string) {
    setBusy(true);
    try {
      const conv = await api<Conversation>(`/conversations/${id}`);
      conversationRef.current = id;
      setConversationId(id);
      setMessages(conv.messages);
      setAttachments(
        conv.attachments.map((doc) => ({
          key: doc.id,
          id: doc.id,
          name: doc.name,
          status: doc.status,
          reason: doc.reason,
        })),
      );
      setDraft("");
      navigate("chat");
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  async function openSource(document: string) {
    sourceTrigger.current = documentElement();
    try {
      setSource(
        await api<Citation[]>(
          `/documents/${document}/chunks${conversationId ? `?conversation_id=${conversationId}` : ""}`,
        ),
      );
    } catch (error) {
      setError(errorText(error));
    }
  }
  function closeSource() {
    setSource(null);
    sourceTrigger.current?.focus();
  }
  function navButton(key: Page) {
    return (
      <button
        key={key}
        disabled={busy}
        className={page === key ? "nav-item selected" : "nav-item"}
        aria-current={page === key ? "page" : undefined}
        onClick={() => navigate(key)}
      >
        {labels[key]}
      </button>
    );
  }

  return (
    <div className={`workspace ${sidebar ? "sidebar-open" : "sidebar-closed"}`}>
      <header className="topbar">
        <IconButton
          label={sidebar ? "サイドバーを閉じる" : "サイドバーを開く"}
          onClick={toggleSidebar}
          aria-expanded={sidebar}
          aria-controls="workspace-sidebar"
        >
          <PanelLeft size={19} />
        </IconButton>
        <strong>研究資料室</strong>
        <select
          className="project-select"
          aria-label="プロジェクト"
          value={projectId}
          disabled={busy}
          onChange={(e) => {
            newChat();
            setProjectId(e.target.value);
            setDocuments([]);
            setHistory([]);
            setPage("chat");
          }}
        >
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <span className="environment">合成データ検証用</span>
        <span className="user-name">{user.username}</span>
        <IconButton
          label="ログアウト"
          onClick={() => {
            void api("/auth/logout", json("POST"))
              .then(onLogout)
              .catch((error) => setError(errorText(error)));
          }}
        >
          <LogOut size={17} />
        </IconButton>
      </header>
      <aside
        id="workspace-sidebar"
        className="sidebar"
        inert={!sidebar}
        aria-hidden={!sidebar}
      >
        <nav aria-label="メインメニュー">
          <p className="nav-heading">資料・調査</p>
          {(["chat", "shared", "personal", "history"] as Page[]).map(navButton)}
          {(user.system_admin || can("manage_roles")) && (
            <>
              <div className="nav-divider" />
              <p className="nav-heading">管理</p>
              <details open>
                <summary>
                  利用者・アクセス <ChevronDown size={12} />
                </summary>
                {user.system_admin && navButton("users")}
                {can("manage_roles") && navButton("roles")}
              </details>
            </>
          )}
          <details open>
            <summary>
              データ・処理 <ChevronDown size={12} />
            </summary>
            {navButton("ingestion")}
            {navButton("settings")}
          </details>
          {user.system_admin && (
            <details>
              <summary>
                運用・記録 <ChevronDown size={12} />
              </summary>
              {navButton("audit")}
            </details>
          )}
        </nav>
        <p className="sidebar-foot">Locus · ローカル開発版</p>
      </aside>
      {sidebar && (
        <button
          className="sidebar-backdrop"
          aria-label="メニューを閉じる"
          onClick={() => setSidebar(false)}
        />
      )}
      <main className="main">
        <div className="page-heading">
          <h1>{labels[page]}</h1>
          {page === "chat" && (
            <IconButton label="新規会話" disabled={busy} onClick={newChat}>
              <SquarePen size={20} />
            </IconButton>
          )}
        </div>
        {error && (
          <div className="notice error" role="alert">
            {error}
            <IconButton label="エラーを閉じる" onClick={() => setError("")}>
              <X size={15} />
            </IconButton>
          </div>
        )}
        {notice && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
        {!projectId && (
          <p className="empty">
            利用可能なプロジェクトがありません。ローカル管理者に所属設定を依頼してください。
          </p>
        )}
        {projectId && page === "chat" && (
          <div className="chat">
            <label className="scope-label">
              参照範囲
              <select
                value={scope}
                disabled={busy}
                onChange={(e) => setScope(e.target.value)}
              >
                <option value="all">共有資料＋個人資料</option>
                <option value="shared">共有資料</option>
                <option value="personal">個人資料</option>
              </select>
            </label>
            <div className="messages" aria-live="polite">
              {messages.length === 0 ? (
                <div className="chat-empty">
                  <FileText size={25} strokeWidth={1.3} />
                  <p>参照できる資料を調べる</p>
                  <span>資料の本文と出典を確認できます。</span>
                </div>
              ) : (
                messages.map((message) => (
                  <article className="exchange" key={message.id}>
                    <p className="user-message">{message.text}</p>
                    <div className="answer">
                      <h2>
                        {message.citations.length
                          ? "資料に見つかった記述"
                          : "参照できる記述が見つかりませんでした"}
                      </h2>
                      {message.citations.map((citation) => (
                        <div key={citation.id} className="citation-excerpt">
                          <blockquote>{citation.text}</blockquote>
                          <button
                            className="text-link"
                            onClick={() => {
                              void openSource(citation.document_id);
                            }}
                          >
                            {citation.name} · p.{citation.page} · chunk{" "}
                            {citation.ordinal}
                          </button>
                        </div>
                      ))}
                      <p className="footnote">
                        {message.citations.length
                          ? "検索で抽出した原文です。AI生成の回答ではありません。判断には元資料を確認してください。"
                          : "参照範囲・資料の処理状態・質問の語句を確認してください。"}
                      </p>
                    </div>
                  </article>
                ))
              )}
            </div>
            <form
              className="composer"
              onSubmit={send}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                void addFiles(Array.from(event.dataTransfer.files));
              }}
            >
              {attachments.length > 0 && (
                <ul className="attachments">
                  {attachments.map((item) => (
                    <li key={item.key}>
                      <FileText size={15} />
                      <span className="attachment-name" title={item.name}>
                        {item.name}
                      </span>
                      <span
                        className={
                          item.status === "failed" ||
                          item.status === "quarantined"
                            ? "error"
                            : "muted"
                        }
                        title={item.reason}
                      >
                        {statusName[item.status] ?? item.status}
                      </span>
                      <IconButton
                        label={`${item.name}を取り外す`}
                        disabled={busy}
                        onClick={() => {
                          void removeAttachment(item);
                        }}
                      >
                        <X size={14} />
                      </IconButton>
                      {item.reason && (
                        <span className="attachment-reason">{item.reason}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <textarea
                placeholder="メッセージを入力"
                aria-label="メッセージ"
                value={draft}
                maxLength={4000}
                disabled={busy || !can("retrieve")}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing &&
                    event.keyCode !== 229
                  ) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <div className="composer-actions">
                <IconButton
                  label="ファイルを添付"
                  disabled={busy || !can("upload")}
                  onClick={() => fileInput.current?.click()}
                >
                  <Plus size={20} />
                </IconButton>
                <input
                  ref={fileInput}
                  type="file"
                  hidden
                  multiple
                  accept=".txt,.md,.csv"
                  aria-label="添付ファイルを選択"
                  onChange={(event) => {
                    void addFiles(Array.from(event.target.files ?? []));
                    event.target.value = "";
                  }}
                />
                <span className="send-state" role="status">
                  {busy ? "処理中…" : ""}
                </span>
                <IconButton
                  label="送信"
                  type="submit"
                  disabled={busy || !draft.trim() || !can("retrieve")}
                >
                  <ArrowUp size={20} />
                </IconButton>
              </div>
            </form>
            <p className="composer-note">
              検証用の検索です。外部AIへ送信しません。
            </p>
          </div>
        )}
        {projectId && ["shared", "personal", "ingestion"].includes(page) && (
          <>
            <div className="section-toolbar">
              <p className="muted">
                {page === "ingestion"
                  ? "検査機能が未接続の資料は隔離され、検索には使われません。"
                  : page === "personal"
                    ? "本人のみが参照できる資料です。会話添付はここに自動登録されません。"
                    : "このプロジェクトで閲覧を許可された資料です。"}
              </p>
              <button
                disabled={busy}
                onClick={() => {
                  void reload().catch((error) => setError(errorText(error)));
                }}
              >
                更新
              </button>
              {page === "personal" && can("upload") && (
                <button
                  disabled={busy}
                  onClick={() => personalInput.current?.click()}
                >
                  資料を追加
                </button>
              )}
              <input
                ref={personalInput}
                hidden
                type="file"
                multiple
                accept=".txt,.md,.csv"
                onChange={(e) => {
                  void addFiles(Array.from(e.target.files ?? []), "personal");
                  e.target.value = "";
                }}
              />
            </div>
            <p className="footnote">
              対応形式：UTF-8のtxt・md・csv、1件256
              KiBまで。実研究資料は登録しないでください。
            </p>
            <DocumentList
              documents={documents.filter(
                (doc) => page === "ingestion" || doc.kind === page,
              )}
              canPublish={can("publish")}
              onSource={openSource}
              onChanged={reload}
              onError={setError}
            />
          </>
        )}
        {projectId && page === "history" && (
          <div className="list">
            {history.length ? (
              history.map((conv) => (
                <div className="list-row" key={conv.id}>
                  <button
                    className="text-link"
                    disabled={busy}
                    onClick={() => {
                      void openConversation(conv.id);
                    }}
                  >
                    調査 ·{" "}
                    {new Date(conv.created * 1000).toLocaleString("ja-JP")}
                  </button>
                  <button
                    onClick={() => {
                      void api(`/conversations/${conv.id}`, json("DELETE"))
                        .then(() => {
                          if (conversationId === conv.id) newChat();
                          return reload();
                        })
                        .catch((error) => setError(errorText(error)));
                    }}
                  >
                    削除
                  </button>
                </div>
              ))
            ) : (
              <p className="empty">本人の調査履歴はまだありません。</p>
            )}
          </div>
        )}
        {projectId && page === "roles" && (
          <RoleEditor projectId={projectId} onError={setError} />
        )}
        {page === "users" && user.system_admin && <AdminList kind="users" />}
        {page === "audit" && user.system_admin && <AdminList kind="audit" />}
        {page === "settings" && (
          <div className="settings">
            <h2>処理先</h2>
            <p>ローカルの原文検索のみ利用できます。モデルは未選定です。</p>
            <h2>外部AI・保存先の接続</h2>
            <p>無効。接続先・契約・送信方針の承認後に実装します。</p>
            <h2>同時利用</h2>
            <p>
              取り込みは1件ずつ処理し、全体32件・一人4件まで受付します。安全のための開発上限であり、性能保証ではありません。
            </p>
            <h2>本番運用</h2>
            <p>LAN公開、回復、管理委任、保存期間は承認待ちです。</p>
          </div>
        )}
      </main>
      {source && (
        <div
          className="modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeSource();
          }}
        >
          <section
            className="source-modal"
            role="dialog"
            aria-modal="true"
            aria-label="出典の原文"
            onKeyDown={(event) => {
              if (event.key === "Escape") closeSource();
              if (event.key === "Tab") {
                event.preventDefault();
                sourceClose.current?.focus();
              }
            }}
          >
            <div className="section-toolbar">
              <h2>出典の原文</h2>
              <button ref={sourceClose} onClick={closeSource}>
                閉じる
              </button>
            </div>
            {source.map((chunk) => (
              <div key={chunk.id}>
                <p className="muted">
                  p.{chunk.page} · chunk {chunk.ordinal}
                </p>
                <pre>{chunk.text}</pre>
              </div>
            ))}
          </section>
        </div>
      )}
    </div>
  );
}

function documentElement(): HTMLElement | null {
  return document.activeElement instanceof HTMLElement
    ? document.activeElement
    : null;
}

function DocumentList({
  documents,
  canPublish,
  onSource,
  onChanged,
  onError,
}: {
  documents: Document[];
  canPublish: boolean;
  onSource: (id: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onError: (error: string) => void;
}) {
  const [publication, setPublication] = useState<string | null>(null);
  const [role, setRole] = useState("researcher");
  async function act(action: () => Promise<unknown>) {
    try {
      await action();
      await onChanged();
    } catch (error) {
      onError(errorText(error));
    }
  }
  return (
    <div className="document-list">
      {!documents.length && (
        <p className="empty">表示できる資料はありません。</p>
      )}
      {documents.map((doc) => (
        <article className="document-row" key={doc.id}>
          <div className="document-main">
            <FileText size={18} />
            <div>
              <button
                className="text-link file-name"
                disabled={doc.status !== "ready"}
                onClick={() => {
                  void onSource(doc.id);
                }}
              >
                {doc.name}
              </button>
              <p className="muted">
                {statusName[doc.status] ?? doc.status}
                {doc.reason ? ` · ${doc.reason}` : ""}
              </p>
            </div>
          </div>
          <div className="document-actions">
            {doc.owned && ["queued", "scanning"].includes(doc.status) && (
              <button
                onClick={() => {
                  void act(() =>
                    api(`/documents/${doc.id}/cancel`, json("POST")),
                  );
                }}
              >
                取消
              </button>
            )}
            {doc.owned && canPublish && doc.kind !== "attachment" && (
              <button
                onClick={() =>
                  setPublication(publication === doc.id ? null : doc.id)
                }
              >
                公開先
              </button>
            )}
            {doc.owned && (
              <button
                onClick={() => {
                  void act(() => api(`/documents/${doc.id}`, json("DELETE")));
                }}
              >
                削除
              </button>
            )}
          </div>
          {publication === doc.id && (
            <form
              className="publication"
              onSubmit={(event) => {
                event.preventDefault();
                void act(() =>
                  api(
                    `/documents/${doc.id}/publication`,
                    json("PUT", {
                      grants: [{ role, operations: ["read", "retrieve"] }],
                    }),
                  ),
                ).then(() => setPublication(null));
              }}
            >
              <label>
                ロール
                <select
                  value={role}
                  onChange={(event) => setRole(event.target.value)}
                >
                  <option value="researcher">研究者</option>
                  <option value="viewer">閲覧者</option>
                  <option value="project_lead">プロジェクト責任者</option>
                </select>
              </label>
              <p>
                「{doc.name}」を、このプロジェクトの「{role}
                」に閲覧・チャット参照を許可します。
              </p>
              <button type="submit">公開設定を保存</button>
              <button
                type="button"
                onClick={() => {
                  void act(() =>
                    api(
                      `/documents/${doc.id}/publication`,
                      json("PUT", { grants: [] }),
                    ),
                  );
                }}
              >
                公開を停止
              </button>
            </form>
          )}
        </article>
      ))}
    </div>
  );
}

function RoleEditor({
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
  useEffect(() => {
    let active = true;
    void api<Roles>(`/projects/${projectId}/roles`)
      .then((data) => {
        if (active) setRoles(data);
      })
      .catch((error) => onError(errorText(error)));
    return () => {
      active = false;
    };
  }, [projectId, onError]);
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await api(
        `/projects/${projectId}/roles`,
        json("POST", { name, permissions }),
      );
      setRoles(await api<Roles>(`/projects/${projectId}/roles`));
      setName("");
      setNotice(
        "ロールを作成しました。利用者への割り当てはローカル管理者が行います。",
      );
    } catch (error) {
      onError(errorText(error));
    }
  }
  return (
    <div className="role-editor">
      <p className="muted">
        ロールは現在のプロジェクト内で有効です。管理権限の委任は無効です。
      </p>
      {notice && <p role="status">{notice}</p>}
      <label>
        テンプレート
        <select
          aria-label="ロールテンプレート"
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
          新しいロール名
          <input
            value={name}
            maxLength={64}
            required
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <p className="field-label">許可する操作</p>
        <div className="permission-chips">
          {roles?.allowed_permissions.map((permission) => (
            <button
              type="button"
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
        <button type="submit" disabled={!name.trim()}>
          ロールを作成
        </button>
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
          </div>
        ))
      ) : (
        <p className="empty">追加のロールはありません。</p>
      )}
    </div>
  );
}

function AdminList({ kind }: { kind: "users" | "audit" }) {
  const [rows, setRows] = useState<Record<string, string | number | boolean>[]>(
    [],
  );
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
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
  return (
    <>
      <p className="muted">
        {kind === "users"
          ? "発行・所属設定はローカルCLIから行います。管理者に個人会話の閲覧権限は付与されません。"
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
                  {row.must_rotate ? "初回変更待ち" : "有効"}
                </span>
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
