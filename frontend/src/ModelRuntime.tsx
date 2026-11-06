import { useRef, useEffect, useState } from "react";
import { api, errorText, json } from "./api";

interface RuntimeState {
  enabled: boolean;
  model: string | null;
}

export function ModelRuntime({ candidate }: { candidate: string | null }) {
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [current, setCurrent] = useState<RuntimeState | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    void api<RuntimeState>("/admin/models/runtime", {
      signal: controller.signal,
    })
      .then((value) => {
        if (!controller.signal.aborted) setCurrent(value);
      })
      .catch((error) => {
        if (!controller.signal.aborted) setStatus(errorText(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
  }, []);
  async function save(enable: boolean) {
    setBusy(true);
    setStatus("");
    setCurrent(null);
    try {
      const result = await api<RuntimeState>(
        "/admin/models/runtime",
        json("PUT", {
          candidate_id: enable ? candidate : null,
          local_only_confirmed: enable && confirmed,
        }),
      );
      if (alive.current) {
        setCurrent(result);
        setStatus(
          result.enabled
            ? `${result.model} を使用します。生成回答は出典とともに保存されます。`
            : "原文検索に戻しました。",
        );
      }
    } catch (error) {
      if (alive.current) setStatus(errorText(error));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <section aria-label="モデルの実行設定">
      <h3>チャットで使用するモデル</h3>
      <p>
        {loading
          ? "現在の設定を確認中です。"
          : current
            ? current.enabled
              ? `現在：${current.model} による生成`
              : "現在：原文検索"
            : "現在の設定を確認できません。"}
      </p>
      <p>
        生成回答を保存します。出典の権限が失われた回答は非表示になります。設定はサーバー再起動で無効になります。
      </p>
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy || loading}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Ollamaのクラウド機能を無効化し、ローカル専用であることを確認しました
      </label>
      <button
        disabled={busy || loading || !current || !candidate || !confirmed}
        onClick={() => void save(true)}
      >
        選択モデルをチャットに使用
      </button>
      <button disabled={busy || loading} onClick={() => void save(false)}>
        原文検索に戻す
      </button>
      {status && <p role="status">{status}</p>}
    </section>
  );
}
