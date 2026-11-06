import type { Document } from "./api";
import { statusName } from "./api";

const stages = [
  "queued",
  "scanning",
  "ready",
  "quarantined",
  "failed",
  "cancelled",
];

export function IngestionProgress({
  documents,
  refresh = "waiting",
}: {
  documents: Document[];
  refresh?: "waiting" | "updating" | "stopped";
}) {
  const unknown = documents.filter(
    (doc) => !stages.includes(doc.status),
  ).length;
  const pending = documents.some((doc) =>
    ["queued", "scanning"].includes(doc.status),
  );
  return (
    <section className="ingestion-progress" aria-label="表示中の資料の処理状況">
      <h2>表示中の資料：{documents.length}件</h2>
      <p className="muted">
        現在のプロジェクトで閲覧を許可された資料のみの集計です。サーバー全体の件数ではありません。
      </p>
      <dl>
        {stages.map((stage) => (
          <div key={stage}>
            <dt>{statusName[stage]}</dt>
            <dd>{documents.filter((doc) => doc.status === stage).length}件</dd>
          </div>
        ))}
        {unknown > 0 && (
          <div>
            <dt>状態不明</dt>
            <dd>{unknown}件</dd>
          </div>
        )}
      </dl>
      <p className="footnote">
        {pending && refresh === "stopped"
          ? "自動更新は停止しています。件数は最後に取得した状態です。「更新」で確認してください。"
          : pending && refresh === "updating"
            ? "状態を確認中です。件数は最後に取得した状態です。"
            : pending
              ? "処理中は2秒ごとに状態を確認します。所要時間はまだ見積もれません。"
              : "参照可能な資料だけを検索に使います。隔離・失敗・取消済みは完了件数に含めません。"}
      </p>
    </section>
  );
}
