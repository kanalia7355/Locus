import { useState } from "react";
import type { RelatedDocument } from "./api";

/** A display of fetched lexical edges, not a semantic or persistent graph. */
export function ProvenanceDiagram({ items }: { items: RelatedDocument[] }) {
  const [expanded, setExpanded] = useState(false);
  const shown = items.slice(0, 10);
  const height = Math.max(120, shown.length * 72 + 24);
  const center = height / 2;
  if (!shown.length) return null;
  return (
    <div className="provenance-diagram">
      <button
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? "資料の関係図を閉じる" : "資料の関係図を表示"}
      </button>
      {expanded && (
        <>
          <p className="muted">
            表示中の資料と共通語句を持つ資料の関係図です。資料間の意味や因果関係を示しません。元資料は下の一覧から開けます。
          </p>
          <div
            className="provenance-viewport"
            role="region"
            aria-label="資料の関係図のスクロール領域"
            tabIndex={0}
          >
            <svg
              role="img"
              aria-label={`共通語句による資料の関係図：表示中の資料と関連資料${shown.length}件`}
              viewBox={`0 0 640 ${height}`}
            >
              <g aria-hidden="true">
                {shown.map((item, index) => {
                  const y = 48 + index * 72;
                  return (
                    <g key={item.document.id}>
                      <path
                        d={`M 155 ${center} C 200 ${center}, 200 ${y}, 255 ${y}`}
                      />
                      <rect x="255" y={y - 25} width="375" height="50" rx="4" />
                      <text x="267" y={y - 3}>
                        {Array.from(item.document.name).slice(0, 23).join("")}
                        {Array.from(item.document.name).length > 23 ? "…" : ""}
                      </text>
                      <text className="provenance-count" x="267" y={y + 15}>
                        共通語句 {item.shared_term_count}件
                      </text>
                    </g>
                  );
                })}
                <rect x="10" y={center - 23} width="145" height="46" rx="4" />
                <text x="22" y={center + 5}>
                  表示中の資料
                </text>
              </g>
            </svg>
          </div>
        </>
      )}
    </div>
  );
}
