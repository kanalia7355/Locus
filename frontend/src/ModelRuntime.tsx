import { useRef, useEffect, useState } from "react";
import { api, errorText, json } from "./api";

export function ModelRuntime({ candidate }: { candidate: string | null }) {
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  async function save(enable: boolean) {
    setBusy(true);
    setStatus("");
    try {
      const result = await api<{ enabled: boolean; model: string | null }>(
        "/admin/models/runtime",
        json("PUT", {
          candidate_id: enable ? candidate : null,
          local_only_confirmed: enable && confirmed,
        }),
      );
      if (alive.current)
        setStatus(
          result.enabled
            ? `${result.model} を使用します。生成回答は出典とともに保存されます。`
            : "原文検索に戻しました。",
        );
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
        生成回答を保存します。出典の権限が失われた回答は非表示になります。設定はサーバー再起動で無効になります。
      </p>
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          disabled={busy}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Ollamaのクラウド機能を無効化し、ローカル専用であることを確認しました
      </label>
      <button
        disabled={busy || !candidate || !confirmed}
        onClick={() => void save(true)}
      >
        選択モデルをチャットに使用
      </button>
      <button disabled={busy} onClick={() => void save(false)}>
        原文検索に戻す
      </button>
      {status && <p role="status">{status}</p>}
    </section>
  );
}
