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
export interface SourceChunk {
  id: string;
  document_id: string;
  page: number;
  ordinal: number;
  text: string;
}
export interface Citation extends SourceChunk {
  name: string;
}
export interface Message {
  id: string;
  text: string;
  scope: string;
  citations: Citation[];
  answer?: string | null;
  model?: string | null;
  answer_hidden?: boolean;
}
export interface RelatedDocument {
  document: Document;
  method: "lexical-common-terms";
  shared_term_count: number;
  evidence: {
    term: string;
    source_chunk_id: string;
    source_page: number;
    target_chunk_id: string;
    target_page: number;
  }[];
}
export interface Conversation {
  id: string;
  project_id: string;
  created: number;
  messages?: Message[];
  attachments?: Document[];
  preview?: string;
}
export interface ChatJobAccepted {
  job_id: string;
  status: "queued";
  text: string;
}
export interface ChatJob {
  id: string;
  conversation_id: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  detail: string;
  message_id: string | null;
  cancel_requested: boolean;
  created: number;
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
export interface ModelSource {
  id: string;
  label: string;
  kind: "ollama" | "folder";
}
export interface ModelInventory {
  inference_enabled: false;
  sources: {
    id: string;
    status: string;
    truncated: boolean;
    count: number;
    rejected_entries: number;
  }[];
  models: {
    id: string;
    source_id: string;
    name: string;
    size_bytes: number;
    format: string;
    status: string;
    inference_enabled: false;
  }[];
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

// Server-sent events for the inline answer. A reply that is not an event
// stream means streaming is unavailable, and the caller sends the ordinary
// request instead, so the waiting line keeps working unchanged.
export async function streamRequest(
  path: string,
  data: unknown,
): Promise<Response> {
  return fetch(`/api${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(data),
  });
}

export const isEventStream = (response: Response) =>
  response.ok &&
  !!response.body &&
  (response.headers.get("Content-Type") ?? "").includes("text/event-stream");

export async function* streamEvents(
  response: Response,
): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffered += done ? "" : decoder.decode(value, { stream: true });
    let border = buffered.indexOf("\n\n");
    while (border >= 0) {
      const block = buffered.slice(0, border);
      buffered = buffered.slice(border + 2);
      let event = "";
      let payload = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        if (line.startsWith("data: ")) payload = line.slice(6);
      }
      if (event && payload) {
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(payload) as Record<string, unknown>;
        } catch {
          data = {};
        }
        yield { event, data };
      }
      border = buffered.indexOf("\n\n");
    }
    if (done) return;
  }
}

export const json = (method: string, data?: unknown): RequestInit => ({
  method,
  ...(data === undefined ? {} : { body: JSON.stringify(data) }),
});
// Keys for client-side list state. crypto.randomUUID is SecureContext-only,
// so a plain-HTTP LAN deployment falls back to getRandomValues and finally to
// time plus a counter, without ever throwing.
let keyCounter = 0;
export function uniqueKey(): string {
  const c = globalThis.crypto;
  if (typeof c?.randomUUID === "function") return c.randomUUID();
  if (typeof c?.getRandomValues === "function") {
    const bytes = c.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // RFC 4122 version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex
      .slice(6, 8)
      .join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`;
  }
  return `key-${Date.now().toString(36)}-${(keyCounter++).toString(36)}`;
}
export const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "処理に失敗しました。再試行してください。";
export const statusName: Record<string, string> = {
  uploading: "送信中",
  queued: "解析待ち",
  scanning: "検査中",
  indexing: "索引中",
  ready: "参照可能",
  quarantined: "隔離中",
  failed: "失敗",
  cancelled: "取消済み",
};
// The stages the ingestion worker can still advance or the owner can cancel.
export const ingestionStages = ["queued", "scanning", "indexing"];
export const ingesting = (status: string) => ingestionStages.includes(status);
