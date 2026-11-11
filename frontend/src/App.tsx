import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  ChevronDown,
  FileText,
  LogOut,
  PanelLeft,
  SquarePen,
  UserCheck,
  UserX,
  X,
} from "lucide-react";
import { api, errorText, json, statusName } from "./api";
import { RelatedDocuments } from "./RelatedDocuments";
import { ChatView } from "./ChatView";
import {
  createAttachmentKey,
  type ChatAttachment,
  type PendingChatJob,
  type ChatJobNotice,
} from "./chatProjection";
import { IngestionProgress } from "./IngestionProgress";
import { AdminLoad, AdminProjects, AdminStorage } from "./AdminSettings";
import { AdminDelegations } from "./Delegations";
import { ModelSettings } from "./ModelSettings";
import { ProvisionUser } from "./ProvisionUser";
import type {
  ChatJob,
  ChatJobAccepted,
  Conversation,
  Document,
  Message,
  Project,
  Role,
  Roles,
  SourceChunk,
  User,
} from "./api";

type Page =
  | "chat"
  | "shared"
  | "personal"
  | "history"
  | "users"
  | "roles"
  | "projects"
  | "delegations"
  | "storage"
  | "load"
  | "ingestion"
  | "audit"
  | "settings";
const labels: Record<Page, string> = {
  chat: "資料を調べる",
  shared: "共有資料",
  personal: "個人資料",
  history: "調査履歴",
  users: "利用者",
  roles: "役割・管理権限",
  projects: "プロジェクト",
  delegations: "管理委任",
  storage: "保存先の接続",
  load: "負荷・実行状況",
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
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [ingestionRefresh, setIngestionRefresh] = useState<
    "waiting" | "updating" | "stopped"
  >("waiting");
  const [busy, setBusy] = useState(false);
  const [pendingJob, setPendingJob] = useState<PendingChatJob | null>(null);
  const [terminalJob, setTerminalJob] = useState<ChatJobNotice | null>(null);
  const [source, setSource] = useState<{
    document: Document;
    chunks: SourceChunk[];
    selectedChunk: string | null;
  } | null>(null);
  const [sourceError, setSourceError] = useState("");
  const conversationPromise = useRef<Promise<string> | null>(null);
  const conversationRef = useRef<string | null>(null);
  const personalInput = useRef<HTMLInputElement>(null);
  const sourceClose = useRef<HTMLButtonElement>(null);
  const sourceTarget = useRef<HTMLDivElement>(null);
  const sourceTrigger = useRef<HTMLElement | null>(null);
  const sourceRequest = useRef(0);
  const activeProject = useRef("");
  const libraryRequest = useRef(0);
  const project = projects.find((project) => project.id === projectId);
  const can = (permission: string) =>
    project?.permissions.includes(permission) ?? false;

  useEffect(() => {
    let active = true;
    void api<Project[]>("/projects")
      .then((items) => {
        if (active) {
          setProjects(items);
          activeProject.current = items[0]?.id ?? "";
          setProjectId(items[0]?.id ?? "");
        }
      })
      .catch((error) => {
        if (active) setError(errorText(error));
      });
    return () => {
      active = false;
      activeProject.current = "";
    };
  }, []);

  const reload = useCallback(async () => {
    if (!projectId || activeProject.current !== projectId) return;
    const request = ++libraryRequest.current;
    try {
      const [docs, conversations] = await Promise.all([
        api<Document[]>(
          `/documents?project_id=${encodeURIComponent(projectId)}`,
        ),
        project?.permissions.includes("retrieve")
          ? api<Conversation[]>(
              `/conversations?project_id=${encodeURIComponent(projectId)}`,
            )
          : Promise.resolve([]),
      ]);
      if (
        request === libraryRequest.current &&
        activeProject.current === projectId
      ) {
        setDocuments(docs);
        setIngestionRefresh("waiting");
        setHistory(conversations);
      }
    } catch (error) {
      if (
        request === libraryRequest.current &&
        activeProject.current === projectId
      )
        throw error;
    }
  }, [projectId, project]);

  const scopedError = useCallback(
    (message: string) => {
      if (activeProject.current === projectId) setError(message);
    },
    [projectId],
  );

  useEffect(() => {
    let active = true;
    void reload().catch((error) => {
      if (active) setError(errorText(error));
    });
    return () => {
      active = false;
    };
  }, [reload]);

  useEffect(() => {
    if (
      page !== "ingestion" ||
      !projectId ||
      !documents.some((doc) => ["queued", "scanning"].includes(doc.status))
    )
      return;
    const controller = new AbortController();
    let expiry: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(() => {
      const request = ++libraryRequest.current;
      setIngestionRefresh("updating");
      expiry = setTimeout(() => {
        controller.abort();
        if (
          request === libraryRequest.current &&
          activeProject.current === projectId
        ) {
          setIngestionRefresh("stopped");
          setError(
            "状態確認が10秒で期限切れになりました。「更新」で確認してください。",
          );
        }
      }, 10000);
      void api<Document[]>(
        `/documents?project_id=${encodeURIComponent(projectId)}`,
        {
          signal: controller.signal,
        },
      )
        .then((docs) => {
          if (
            !controller.signal.aborted &&
            request === libraryRequest.current &&
            activeProject.current === projectId
          ) {
            setDocuments(docs);
            setIngestionRefresh("waiting");
          }
        })
        .catch((error) => {
          if (
            !controller.signal.aborted &&
            request === libraryRequest.current &&
            activeProject.current === projectId
          ) {
            setIngestionRefresh("stopped");
            setError(
              `状態の自動更新を停止しました。「更新」で確認してください。${errorText(error)}`,
            );
          }
        })
        .finally(() => clearTimeout(expiry));
    }, 2000);
    return () => {
      clearTimeout(timer);
      clearTimeout(expiry);
      controller.abort();
    };
  }, [page, projectId, documents]);

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

  const pendingJobId = pendingJob?.id;
  const pendingConversation = pendingJob?.conversation;
  const pendingText = pendingJob?.text;
  const pendingJobIdRef = useRef<string | null>(null);
  pendingJobIdRef.current = pendingJobId ?? null;
  useEffect(() => {
    if (!pendingJobId || !pendingConversation || !pendingText) return;
    const job = {
      id: pendingJobId,
      conversation: pendingConversation,
      text: pendingText,
    };
    const controller = new AbortController();
    const timer = setInterval(() => {
      void api<ChatJob>(`/chat-jobs/${job.id}`, { signal: controller.signal })
        .then((status) => {
          if (controller.signal.aborted || pendingJobIdRef.current !== job.id)
            return;
          if (status.status === "running") {
            setPendingJob((current) =>
              current && current.id === job.id
                ? {
                    ...current,
                    status: "running",
                    cancelRequested:
                      current.cancelRequested || status.cancel_requested,
                  }
                : current,
            );
          } else if (status.status === "done") {
            setPendingJob(null);
            setTerminalJob({
              conversation: job.conversation,
              text: job.text,
              status: "done",
            });
            if (status.conversation_id === conversationRef.current) {
              void api<Conversation>(`/conversations/${status.conversation_id}`)
                .then((conv) => {
                  if (
                    !controller.signal.aborted &&
                    conversationRef.current === status.conversation_id
                  ) {
                    setMessages(conv.messages);
                    setTerminalJob(null);
                  }
                })
                .catch((error) => setError(errorText(error)));
            } else
              setNotice(
                "待機していた質問の回答が完成しました。調査履歴から開いてください。",
              );
          } else if (status.status === "failed") {
            setPendingJob(null);
            setTerminalJob({
              conversation: job.conversation,
              text: job.text,
              status: "failed",
              detail: status.detail,
            });
          } else if (status.status === "cancelled") {
            setPendingJob(null);
            setTerminalJob({
              conversation: job.conversation,
              text: job.text,
              status: "cancelled",
            });
            setNotice("質問を取り消しました。");
          }
        })
        .catch((error) => {
          if (controller.signal.aborted || pendingJobIdRef.current !== job.id)
            return;
          clearInterval(timer);
          setPendingJob(null);
          setError(
            `質問の状態確認を停止しました。回答は調査履歴から確認できます。${errorText(error)}`,
          );
        });
    }, 2000);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [pendingJobId, pendingConversation, pendingText]);

  useEffect(() => {
    if (source?.selectedChunk && sourceTarget.current) {
      sourceTarget.current.focus();
      sourceTarget.current.scrollIntoView({ block: "nearest" });
    } else if (source) sourceClose.current?.focus();
  }, [source]);

  function toggleSidebar() {
    setSidebar((open) => {
      localStorage.setItem("locus-sidebar", open ? "closed" : "open");
      return !open;
    });
  }
  function navigate(next: Page) {
    sourceRequest.current++;
    setSource(null);
    setPage(next);
    setError("");
    setNotice("");
    if (window.innerWidth < 768) setSidebar(false);
  }
  function newChat() {
    setTerminalJob(null);
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
    setNotice("");
    setBusy(true);
    let accepted = 0;
    const failures: string[] = [];
    try {
      if (files.length + (kind === "attachment" ? attachments.length : 0) > 10)
        throw new Error("一度に添付できる資料は10件までです。");
      const conversation =
        kind === "attachment" ? await ensureConversation() : null;
      for (const file of files) {
        const key = createAttachmentKey();
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
          accepted++;
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
          else failures.push(`${file.name}：${errorText(error)}`);
        }
      }
      if (kind === "personal") {
        if (accepted > 0)
          setNotice(
            `${accepted}件の登録を受け付けました。取り込み状況を確認してください。`,
          );
        if (failures.length)
          setError(
            `${failures.length}件を登録できませんでした。${failures.join(" / ")}`,
          );
      }
      try {
        await reload();
      } catch (error) {
        const refreshError = `一覧の更新に失敗しました：${errorText(error)}`;
        setError((previous) =>
          previous ? `${previous} ${refreshError}` : refreshError,
        );
      }
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  async function removeAttachment(item: ChatAttachment) {
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
    if (!draft.trim() || busy || pendingJob || !can("retrieve")) return;
    setTerminalJob(null);
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
      const response = await api<Message | ChatJobAccepted>(
        `/conversations/${id}/messages`,
        json("POST", {
          text: draft,
          scope,
          attachment_ids: attachments.map((item) => item.id),
        }),
      );
      if ("job_id" in response) {
        // The model slot was busy: the question waits in line and its answer
        // is stored in the conversation, so a reload after completion shows it.
        setPendingJob({
          id: response.job_id,
          conversation: id,
          text: response.text,
          status: "queued",
          cancelRequested: false,
        });
      } else {
        setMessages((items) => [...items, response]);
      }
      setDraft("");
      await reload();
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  async function cancelPendingJob() {
    if (!pendingJob) return;
    setError("");
    try {
      await api(`/chat-jobs/${pendingJob.id}`, json("DELETE", {}));
      // The UI may still say queued after the worker atomically started the job.
      // Keep polling until the server reports its terminal cancelled state.
      setPendingJob((current) =>
        current && current.id === pendingJob.id
          ? { ...current, cancelRequested: true }
          : current,
      );
      setNotice(
        "質問の取り消しを受け付けました。処理終了後に結果を破棄します。",
      );
    } catch (error) {
      setError(errorText(error));
    }
  }
  async function openConversation(id: string) {
    setBusy(true);
    try {
      const conv = await api<Conversation>(`/conversations/${id}`);
      conversationRef.current = id;
      setTerminalJob(null);
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
  async function openSource(document: string, chunkId?: string) {
    if (!source) sourceTrigger.current = documentElement();
    const request = ++sourceRequest.current;
    setSourceError("");
    try {
      const query = conversationId
        ? `?conversation_id=${encodeURIComponent(conversationId)}`
        : "";
      const path = `/documents/${encodeURIComponent(document)}`;
      const [metadata, chunks] = await Promise.all([
        api<Document>(`${path}${query}`),
        api<SourceChunk[]>(`${path}/chunks${query}`),
      ]);
      if (chunkId && !chunks.some((chunk) => chunk.id === chunkId))
        throw new Error(
          "引用箇所が更新または削除されています。最新の資料を確認してください。",
        );
      if (request === sourceRequest.current)
        setSource({
          document: metadata,
          chunks,
          selectedChunk: chunkId ?? null,
        });
    } catch (error) {
      if (request === sourceRequest.current) {
        if (source) setSourceError(errorText(error));
        else setError(errorText(error));
      }
    }
  }
  function closeSource() {
    sourceRequest.current++;
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
            activeProject.current = e.target.value;
            libraryRequest.current++;
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
          {(user.system_admin || can("manage_roles") || !!projectId) && (
            <>
              <div className="nav-divider" />
              <p className="nav-heading">管理</p>
              <details open>
                <summary>
                  利用者・アクセス <ChevronDown size={12} />
                </summary>
                {user.system_admin && navButton("users")}
                {can("manage_roles") && navButton("roles")}
                {user.system_admin && navButton("projects")}
                {!!projectId && navButton("delegations")}
              </details>
            </>
          )}
          <details open>
            <summary>
              データ・処理 <ChevronDown size={12} />
            </summary>
            {navButton("ingestion")}
            {user.system_admin && navButton("storage")}
            {user.system_admin && navButton("load")}
            {navButton("settings")}
          </details>
          {user.system_admin && (
            <details open={page === "audit"}>
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
          <ChatView
            attachments={attachments}
            busy={busy}
            canRetrieve={can("retrieve")}
            canUpload={can("upload")}
            terminalJob={terminalJob}
            conversationId={conversationId}
            draft={draft}
            messages={messages}
            pendingJob={pendingJob}
            scope={scope}
            onAddFiles={(files) => void addFiles(files)}
            onCancelPendingJob={() => void cancelPendingJob()}
            onChangeDraft={setDraft}
            onOpenSource={(documentId, chunkId) => {
              void openSource(documentId, chunkId);
            }}
            onRemoveAttachment={(attachment) =>
              void removeAttachment(attachment)
            }
            onScopeChange={setScope}
            onSubmit={send}
          />
        )}
        {projectId && ["shared", "personal", "ingestion"].includes(page) && (
          <>
            <div className="section-toolbar">
              <p className="muted">
                {page === "ingestion"
                  ? "安全検査を通過していない資料は隔離され、検索には使われません。"
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
            {page === "ingestion" && (
              <IngestionProgress
                documents={documents}
                refresh={ingestionRefresh}
              />
            )}
            <DocumentList
              key={projectId}
              projectId={projectId}
              documents={documents.filter(
                (doc) => page === "ingestion" || doc.kind === page,
              )}
              canPublish={can("publish")}
              canManageRoles={can("manage_roles")}
              onSource={openSource}
              onChanged={reload}
              onError={scopedError}
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
                          if (conversationRef.current === conv.id) newChat();
                          return reload();
                        })
                        .catch((error) => scopedError(errorText(error)));
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
          <RoleEditor
            key={projectId}
            projectId={projectId}
            onError={setError}
          />
        )}
        {page === "users" && user.system_admin && (
          <AdminUsers currentUserId={user.id} />
        )}
        {page === "audit" && user.system_admin && (
          <AdminList key="audit" kind="audit" />
        )}
        {page === "projects" && user.system_admin && <AdminProjects />}
        {page === "delegations" && <AdminDelegations />}
        {page === "storage" && user.system_admin && <AdminStorage />}
        {page === "load" && user.system_admin && <AdminLoad />}
        {page === "settings" && (
          <div className="settings">
            <h2>処理先</h2>
            <p>
              既定はローカルの原文検索です。管理者がOllamaモデルを明示的に有効化した場合は、参照資料に基づく回答を生成します。
            </p>
            {user.system_admin && <ModelSettings />}
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
                const controls =
                  event.currentTarget.querySelectorAll<HTMLButtonElement>(
                    "button:not(:disabled)",
                  );
                const first = controls[0];
                const last = controls[controls.length - 1];
                const inside = Array.from(controls).some(
                  (control) => control === document.activeElement,
                );
                if (!inside) {
                  event.preventDefault();
                  (event.shiftKey ? last : first)?.focus();
                } else if (event.shiftKey && document.activeElement === first) {
                  event.preventDefault();
                  last?.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                  event.preventDefault();
                  first?.focus();
                }
              }
            }}
          >
            <div className="source-heading">
              <div className="section-toolbar">
                <h2>出典の原文</h2>
                <button ref={sourceClose} onClick={closeSource}>
                  閉じる
                </button>
              </div>
              <p className="source-document-name">{source.document.name}</p>
            </div>
            {sourceError && <p role="alert">{sourceError}</p>}
            {source.chunks.map((chunk) => (
              <div
                key={chunk.id}
                ref={source.selectedChunk === chunk.id ? sourceTarget : null}
                className={
                  source.selectedChunk === chunk.id
                    ? "selected-source"
                    : undefined
                }
                role={source.selectedChunk === chunk.id ? "region" : undefined}
                aria-label={
                  source.selectedChunk === chunk.id
                    ? `引用箇所 p.${chunk.page} chunk ${chunk.ordinal}`
                    : undefined
                }
                tabIndex={source.selectedChunk === chunk.id ? -1 : undefined}
              >
                <p className="muted">
                  p.{chunk.page} · chunk {chunk.ordinal}
                </p>
                <pre>{chunk.text}</pre>
              </div>
            ))}
            {can("retrieve") && (
              <RelatedDocuments
                key={`${source.document.id}:${conversationId ?? ""}`}
                documentId={source.document.id}
                conversationId={conversationId}
                onOpen={openSource}
              />
            )}
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
  projectId,
  documents,
  canPublish,
  canManageRoles,
  onSource,
  onChanged,
  onError,
}: {
  projectId: string;
  documents: Document[];
  canPublish: boolean;
  canManageRoles: boolean;
  onSource: (id: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onError: (error: string) => void;
}) {
  const [publication, setPublication] = useState<string | null>(null);
  const [role, setRole] = useState("researcher");
  const [access, setAccess] = useState("read");
  const [pending, setPending] = useState(false);
  const [customRoles, setCustomRoles] = useState<Role[]>([]);
  useEffect(() => {
    if (!canManageRoles) return;
    const controller = new AbortController();
    void api<Roles>(`/projects/${encodeURIComponent(projectId)}/roles`, {
      signal: controller.signal,
    })
      .then((catalog) => {
        if (!controller.signal.aborted)
          setCustomRoles(
            catalog.custom.filter((item) => item.permissions.includes("read")),
          );
      })
      .catch((error) => {
        if (!controller.signal.aborted) onError(errorText(error));
      });
    return () => controller.abort();
  }, [projectId, canManageRoles, onError]);
  const roleNames: Record<string, string> = {
    researcher: "研究者",
    viewer: "閲覧者",
    project_lead: "プロジェクト責任者",
  };
  const selectedCustom = customRoles.find((item) => item.id === role);
  const mayRetrieve =
    !selectedCustom || selectedCustom.permissions.includes("retrieve");
  async function act(action: () => Promise<unknown>) {
    setPending(true);
    onError("");
    try {
      await action();
      await onChanged();
      return true;
    } catch (error) {
      onError(errorText(error));
      return false;
    } finally {
      setPending(false);
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
                disabled={pending}
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
                disabled={pending}
                onClick={() => {
                  setPublication(publication === doc.id ? null : doc.id);
                  setRole("researcher");
                  setAccess("read");
                }}
              >
                公開先
              </button>
            )}
            {doc.owned && (
              <button
                disabled={pending}
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
                      grants: [
                        {
                          role,
                          operations:
                            access === "retrieve" && mayRetrieve
                              ? ["read", "retrieve"]
                              : ["read"],
                        },
                      ],
                    }),
                  ),
                ).then((saved) => {
                  if (saved) setPublication(null);
                });
              }}
            >
              <label>
                ロール
                <select
                  disabled={pending}
                  value={role}
                  onChange={(event) => {
                    setRole(event.target.value);
                    setAccess("read");
                  }}
                >
                  <option value="researcher">研究者</option>
                  <option value="viewer">閲覧者</option>
                  <option value="project_lead">プロジェクト責任者</option>
                  {customRoles.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                許可する操作
                <select
                  value={access}
                  disabled={pending}
                  onChange={(event) => setAccess(event.target.value)}
                >
                  <option value="read">閲覧のみ</option>
                  <option value="retrieve" disabled={!mayRetrieve}>
                    閲覧・チャット参照
                  </option>
                </select>
              </label>
              <p>
                「{doc.name}」を、このプロジェクトの「
                {roleNames[role] ?? selectedCustom?.name}
                」に{access === "retrieve" ? "閲覧・チャット参照" : "閲覧のみ"}
                を許可します。
              </p>
              <p className="muted">
                保存すると、この資料の既存の公開先をこの設定で置き換えます。
              </p>
              <button type="submit" disabled={pending}>
                公開設定を保存
              </button>
              <button
                type="button"
                disabled={pending}
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
  const [editing, setEditing] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const alive = useRef(true);
  useEffect(() => {
    let active = true;
    alive.current = true;
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
        ロールは現在のプロジェクト内で有効です。管理権限の委任は無効です。
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

function AdminUsers({ currentUserId }: { currentUserId?: string }) {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <>
      <ProvisionUser onCreated={() => setRefreshKey((key) => key + 1)} />
      <AdminList key={refreshKey} kind="users" currentUserId={currentUserId} />
    </>
  );
}

function AdminList({
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
