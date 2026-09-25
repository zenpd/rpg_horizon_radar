interface ScoreBadgeProps {
  score: number;
  size?: "md" | "lg";
}

function bandFor(score: number): { label: string; cls: string } {
  if (score >= 75) return { label: "High", cls: "score-high" };
  if (score >= 50) return { label: "Elevated", cls: "score-elevated" };
  return { label: "Low", cls: "score-low" };
}

export default function ScoreBadge({ score, size = "md" }: ScoreBadgeProps) {
  const { label, cls } = bandFor(score);
  const sizeCls = size === "lg" ? "text-sm px-3 py-1" : "";
  return (
    <span className={`${cls} ${sizeCls} font-mono`} title={`Opportunity/distress score: ${score} (${label})`}>
      {score}
      <span className="font-sans font-semibold opacity-80">{label}</span>
    </span>
  );
}
