import { useState } from "react";
import type { FormEvent } from "react";
import { api, errorText, json } from "./api";

type ProvisionedUser = {
  id: string;
  username: string;
  temporary_password: string;
  must_rotate: boolean;
};

export function ProvisionUser({ onCreated }: { onCreated: () => void }) {
  const [formOpen, setFormOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      const created = await api<ProvisionedUser>(
        "/admin/users",
        json("POST", { username }),
      );
      setUsername("");
      setFormOpen(false);
      setTemporaryPassword(created.temporary_password);
      setCopyNotice("");
      onCreated();
    } catch (submitError) {
      setError(errorText(submitError));
    } finally {
      setPending(false);
    }
  }

  async function copyPassword() {
    if (!temporaryPassword) return;
    try {
      await navigator.clipboard.writeText(temporaryPassword);
      setCopyNotice("コピーしました。");
    } catch {
      setCopyNotice("コピーできませんでした。パスワードを選択してコピーしてください。");
    }
  }

  return (
    <section className="provision-user" aria-labelledby="provision-user-heading">
      <div className="section-toolbar">
        <h2 id="provision-user-heading">利用者の追加</h2>
        <button
          type="button"
          aria-expanded={formOpen}
          aria-controls="provision-user-form"
          onClick={() => {
            setFormOpen((open) => !open);
            setError("");
          }}
        >
          {formOpen ? "入力を閉じる" : "追加"}
        </button>
      </div>
      {formOpen && (
        <form id="provision-user-form" className="provision-user-form" onSubmit={submit}>
          <label htmlFor="provision-user-username">利用者ID</label>
          <div className="provision-user-controls">
            <input
              id="provision-user-username"
              name="username"
              autoComplete="off"
              maxLength={64}
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "provision-user-error" : undefined}
            />
            <button type="submit" className="primary" disabled={pending}>
              {pending ? "作成中…" : "作成"}
            </button>
          </div>
          {error && (
            <p id="provision-user-error" role="alert" className="error">
              {error}
            </p>
          )}
        </form>
      )}
      {temporaryPassword && (
        <div
          className="one-time-password"
          role="region"
          aria-label="一度だけ表示される仮パスワード"
        >
          <p>
            <strong>一度だけ表示されます。</strong>
            画面を更新すると再表示できません。利用者へ安全に伝えてください。
          </p>
          <div className="provision-user-controls">
            <code aria-label="仮パスワード">{temporaryPassword}</code>
            <button type="button" onClick={() => void copyPassword()}>
              コピー
            </button>
            <button
              type="button"
              onClick={() => {
                setTemporaryPassword(null);
                setCopyNotice("");
              }}
            >
              閉じる
            </button>
          </div>
          {copyNotice && (
            <p className="muted" aria-live="polite">
              {copyNotice}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
