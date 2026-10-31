export interface User {
  id: string;
  username: string;
  system_admin: boolean;
  must_rotate: boolean;
}
export interface Project {
  id: string;
  org_id: string;
  name: string;
  role: string;
  permissions: string[];
}
export interface Document {
  id: string;
  name: string;
  project_id: string;
  kind: string;
  status: string;
  reason: string;
  conversation_id: string | null;
  created: number;
  owned: boolean;
}
export interface Citation {
  id: string;
  document_id: string;
  name: string;
  page: number;
  ordinal: number;
  text: string;
}
export interface Message {
  id: string;
  text: string;
  scope: string;
  citations: Citation[];
}
export interface Conversation {
  id: string;
  project_id: string;
  created: number;
  messages: Message[];
  attachments: Document[];
}
export interface Role {
  id: string;
  name: string;
  permissions: string[];
}
export interface Roles {
  templates: Role[];
  custom: Role[];
  allowed_permissions: string[];
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    headers,
  });
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* use status fallback */
    }
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("locus-session-expired"));
    throw new Error(
      typeof detail === "string"
        ? detail
        : `操作できませんでした（${response.status}）。入力内容を確認してください。`,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export const json = (method: string, data?: unknown): RequestInit => ({
  method,
  ...(data === undefined ? {} : { body: JSON.stringify(data) }),
});
export const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "処理に失敗しました。再試行してください。";
export const statusName: Record<string, string> = {
  uploading: "送信中",
  queued: "解析待ち",
  scanning: "検査中",
  ready: "参照可能",
  quarantined: "隔離中",
  failed: "失敗",
  cancelled: "取消済み",
};
