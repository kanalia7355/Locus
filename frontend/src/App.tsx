import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import {
  ArrowUp,
  Check,
  ChevronDown,
  FileText,
  LogOut,
  PanelLeft,
  Plus,
  X,
} from "lucide-react";
import { dialogControls } from "./dialog";
import { IconButton } from "./IconButton";
import { SettingsDialog } from "./SettingsDialog";
import { Sidebar } from "./Sidebar";
import {
  api,
  errorText,
  ingesting,
  isEventStream,
  json,
  statusName,
  streamEvents,
  streamRequest,
  uniqueKey,
} from "./api";
import { RelatedDocuments } from "./RelatedDocuments";
import { StructuredCitationText } from "./StructuredCitationText";
import { IngestionProgress } from "./IngestionProgress";
import {
  parseThemePreference,
  resolveColorScheme,
  THEME_STORAGE_KEY,
} from "./theme";
import type { ColorScheme, ThemePreference } from "./theme";
import { useUserInvalidForm } from "./ProvisionUser";
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



function readStoredTheme(): string | null {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY);
  } catch {
    return null;
  }
}

function systemPrefersDark(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function applyColorScheme(scheme: ColorScheme) {
  document.documentElement.dataset.mode = scheme;
}

// 初期描画で明るい配色が一瞬見える（ちらつく）ことを防ぐため、
// モジュール評価の時点で <html data-mode> を決めておく。
// localStorage が読めない環境ではシステム設定に従う。
if (typeof window !== "undefined" && typeof document !== "undefined") {
  try {
    applyColorScheme(
      resolveColorScheme(readStoredTheme(), systemPrefersDark()),
    );
  } catch {
    // 適用に失敗しても、CSS の media query がシステム設定を反映する
  }
}

type Page = "chat" | "shared" | "personal" | "ingestion";
type Attachment = {
  key: string;
  name: string;
  status: string;
  id?: string;
  reason?: string;
};
const labels: Record<Page, string> = {
  chat: "会話",
  shared: "共有資料",
  personal: "個人資料",
  ingestion: "取り込み状況",
};




const scopeOptions = [
  { value: "all", label: "共有資料＋個人資料" },
  { value: "shared", label: "共有資料" },
  { value: "personal", label: "個人資料" },
] as const;
type ScopeValue = (typeof scopeOptions)[number]["value"];

// The scope picker is a button plus a popup, not an OS <select>: the native
// control cannot match the composer's chip styling. Everything <select> gave
// unpaid is paid back here — arrow keys move, Enter commits, Escape closes,
// and focus stays inside the picker while it is open. The popup rides the
// Popover API (Baseline 2025-01-27), so outside-click light dismiss, Escape
// and top-layer stacking come from the platform; only the arrow keys and
// Enter remain hand-rolled. Positioning is one getBoundingClientRect() read
// at open time with a single above/below flip — no CSS anchor positioning
// (Chrome/Edge 157+ and Safari 27+ only, Firefox unsupported).
function ScopePicker({
  value,
  disabled = false,
  onChange,
}: {
  value: ScopeValue;
  disabled?: boolean;
  onChange: (value: ScopeValue) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(() =>
    Math.max(
      0,
      scopeOptions.findIndex((option) => option.value === value),
    ),
  );
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [listId] = useState(() => `scope-list-${uniqueKey()}`);
  const optionId = (index: number) => `${listId}-option-${index}`;
  const selected =
    scopeOptions.find((option) => option.value === value) ?? scopeOptions[0];

  // 開閉を React の open に合わせて Popover API へ反映する。外側クリックや
  // Escape による light dismiss はブラウザが直接ポップオーバーを閉じるので、
  // toggle イベント側でも open を追随させる（二重に閉じても無害な冪等な経路）。
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (open) {
      try {
        list.showPopover();
      } catch {
        // 既に開いているポップオーバーに showPopover() を呼ぶと投げられる。
        // 二重呼び出しはここで捨てる。
      }
      list.focus();
      // 開くたびに座標を一度だけ測る。上端に収まらなければチップの下側へ出す。
      const chip = triggerRef.current?.getBoundingClientRect();
      if (chip) {
        const height = list.getBoundingClientRect().height;
        const top = chip.top - height - 8;
        const left = Math.min(
          Math.max(chip.left, 8),
          Math.max(
            8,
            window.innerWidth - list.getBoundingClientRect().width - 8,
          ),
        );
        list.style.top = `${top >= 8 ? top : chip.bottom + 8}px`;
        list.style.left = `${left}px`;
      }
      return;
    }
    try {
      list.hidePopover();
    } catch {
      // light dismiss で既に閉じられている場合は投げられる。二重に閉じない。
    }
  }, [open]);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const onToggle = (event: Event) => {
      if ((event as ToggleEvent).newState !== "closed") return;
      // light dismiss（外側クリック / Escape）で勝手に閉じた場合に React の
      // 状態を追随させ、どちらが閉じてもチップへフォーカスを戻す。
      setOpen(false);
      triggerRef.current?.focus();
    };
    list.addEventListener("toggle", onToggle);
    return () => list.removeEventListener("toggle", onToggle);
  }, []);

  function openPopup() {
    setActive(
      Math.max(
        0,
        scopeOptions.findIndex((option) => option.value === value),
      ),
    );
    setOpen(true);
  }
  function closePopup() {
    setOpen(false);
    triggerRef.current?.focus();
  }
  function choose(next: ScopeValue) {
    onChange(next);
    closePopup();
  }
  function onKeyDown(event: KeyboardEvent) {
    if (!open) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        openPopup();
      }
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((current) => (current + 1) % scopeOptions.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive(
          (current) =>
            (current - 1 + scopeOptions.length) % scopeOptions.length,
        );
        break;
      case "Home":
        event.preventDefault();
        setActive(0);
        break;
      case "End":
        event.preventDefault();
        setActive(scopeOptions.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        choose(scopeOptions[active].value);
        break;
      case "Escape":
        event.preventDefault();
        closePopup();
        break;
      case "Tab":
        // Focus must not slip out while the popup is open; closing first
        // keeps the focus order predictable instead.
        event.preventDefault();
        closePopup();
        break;
      default:
        break;
    }
  }

  return (
    <div className="scope-picker" onKeyDown={onKeyDown}>
      <button
        type="button"
        className="scope-chip"
        ref={triggerRef}
        aria-label="参照範囲"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        onClick={() => (open ? closePopup() : openPopup())}
      >
        <span className="scope-chip-label">{selected.label}</span>
        <ChevronDown
          size={14}
          aria-hidden="true"
          className={open ? "scope-chip-caret open" : "scope-chip-caret"}
        />
      </button>
      <ul
        id={listId}
        ref={listRef}
        className="scope-popup"
        role="listbox"
        popover="auto"
        aria-label="参照範囲"
        tabIndex={-1}
        data-open={open}
        aria-activedescendant={open ? optionId(active) : undefined}
        aria-hidden={!open}
      >
        {scopeOptions.map((option, index) => (
          <li
            key={option.value}
            id={optionId(index)}
            role="option"
            aria-selected={option.value === value}
            className={[
              "scope-option",
              index === active ? "active" : "",
              option.value === value ? "selected" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => choose(option.value)}
            onMouseEnter={() => setActive(index)}
          >
            <span>{option.label}</span>
            {option.value === value && (
              <Check
                size={14}
                aria-hidden="true"
                className="scope-option-check"
              />
            )}
          </li>
        ))}
      </ul>
    </div>
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
  const { invalidFields, attachForm } = useUserInvalidForm();
  const rotate = !!user?.must_rotate;
  const fieldProps = (id: string) =>
    ({
      id,
      "aria-invalid": invalidFields.has(id),
      "aria-describedby": invalidFields.has(id) ? `${id}-error` : undefined,
    }) as const;
  const fieldError = (id: string, message: string) =>
    invalidFields.has(id) ? (
      <p id={`${id}-error`} className="field-error">
        {message}
      </p>
    ) : null;
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
      <div className="access-brand">Locus</div>
      <form onSubmit={submit} className="access-form" ref={attachForm}>
        <p className="eyebrow">ローカル検証環境 · 合成データ専用</p>
        <h1>{rotate ? "仮パスワードの変更" : "ログイン"}</h1>
        {rotate ? (
          <p>資料を開く前に、仮パスワードを変更してください。</p>
        ) : (
          <p>管理者が発行した利用者IDでログインしてください。</p>
        )}
        {!rotate && (
          <>
            <label>
              利用者ID
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                maxLength={64}
                {...fieldProps("access-username")}
              />
            </label>
            {fieldError(
              "access-username",
              "利用者IDが未入力です。管理者が発行した利用者IDを入力してください。",
            )}
          </>
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
            {...fieldProps("access-password")}
          />
        </label>
        {fieldError(
          "access-password",
          "パスワードが未入力です。管理者が発行したパスワードを入力してください。",
        )}
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
                {...fieldProps("access-new-password")}
              />
            </label>
            {fieldError(
              "access-new-password",
              "新しいパスワードは14〜128文字で設定してください。",
            )}
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
                {...fieldProps("access-confirmation-password")}
              />
            </label>
            {fieldError(
              "access-confirmation-password",
              "新しいパスワードと同じものをもう一度、14〜128文字で入力してください。",
            )}
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
  const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
    parseThemePreference(readStoredTheme()),
  );
  // 利用者の選択はメディアクエリより常に優先する（両方向とも）。
  // 「システムに従う」の間は OS 側のカラースキーム変更にも追従する。
  useEffect(() => {
    const media =
      typeof window.matchMedia === "function"
        ? window.matchMedia("(prefers-color-scheme: dark)")
        : null;
    const apply = () =>
      applyColorScheme(
        resolveColorScheme(themePreference, media?.matches ?? false),
      );
    apply();
    if (!media) return undefined;
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [themePreference]);
  const changeThemePreference = (preference: ThemePreference) => {
    setThemePreference(preference);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // 保存できない環境では、この画面の表示だけ反映する
    }
  };
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
  return (
    <Workspace
      key={user.id}
      user={user}
      onLogout={() => setUser(null)}
      themePreference={themePreference}
      onThemePreferenceChange={changeThemePreference}
    />
  );
}

const WIDE_LAYOUT_MEDIA_QUERY = "(min-width: 48em)";

function isWideLayout(): boolean {
  // jsdom など matchMedia が未実装または常に false を返すスタブ環境では広い配置に倒す。
  if (
    typeof window.matchMedia !== "function" ||
    !window.matchMedia("(min-width: 0px)").matches
  ) {
    return true;
  }
  return window.matchMedia(WIDE_LAYOUT_MEDIA_QUERY).matches;
}

function Workspace({
  user,
  onLogout,
  themePreference,
  onThemePreferenceChange,
}: {
  user: User;
  onLogout: () => void;
  themePreference: ThemePreference;
  onThemePreferenceChange: (preference: ThemePreference) => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [page, setPage] = useState<Page>("chat");
  const [sidebar, setSidebar] = useState(
    () => localStorage.getItem("locus-sidebar") !== "closed" && isWideLayout(),
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [documentQuery, setDocumentQuery] = useState("");
  const [history, setHistory] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [scope, setScope] = useState<ScopeValue>("all");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [ingestionRefresh, setIngestionRefresh] = useState<
    "waiting" | "updating" | "stopped"
  >("waiting");
  const [busy, setBusy] = useState(false);
  const [pendingJob, setPendingJob] = useState<{
    id: string;
    conversation: string;
    text: string;
    status: "queued" | "running";
    cancelRequested: boolean;
    streaming?: boolean;
  } | null>(null);
  const [streamedAnswer, setStreamedAnswer] = useState("");
  const [cancelledJob, setCancelledJob] = useState<{
    conversation: string;
    text: string;
  } | null>(null);
  const [source, setSource] = useState<{
    document: Document;
    chunks: SourceChunk[];
    selectedChunk: string | null;
  } | null>(null);
  const [sourceError, setSourceError] = useState("");
  const conversationPromise = useRef<Promise<string> | null>(null);
  const conversationRef = useRef<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const personalInput = useRef<HTMLInputElement>(null);
  const sourceDialog = useRef<HTMLDialogElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const sidebarToggle = useRef<HTMLButtonElement>(null);
  const lastPage = useRef(page);
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
      !documents.some((doc) => ingesting(doc.status))
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
    if (!attachments.some((item) => ingesting(item.status))) return;
    const timer = setInterval(() => {
      void Promise.all(
        attachments
          .filter((item) => item.id && ingesting(item.status))
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
  const pendingStreaming = pendingJob?.streaming ?? false;
  const pendingJobIdRef = useRef<string | null>(null);
  pendingJobIdRef.current = pendingJobId ?? null;
  useEffect(() => {
    if (!pendingJobId || !pendingConversation || !pendingText) return;
    // Only poll for jobs belonging to the current conversation.
    // This prevents job state from carrying over when switching projects.
    if (pendingConversation !== conversationRef.current) return;
    // A streamed dialogue reports its own progress and outcome over SSE.
    if (pendingStreaming) return;
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
            setCancelledJob(null);
            if (status.conversation_id === conversationRef.current) {
              void api<Conversation>(`/conversations/${status.conversation_id}`)
                .then((conv) => {
                  if (
                    !controller.signal.aborted &&
                    conversationRef.current === status.conversation_id
                  )
                    setMessages(conv.messages ?? []);
                })
                .catch((error) => setError(errorText(error)));
            } else
              setNotice(
                "待機していた質問の回答が完成しました。サイドバーの会話から開いてください。",
              );
          } else if (status.status === "failed") {
            setPendingJob(null);
            setCancelledJob(null);
            setError(`回答を生成できませんでした。${status.detail}`);
          } else if (status.status === "cancelled") {
            setPendingJob(null);
            setCancelledJob({ conversation: job.conversation, text: job.text });
            setNotice("質問を取り消しました。");
          }
        })
        .catch((error) => {
          if (controller.signal.aborted || pendingJobIdRef.current !== job.id)
            return;
          clearInterval(timer);
          setPendingJob(null);
          setError(
            `質問の状態確認を停止しました。回答はサイドバーの会話から確認できます。${errorText(error)}`,
          );
        });
    }, 2000);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [pendingJobId, pendingConversation, pendingText, pendingStreaming]);

  useEffect(() => {
    if (lastPage.current === page) return;
    lastPage.current = page;
    // The heading is the first element of the new page, so keyboard and
    // screen reader users continue from the content that replaced it.
    headingRef.current?.focus();
  }, [page]);

  useEffect(() => {
    if (!source) return;
    // showModal() is what makes the dialog modal: it moves the element to the
    // top layer, makes the rest of the page inert and contains focus. Opening
    // with the `open` attribute (or show()) would skip all of that. The .open
    // guard avoids calling showModal() again on a dialog that is already open
    // (e.g. a related document opened from inside it).
    const dialog = sourceDialog.current;
    if (dialog && !dialog.open) dialog.showModal();
    // AC: after entry animation focus lands on the initial position ("閉じる").
    // Keep it there even when a cited chunk is present; scroll the chunk into
    // view without stealing focus.
    const closeButton =
      dialog?.querySelector<HTMLElement>("form[method='dialog'] button") ??
      dialog?.querySelector<HTMLElement>("[autofocus]");
    closeButton?.focus();
    if (source.selectedChunk && sourceTarget.current) {
      sourceTarget.current.scrollIntoView?.({ block: "nearest" });
    }
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
    if (!isWideLayout()) setSidebar(false);
  }
  function newChat() {
    setCancelledJob(null);
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
        const key = uniqueKey();
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
  async function sendStreamed(
    id: string,
    question: {
      text: string;
      scope: string;
      attachment_ids: (string | undefined)[];
    },
  ): Promise<boolean> {
    // Returns false when the answer must be requested the ordinary way: an
    // unavailable stream, a busy model slot, or a browser without streams.
    let response: Response;
    try {
      response = await streamRequest(
        `/conversations/${id}/messages/stream`,
        question,
      );
    } catch {
      return false;
    }
    if (!isEventStream(response)) return false;
    let streamed = false;
    let queued: typeof pendingJob = null;
    try {
      for await (const part of streamEvents(response)) {
        if (part.event === "start") {
          setStreamedAnswer("");
          setPendingJob({
            id: String(part.data.job_id ?? ""),
            conversation: id,
            text: question.text,
            status: "running",
            cancelRequested: false,
            streaming: true,
          });
        } else if (part.event === "delta") {
          setStreamedAnswer(
            (current) => current + String(part.data.text ?? ""),
          );
        } else if (part.event === "message") {
          setMessages((items) => [...items, part.data as unknown as Message]);
          streamed = true;
        } else if (part.event === "cancelled") {
          setCancelledJob({ conversation: id, text: question.text });
          setNotice("質問を取り消しました。");
          streamed = true;
        } else if (part.event === "queued") {
          // The slot was taken after the stream opened, so the server put this
          // question in the waiting line. Resending it would charge the
          // per-user dialogue budget twice for one question.
          queued = {
            id: String(part.data.job_id ?? ""),
            conversation: id,
            text: question.text,
            status: "queued" as const,
            cancelRequested: false,
          };
          streamed = true;
        } else if (part.event === "error") {
          setError(
            `回答を生成できませんでした。${String(part.data.detail ?? "")}`,
          );
          streamed = true;
        }
      }
    } catch (error) {
      setError(
        `逐次表示が途切れました。回答はサイドバーの会話から確認できます。${errorText(error)}`,
      );
      streamed = true;
    } finally {
      // A queued question keeps its waiting entry; the status poll takes over
      // from here because the stream is closed.
      setPendingJob(queued);
      setStreamedAnswer("");
    }
    return streamed;
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy || pendingJob || !can("retrieve")) return;
    setCancelledJob(null);
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
      const question = {
        text: draft,
        scope,
        attachment_ids: attachments.map((item) => item.id),
      };
      if (await sendStreamed(id, question)) {
        setDraft("");
        await reload();
        return;
      }
      const response = await api<Message | ChatJobAccepted>(
        `/conversations/${id}/messages`,
        json("POST", question),
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
      setCancelledJob(null);
      setConversationId(id);
      setMessages(conv.messages ?? []);
      setAttachments(
        (conv.attachments ?? []).map((doc) => ({
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
  async function deleteConversation(id: string) {
    setError("");
    try {
      await api(`/conversations/${id}`, json("DELETE"));
      if (conversationRef.current === id) newChat();
      await reload();
    } catch (error) {
      scopedError(errorText(error));
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
  return (
    <div className={`workspace ${sidebar ? "sidebar-open" : "sidebar-closed"}`}>
      <header className="topbar">
        <IconButton
          label={sidebar ? "サイドバーを閉じる" : "サイドバーを開く"}
          onClick={toggleSidebar}
          buttonRef={sidebarToggle}
          aria-expanded={sidebar}
          aria-controls="workspace-sidebar"
        >
          <PanelLeft size={19} />
        </IconButton>
        <strong>Locus</strong>
        <select
          className="project-select"
          aria-label="プロジェクト"
          value={projectId}
          disabled={busy}
          onChange={(e) => {
            activeProject.current = e.target.value;
            libraryRequest.current++;
            newChat();
            setPendingJob(null);
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
      <Sidebar
        open={sidebar}
        onClose={() => {
          setSidebar(false);
          sidebarToggle.current?.focus();
        }}
        onNewChat={newChat}
        conversations={history}
        activeConversationId={conversationId}
        onOpenConversation={(id) => {
          void openConversation(id);
        }}
        onDeleteConversation={(id) => {
          void deleteConversation(id);
        }}
        page={page}
        onNavigate={(next) => navigate(next)}
        user={user}
        onOpenSettings={() => setSettingsOpen(true)}
        busy={busy}
      />
      {sidebar && (
        <button
          className="sidebar-backdrop"
          aria-label="メニューを閉じる"
          onClick={() => {
            setSidebar(false);
            sidebarToggle.current?.focus();
          }}
        />
      )}
      <main className="main">
        <div className="page-heading">
          <h1 ref={headingRef} tabIndex={-1}>
            {labels[page]}
          </h1>
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
            <p className="chat-notice">
              Locusは間違えることがあります。重要な情報は確認してください。
            </p>
            <div className="messages" aria-live="polite">
              {messages.length === 0 ? (
                <div className="chat-empty">
                  <FileText size={25} strokeWidth={1.3} />
                  <p>資料を参照して質問できます</p>
                  <span>資料の本文と出典を確認できます。</span>
                </div>
              ) : (
                messages.map((message) => (
                  <article className="exchange" key={message.id}>
                    <p className="user-message">{message.text}</p>
                    <div className="answer">
                      {message.answer && (
                        <>
                          <h2>資料に基づく提案</h2>
                          <p style={{ whiteSpace: "pre-wrap" }}>
                            {message.answer}
                          </p>
                          <p className="footnote">
                            {message.model}{" "}
                            による生成内容です。判断には元資料を確認してください。
                          </p>
                        </>
                      )}
                      {message.answer_hidden && (
                        <p>
                          出典の削除または権限変更により、生成回答を非表示にしました。
                        </p>
                      )}
                      <h2>
                        {message.citations.length
                          ? "資料に見つかった記述"
                          : "参照できる記述が見つかりませんでした"}
                      </h2>
                      {message.citations.map((citation) => (
                        <div key={citation.id} className="citation-excerpt">
                          <StructuredCitationText
                            text={citation.text}
                            label={`${citation.name} p.${citation.page} chunk ${citation.ordinal} の表`}
                          />
                          <button
                            className="text-link"
                            onClick={() => {
                              void openSource(
                                citation.document_id,
                                citation.id,
                              );
                            }}
                          >
                            {citation.name} · p.{citation.page} · chunk{" "}
                            {citation.ordinal}
                          </button>
                        </div>
                      ))}
                      <p className="footnote">
                        {message.citations.length
                          ? message.answer
                            ? "以下の出典は検索で抽出した原文です。生成内容とは区別して確認してください。"
                            : "検索で抽出した原文です。AI生成の回答ではありません。判断には元資料を確認してください。"
                          : "参照範囲・資料の処理状態・質問の語句を確認してください。"}
                      </p>
                    </div>
                  </article>
                ))
              )}
              {cancelledJob && cancelledJob.conversation === conversationId && (
                <article className="exchange">
                  <p className="user-message">{cancelledJob.text}</p>
                  <div className="answer">
                    <p role="status">
                      質問を取り消しました。回答は表示されません。
                    </p>
                  </div>
                </article>
              )}
              {pendingJob && pendingJob.conversation === conversationId && (
                <article className="exchange" aria-busy={true}>
                  <p className="user-message">{pendingJob.text}</p>
                  <div className="answer">
                    <p role="status">
                      {pendingJob.cancelRequested
                        ? "質問の取り消しを受け付けました。処理終了後に結果を破棄します。"
                        : pendingJob.streaming
                          ? "回答を作成中です。確定前の途中経過を表示しています。"
                          : pendingJob.status === "running"
                            ? "回答を作成中です。完成するとこの会話に表示されます。"
                            : "回答の生成は順番待ちです。モデルが空くと自動的に処理されます。待ち位置は混雑により変動します。"}
                    </p>
                    {streamedAnswer && (
                      <>
                        <h2>資料に基づく提案</h2>
                        {/* The surrounding list is aria-live="polite", so the
                            growing text is announced without a second region. */}
                        <p style={{ whiteSpace: "pre-wrap" }}>
                          {streamedAnswer}
                        </p>
                        <p className="footnote">
                          生成中の未検証の提案です。確定後に出典と併せて確認してください。
                        </p>
                      </>
                    )}
                    {!pendingJob.cancelRequested && (
                      <button
                        className="text-link"
                        onClick={() => {
                          void cancelPendingJob();
                        }}
                      >
                        この質問を取り消す
                      </button>
                    )}
                  </div>
                </article>
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
                <ScopePicker
                  value={scope}
                  disabled={busy}
                  onChange={setScope}
                />
                <span className="send-state" role="status">
                  {busy ? "処理中…" : pendingJob ? "順番待ちあり" : ""}
                </span>
                <IconButton
                  label="送信"
                  type="submit"
                  disabled={
                    busy || !!pendingJob || !draft.trim() || !can("retrieve")
                  }
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
                  ? "安全検査を通過していない資料は隔離され、検索には使われません。"
                  : page === "personal"
                    ? "本人のみが参照できる資料です。会話添付はここに自動登録されません。"
                    : "このプロジェクトで閲覧を許可された資料です。"}
              </p>
              <label className="search-field">
                <span className="visually-hidden">資料を検索</span>
                <input
                  type="search"
                  value={documentQuery}
                  onChange={(event) => setDocumentQuery(event.target.value)}
                  placeholder="資料名で検索"
                  aria-label="資料名で検索"
                />
              </label>
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
              documents={documents.filter((doc) => {
                if (page !== "ingestion" && doc.kind !== page) return false;
                const q = documentQuery.trim().toLowerCase();
                return !q || doc.name.toLowerCase().includes(q);
              })}
              canPublish={can("publish")}
              canManageRoles={can("manage_roles")}
              onSource={openSource}
              onChanged={reload}
              onError={scopedError}
            />
          </>
        )}
      </main>
      <SettingsDialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        user={user}
        project={project}
        can={can}
        themePreference={themePreference}
        onThemePreferenceChange={onThemePreferenceChange}
      />
      {source && (
        <dialog
          ref={sourceDialog}
          className="source-modal"
          aria-label="出典の原文"
          closedby="any"
          onClose={closeSource}
          onClick={(event) => {
            // Safari has no light dismiss for <dialog> (and does not support
            // closedby), so a click that lands on the dialog itself, outside
            // the content rectangle, closes it as the fallback for such
            // browsers. Chromium closes on the native closedby="any" path.
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
            onFocus={() =>
              dialogControls(sourceDialog.current).at(-1)?.focus()
            }
          />
          <div className="source-heading">
            <div className="section-toolbar">
              <h2>出典の原文</h2>
              {/* Only the close button sits in the dialog form:
                  RelatedDocuments renders plain <button>s, which would become
                  submit buttons and close the dialog on every click. */}
              <form method="dialog">
                <button autoFocus>閉じる</button>
              </form>
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
          <span
            className="focus-guard"
            tabIndex={0}
            onFocus={() => dialogControls(sourceDialog.current)[0]?.focus()}
          />
        </dialog>
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
                id={`document-name-${doc.id}`}
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
            {doc.owned && ingesting(doc.status) && (
              <button
                disabled={pending}
                aria-describedby={`document-name-${doc.id}`}
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
                aria-describedby={`document-name-${doc.id}`}
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
                aria-describedby={`document-name-${doc.id}`}
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

