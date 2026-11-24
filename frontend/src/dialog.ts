export function dialogControls(dialog: HTMLDialogElement | null): HTMLElement[] {
  if (!dialog) return [];
  return Array.from(
    dialog.querySelectorAll<HTMLElement>(
      'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter(
    (control) =>
      !control.classList.contains("focus-guard") &&
      control.getClientRects().length > 0,
  );
}
