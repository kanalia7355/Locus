import { useCallback, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, errorText, json } from "./api";

// Shared :user-invalid ⇄ aria-invalid sync for the auth forms.
// It lives here (not in a new module) because this job's allowed paths do
// not include a shared file; both App.tsx and this file consume it.
//
// `:user-invalid` only matches after the user has interacted with the
// control (or tried to submit), so a pristine field never renders as
// invalid. Firefox and Safari publish an empty `required` control as
// invalid from page load, which is why every field also pins
// aria-invalid="false" as its initial value and why this sync decides via
// element.matches(":user-invalid") rather than the bare :invalid.
type FormControl = HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;

function isFormControl(element: EventTarget | null): element is FormControl {
  return (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement
  );
}

type Listeners = {
  node: HTMLFormElement;
  sync: (event: Event) => void;
  onInvalid: (event: Event) => void;
};

export function useUserInvalidForm() {
  const [invalidFields, setInvalidFields] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const listeners = useRef<Listeners | null>(null);

  const sync = useCallback((event: Event) => {
    if (!isFormControl(event.target)) return;
    const element = event.target;
    if (!element.id) return;
    const matches = element.matches(":user-invalid");
    setInvalidFields((previous) => {
      if (previous.has(element.id) === matches) return previous;
      const next = new Set(previous);
      if (matches) next.add(element.id);
      else next.delete(element.id);
      return next;
    });
  }, []);

  const onInvalid = useCallback(
    (event: Event) => {
      sync(event);
      // Native validation does not move focus in jsdom, and the spec only
      // guarantees the first failing control is submitted last anyway, so
      // find the first invalid control explicitly rather than trusting the
      // order of the invalid events. Note: validity.valid (unlike
      // checkValidity()) does not fire invalid events, so this stays safe
      // inside the invalid-event dispatch, which is limited to capture
      // listeners on the form.
      const form =
        event.target instanceof HTMLElement ? event.target.closest("form") : null;
      if (!form) return;
      for (const element of Array.from(form.elements)) {
        if (isFormControl(element) && !element.validity.valid) {
          element.focus();
          break;
        }
      }
    },
    [sync],
  );

  // Registered natively rather than through React props: React delegates
  // blur to the focusout event, so a React onBlur never observes a bare
  // blur dispatchment (e.g. testing-library's fireEvent.blur). Any number of
  // handlers can run for the same event — the state update is idempotent.
  const attachForm = useCallback(
    (node: HTMLFormElement | null) => {
      if (listeners.current) {
        const { node: old, sync: oldSync, onInvalid: oldInvalid } = listeners.current;
        old.removeEventListener("input", oldSync, true);
        old.removeEventListener("change", oldSync, true);
        old.removeEventListener("blur", oldSync, true);
        old.removeEventListener("invalid", oldInvalid, true);
        listeners.current = null;
      }
      if (node) {
        node.addEventListener("input", sync, true);
        node.addEventListener("change", sync, true);
        node.addEventListener("blur", sync, true);
        node.addEventListener("invalid", onInvalid, true);
        listeners.current = { node, sync, onInvalid };
      }
    },
    [sync, onInvalid],
  );

  const reset = useCallback(() => setInvalidFields(new Set()), []);

  return { invalidFields, reset, attachForm };
}

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
  const { invalidFields, reset, attachForm } = useUserInvalidForm();

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
      reset();
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
            reset();
          }}
        >
          {formOpen ? "入力を閉じる" : "追加"}
        </button>
      </div>
      {formOpen && (
        <form
          id="provision-user-form"
          className="provision-user-form"
          onSubmit={submit}
          ref={attachForm}
        >
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
              aria-invalid={invalidFields.has("provision-user-username")}
              aria-describedby={
                invalidFields.has("provision-user-username")
                  ? "provision-user-username-error"
                  : undefined
              }
            />
            <button type="submit" className="primary" disabled={pending}>
              {pending ? "作成中…" : "作成"}
            </button>
          </div>
          {invalidFields.has("provision-user-username") && (
            <p id="provision-user-username-error" className="field-error">
              利用者IDが未入力です。追加する利用者のID（1〜64文字）を入力してください。
            </p>
          )}
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
