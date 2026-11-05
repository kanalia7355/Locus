import { useEffect, useRef, useState } from "react";
import { api, errorText, json } from "./api";
import type { ModelInventory, ModelSource } from "./api";

export function ModelSettings() {
  const [sources, setSources] = useState<ModelSource[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<ModelInventory | null>(null);
  const [candidate, setCandidate] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void api<ModelSource[]>("/admin/models/sources", {
      signal: controller.signal,
    })
      .then((value) => {
        if (!controller.signal.aborted) setSources(value);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setError(errorText(error));
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, []);

  async function discover() {
    if (busy || !selected.length) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    setResult(null);
    setCandidate(null);
    try {
      const value = await api<ModelInventory>("/admin/models/discover", {
        ...json("POST", { sources: selected }),
        signal: controller.signal,
      });
      if (!controller.signal.aborted) setResult(value);
    } catch (error) {
      if (!controller.signal.aborted) setError(errorText(error));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="model-catalog" aria-label="ローカルモデルの検出">
      <h2>ローカルモデルの候補</h2>
      <p>
        検出するのはLocusサーバー上のモデルです。選択した場所の名前・サイズだけを確認します。
      </p>
      <p className="muted">
        ダウンロード・取り込み・推論は行いません。追加フォルダーの登録はサーバー側で行います。
      </p>
      <fieldset disabled={busy}>
        <legend>検出する場所</legend>
        {sources.map((source) => (
          <label key={source.id}>
            <input
              type="checkbox"
              checked={selected.includes(source.id)}
              onChange={() => {
                setSelected((items) =>
                  items.includes(source.id)
                    ? items.filter((id) => id !== source.id)
                    : [...items, source.id],
                );
              }}
            />
            {source.label}
          </label>
        ))}
      </fieldset>
      <button
        disabled={busy || !selected.length}
        onClick={() => void discover()}
      >
        {busy ? "モデルを検出中" : "選択した場所でモデルを検出"}
      </button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <p role="status">
            {result.models.length}件のモデル候補を検出しました。
            {result.sources.some((source) => source.status !== "complete")
              ? "一部の場所・項目は未確認です。"
              : "検出対象の確認が完了しました。"}
          </p>
          <ul>
            {result.sources.map((source) => (
              <li key={source.id}>
                {sources.find((item) => item.id === source.id)?.label}：
                {source.status === "complete"
                  ? "確認済み"
                  : source.status === "unavailable"
                    ? "利用できません"
                    : "一部のみ確認"}
              </li>
            ))}
          </ul>
          {result.models.map((model) => (
            <article className="model-candidate" key={model.id}>
              <h3>{model.name}</h3>
              <p>
                {model.format} · 検出サイズ{" "}
                {model.size_bytes.toLocaleString("ja-JP")} B
              </p>
              <p className="muted">
                {model.status.startsWith("registered")
                  ? "Ollama登録済み。実行環境の確認が必要です。"
                  : "モデルファイルの候補です。取り込み・形式の確認が必要です。"}
              </p>
              <button
                aria-pressed={candidate === model.id}
                onClick={() => setCandidate(model.id)}
              >
                候補として選択
              </button>
              {candidate === model.id && (
                <p>
                  「{model.name}
                  」を候補として選択中です。推論はまだ有効ではありません。
                </p>
              )}
            </article>
          ))}
        </>
      )}
    </section>
  );
}
