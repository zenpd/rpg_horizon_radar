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

  if (locked) {
    return (
      <span className="chip-locked inline-flex items-center gap-1.5" title="Awaiting Compliance sign-off">
        <Lock size={12} />
        {name}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "chip-open inline-flex items-center gap-1.5"
          : "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold bg-gray-50 text-slate-600 ring-1 ring-gray-200 hover:ring-zen-200 hover:text-zen-600 transition-colors"
      }
    >
      {code}
    </button>
  );
}
