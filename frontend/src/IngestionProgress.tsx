import type { Document } from "./api";
import { statusName } from "./api";

type ProgressDocument = Document & {
  stage?: string;
  failure_code?: string;
};

const stages = [
  "queued",
  "scanning",
  "indexing",
  "ready",
  "quarantined",
  "failed",
  "cancelled",
];

const stageLabels: Record<string, string> = {
  queued: statusName.queued,
  scanning: statusName.scanning,
  indexing: "索引中",
  done: "完了",
  failed: "失敗",
};

const failureLabels: Record<string, string> = {
  permission_revoked: "登録者の利用権限が失効",
  scanner_rejected: "安全検査で拒否",
  scanner_unavailable: "安全検査を実行できないため既定拒否",
  index_failed: "索引処理に失敗（再開待ち）",
  cancelled: "利用者が取消",
};

function stageOf(doc: ProgressDocument): string {
  if (doc.stage) return doc.stage;
  if (doc.status === "ready") return "done";
  if (["quarantined", "failed", "cancelled"].includes(doc.status)) {
    return "failed";
  }
  return doc.status;
}

function failureReason(doc: ProgressDocument): string {
  const code = doc.failure_code;
  if (code && failureLabels[code]) return failureLabels[code];
  return doc.reason || "理由不明";
}

export function IngestionProgress({
  documents,
  refresh = "waiting",
}: {
  documents: ProgressDocument[];
  refresh?: "waiting" | "updating" | "stopped";
}) {
  const unknown = documents.filter(
    (doc) => !stages.includes(doc.status),
  ).length;
  const pending = documents.some((doc) =>
    ["queued", "scanning", "indexing"].includes(doc.status),
  );
  const active = documents.filter((doc) =>
    ["queued", "scanning", "indexing"].includes(doc.status),
  );
  const incomplete = documents.filter((doc) =>
    ["quarantined", "failed", "cancelled"].includes(doc.status),
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
            <dt>
              {stage === "indexing" ? stageLabels.indexing : statusName[stage]}
            </dt>
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
      {active.length > 0 && (
        <div className="ingestion-active">
          <p className="muted">
            <strong>処理中</strong>
          </p>
          <ul>
            {active.map((doc) => (
              <li key={doc.id}>
                {doc.name}：{stageLabels[stageOf(doc)] ?? stageOf(doc)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {incomplete.length > 0 && (
        <div className="ingestion-incomplete">
          <p className="muted">
            <strong>完了しなかった資料</strong>
          </p>
          <ul>
            {incomplete.map((doc) => (
              <li key={doc.id}>
                {doc.name}：{failureReason(doc)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="footnote">
        {pending && refresh === "stopped"
          ? "自動更新は停止しています。件数は最後に取得した状態です。「更新」で確認してください。"
          : pending && refresh === "updating"
            ? "状態を確認中です。件数は最後に取得した状態です。"
            : pending
              ? "処理中は2秒ごとに状態を確認します。所要時間はまだ見積もれません。索引は完了済みの頁から再開できます。"
              : "参照可能な資料だけを検索に使います。隔離・失敗・取消済みは完了件数に含めません。"}
      </p>
    </section>
  );
}
