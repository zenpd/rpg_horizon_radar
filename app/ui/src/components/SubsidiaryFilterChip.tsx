import { Lock } from "lucide-react";

import type { Subsidiary } from "../types";

interface SubsidiaryFilterChipProps {
  subsidiary: Subsidiary;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}

export default function SubsidiaryFilterChip({
  subsidiary,
  active,
  disabled,
  onClick,
}: SubsidiaryFilterChipProps) {
  const { code, name, compliance_gate: gated } = subsidiary;
  const locked = disabled || !gated;

  const base =
    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors";

  if (locked) {
    return (
      <span
        className={`${base} border-ink-600 bg-ink-800 text-ink-500 cursor-not-allowed`}
        title="Awaiting Compliance sign-off"
      >
        <Lock size={12} />
        {name}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={`${base} ${
        active
          ? "border-accent bg-accent/15 text-accent-light"
          : "border-ink-600 bg-ink-800 text-ink-500 hover:border-accent/50 hover:text-ink-100"
      }`}
    >
      {code}
    </button>
  );
}
