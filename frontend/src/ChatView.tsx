import { useRef } from "react";
import type { FormEvent, ReactNode } from "react";
import { ArrowUp, FileText, Plus, X } from "lucide-react";
import { statusName, type Message } from "./api";
import { StructuredCitationText } from "./StructuredCitationText";
import {
  projectChatRows,
  type ChatAttachment,
  type ChatJobNotice,
  type PendingChatJob,
} from "./chatProjection";

function IconButton({
  label,
  onClick,
  children,
  disabled = false,
  type = "button",
}: {
  label: string;
  onClick?: () => void;
  children: ReactNode;
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      className="icon-button"
      type={type}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
      <span className="tooltip" role="tooltip">
        {label}
      </span>
    </button>
  );
}

export function ChatMessage({
  message,
  onOpenSource,
}: {
  message: Message;
  onOpenSource: (documentId: string, chunkId: string) => void;
}) {
  return (
    <article className="exchange">
      <p className="user-message">{message.text}</p>
      <div className="answer">
        {message.answer && (
          <>
            <h2>資料に基づく提案</h2>
            <p style={{ whiteSpace: "pre-wrap" }}>{message.answer}</p>
            <p className="footnote">
              {message.model}{" "}
              による生成内容です。判断には元資料を確認してください。
            </p>
          </>
        )}
        {message.answer_hidden && (
          <p>出典の削除または権限変更により、生成回答を非表示にしました。</p>
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
              onClick={() => onOpenSource(citation.document_id, citation.id)}
            >
              {citation.name} · p.{citation.page} · chunk {citation.ordinal}
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
  );
}

function ChatJobMessage({
  text,
  status,
  cancelRequested,
  detail,
  onCancel,
}: {
  text: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  cancelRequested: boolean;
  detail?: string;
  onCancel?: () => void;
}) {
  const statusText =
    status === "cancelled"
      ? "質問を取り消しました。回答は表示されません。"
      : status === "failed"
        ? `回答を生成できませんでした。${detail ?? ""}`
        : status === "done"
          ? "回答が会話に追加されました。"
          : cancelRequested
            ? "質問の取り消しを受け付けました。処理終了後に結果を破棄します。"
            : status === "running"
              ? "回答を作成中です。完成するとこの会話に表示されます。"
              : "回答の生成は順番待ちです。モデルが空くと自動的に処理されます。";
  return (
    <article className="exchange">
      {status !== "done" && status !== "failed" && (
        <p className="user-message">{text}</p>
      )}
      <div className="answer">
        <p
          className="chat-processing-status"
          role="status"
          data-status={status}
        >
          {statusText}
        </p>
        {onCancel && !cancelRequested && (
          <button className="text-link" onClick={onCancel}>
            この質問を取り消す
          </button>
        )}
      </div>
    </article>
  );
}

export function ChatComposer({
  attachments,
  busy,
  canRetrieve,
  canUpload,
  draft,
  pendingJob,
  onAddFiles,
  onChangeDraft,
  onRemoveAttachment,
  onSubmit,
}: {
  attachments: ChatAttachment[];
  busy: boolean;
  canRetrieve: boolean;
  canUpload: boolean;
  draft: string;
  pendingJob: PendingChatJob | null;
  onAddFiles: (files: File[]) => void;
  onChangeDraft: (draft: string) => void;
  onRemoveAttachment: (attachment: ChatAttachment) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  return (
    <>
      <form
        className="composer"
        onSubmit={onSubmit}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          onAddFiles(Array.from(event.dataTransfer.files));
        }}
      >
        {attachments.length > 0 && (
          <ul className="attachments">
            {attachments.map((item) => {
              const failed =
                item.status === "failed" || item.status === "quarantined";
              return (
                <li key={item.key}>
                  <FileText size={15} />
                  <span className="attachment-name" title={item.name}>
                    {item.name}
                  </span>
                  <span
                    className={failed ? "error" : "muted"}
                    title={item.reason}
                  >
                    {statusName[item.status] ?? item.status}
                  </span>
                  <IconButton
                    label={`${item.name}を取り外す`}
                    disabled={busy}
                    onClick={() => onRemoveAttachment(item)}
                  >
                    <X size={14} />
                  </IconButton>
                  {item.reason && (
                    <span className="attachment-reason">{item.reason}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <textarea
          placeholder="メッセージを入力"
          aria-label="メッセージ"
          value={draft}
          maxLength={4000}
          disabled={busy || !canRetrieve}
          onChange={(event) => onChangeDraft(event.target.value)}
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
            disabled={busy || !canUpload}
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
              onAddFiles(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
          <span className="send-state" role="status">
            {busy ? "処理中…" : ""}
          </span>
          <IconButton
            label="送信"
            type="submit"
            disabled={busy || !!pendingJob || !draft.trim() || !canRetrieve}
          >
            <ArrowUp size={20} />
          </IconButton>
        </div>
      </form>
      <p className="composer-note">検証用の検索です。外部AIへ送信しません。</p>
    </>
  );
}

export function ChatView({
  attachments,
  busy,
  canRetrieve,
  canUpload,
  terminalJob,
  conversationId,
  draft,
  messages,
  pendingJob,
  scope,
  onAddFiles,
  onCancelPendingJob,
  onChangeDraft,
  onOpenSource,
  onRemoveAttachment,
  onScopeChange,
  onSubmit,
}: {
  attachments: ChatAttachment[];
  busy: boolean;
  canRetrieve: boolean;
  canUpload: boolean;
  terminalJob: ChatJobNotice | null;
  conversationId: string | null;
  draft: string;
  messages: Message[];
  pendingJob: PendingChatJob | null;
  scope: string;
  onAddFiles: (files: File[]) => void;
  onCancelPendingJob: () => void;
  onChangeDraft: (draft: string) => void;
  onOpenSource: (documentId: string, chunkId: string) => void;
  onRemoveAttachment: (attachment: ChatAttachment) => void;
  onScopeChange: (scope: string) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const rows = projectChatRows(
    messages,
    pendingJob,
    terminalJob,
    conversationId,
  );
  return (
    <div className="chat">
      <label className="scope-label">
        参照範囲
        <select
          value={scope}
          disabled={busy}
          onChange={(event) => onScopeChange(event.target.value)}
        >
          <option value="all">共有資料＋個人資料</option>
          <option value="shared">共有資料</option>
          <option value="personal">個人資料</option>
        </select>
      </label>
      <div className="messages" aria-live="polite">
        {rows.length === 0 ? (
          <div className="chat-empty">
            <FileText size={25} strokeWidth={1.3} />
            <p>参照できる資料を調べる</p>
            <span>資料の本文と出典を確認できます。</span>
          </div>
        ) : (
          rows.map((row) =>
            row.kind === "message" ? (
              <ChatMessage
                key={row.key}
                message={row.message}
                onOpenSource={onOpenSource}
              />
            ) : (
              <ChatJobMessage
                key={row.key}
                text={row.text}
                status={row.status}
                cancelRequested={row.cancelRequested}
                detail={row.detail}
                onCancel={
                  (row.status === "queued" || row.status === "running") &&
                  pendingJob &&
                  row.key === `job:${pendingJob.id}`
                    ? onCancelPendingJob
                    : undefined
                }
              />
            ),
          )
        )}
      </div>
      <ChatComposer
        attachments={attachments}
        busy={busy}
        canRetrieve={canRetrieve}
        canUpload={canUpload}
        draft={draft}
        pendingJob={pendingJob}
        onAddFiles={onAddFiles}
        onChangeDraft={onChangeDraft}
        onRemoveAttachment={onRemoveAttachment}
        onSubmit={onSubmit}
      />
    </div>
  );
}
