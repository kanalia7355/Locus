import { useEffect, useRef, useState } from "react";
import { api, errorText } from "./api";
import type { RelatedDocument } from "./api";

export function RelatedDocuments({
  documentId,
  conversationId,
  onOpen,
}: {
  documentId: string;
  conversationId: string | null;
  onOpen: (id: string) => Promise<void>;
}) {
  const [items, setItems] = useState<RelatedDocument[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function load() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setItems(null);
    setError("");
    try {
      const query = conversationId
        ? `?conversation_id=${encodeURIComponent(conversationId)}`
        : "";
      const result = await api<RelatedDocument[]>(
        `/documents/${encodeURIComponent(documentId)}/related${query}`,
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) setItems(result);
    } catch (error) {
      if (!controller.signal.aborted) setError(errorText(error));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  return (
    <section className="related-documents" aria-label="関連資料">
      <button
        aria-disabled={loading}
        onClick={() => {
          if (!loading) void load();
        }}
      >
        {loading ? "関連資料を確認中" : "関連資料を確認"}
      </button>
      <p className="muted">
        共通語句による関連です。意味上の関係や研究上の結論を示すものではありません。
      </p>
      {error && <p role="alert">{error}</p>}
      {items && items.length === 0 && (
        <p role="status">現在参照できる関連資料はありません。</p>
      )}
      {items && items.length > 0 && (
        <ul>
          {items.map((item) => (
            <li key={item.document.id}>
              <button onClick={() => void onOpen(item.document.id)}>
                {item.document.name}
              </button>
              <p>共通語句 {item.shared_term_count}件</p>
              <ul>
                {item.evidence.map((evidence) => (
                  <li key={evidence.term}>
                    「{evidence.term}」 · この資料 p.{evidence.source_page} →
                    関連資料 p.{evidence.target_page}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
