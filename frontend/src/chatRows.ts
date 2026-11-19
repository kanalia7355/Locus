import type { Citation, Message } from "./api";

// Display row kinds rendered by the chat screen today. Each message becomes a
// single exchange row: the user question plus its answer, sources and footnote.
// Kinds that no backend surface exists for yet (tool execution, turn phases)
// are deliberately not invented here.
export type ChatRowKind = "exchange";

export interface ChatRow {
  // Stable identity for React keys and row-level memoization. It is derived
  // from the message id alone, so an answer that moves from "unconfirmed" to
  // "confirmed" keeps the same row.
  key: string;
  kind: ChatRowKind;
  text: string;
  answer: string | null;
  model: string | null;
  answerHidden: boolean;
  citations: Citation[];
}

// Pure projection from the conversation message list to display rows. No side
// effects, no React, no Date.now(): the same input always yields the same rows.
export function chatRows(messages: Message[]): ChatRow[] {
  return messages.map((message) => {
    // A masked answer (for example after a permission loss) must not surface
    // its body, model or sources through the row; the renderer shows the
    // masking notice instead. The backend state itself is not fabricated here.
    const answerHidden = message.answer_hidden === true;
    return {
      key: message.id,
      kind: "exchange",
      text: message.text,
      answer: answerHidden ? null : (message.answer ?? null),
      model: answerHidden ? null : (message.model ?? null),
      answerHidden,
      citations: answerHidden ? [] : (message.citations ?? []),
    };
  });
}
