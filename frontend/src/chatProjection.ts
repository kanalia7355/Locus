import type { Message } from "./api";

export interface ChatAttachment {
  key: string;
  name: string;
  status: string;
  id?: string;
  reason?: string;
}

export interface PendingChatJob {
  id: string;
  conversation: string;
  text: string;
  status: "queued" | "running";
  cancelRequested: boolean;
}

export interface ChatJobNotice {
  conversation: string;
  text: string;
  status: "done" | "failed" | "cancelled";
  detail?: string;
}

export type ChatTimelineRow =
  | { kind: "message"; key: string; message: Message }
  | {
      kind: "job";
      key: string;
      text: string;
      status: "queued" | "running" | "done" | "failed" | "cancelled";
      cancelRequested: boolean;
      detail?: string;
    };

export function projectChatRows(
  messages: Message[],
  pendingJob: PendingChatJob | null,
  terminalJob: ChatJobNotice | null,
  conversationId: string | null,
): ChatTimelineRow[] {
  const rows: ChatTimelineRow[] = messages.map((message) => ({
    kind: "message",
    key: message.id,
    message,
  }));

  if (terminalJob && terminalJob.conversation === conversationId) {
    rows.push({
      kind: "job",
      key: `job:${terminalJob.status}:${terminalJob.conversation}`,
      text: terminalJob.text,
      status: terminalJob.status,
      cancelRequested: false,
      detail: terminalJob.detail,
    });
  }

  if (pendingJob && pendingJob.conversation === conversationId) {
    rows.push({
      kind: "job",
      key: `job:${pendingJob.id}`,
      text: pendingJob.text,
      status: pendingJob.status,
      cancelRequested: pendingJob.cancelRequested,
    });
  }

  return rows;
}

/** Generate a stable attachment UI key on both secure and plain-HTTP origins. */
export function createAttachmentKey(): string {
  const cryptoApi = globalThis.crypto;
  if (typeof cryptoApi?.randomUUID === "function")
    return cryptoApi.randomUUID();

  const bytes = new Uint8Array(16);
  if (typeof cryptoApi?.getRandomValues === "function") {
    cryptoApi.getRandomValues(bytes);
  } else {
    // Attachment keys are not security credentials; this last-resort fallback
    // exists only for browsers without Web Crypto in an insecure LAN context.
    for (let index = 0; index < bytes.length; index++)
      bytes[index] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex
    .slice(6, 8)
    .join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}
