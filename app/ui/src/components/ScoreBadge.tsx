function severityFor(score: number) {
  if (score >= 75) return { label: "High", classes: "bg-severity-high/15 text-severity-high border-severity-high/40" };
  if (score >= 50) return { label: "Elevated", classes: "bg-severity-mid/15 text-severity-mid border-severity-mid/40" };
  return { label: "Low", classes: "bg-severity-low/15 text-severity-low border-severity-low/40" };
}

interface ScoreBadgeProps {
  score: number;
  size?: "md" | "lg";
}

export default function ScoreBadge({ score, size = "md" }: ScoreBadgeProps) {
  const { label, classes } = severityFor(score);
  const sizeClasses = size === "lg" ? "text-base px-3 py-1.5" : "text-xs px-2 py-1";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border font-mono font-semibold ${sizeClasses} ${classes}`}
      title={`Opportunity/distress score: ${score} (${label})`}
    >
      {score}
      <span className="font-sans font-medium opacity-80">{label}</span>
    </span>
  );
}
