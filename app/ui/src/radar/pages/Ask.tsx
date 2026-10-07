import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp } from "../state";

function ScopeNote() {
  const app = useApp();
  return app.scope === "All" ? <div><span className="scope-note">Showing {app.cur} — pick a company above to change</span></div> : null;
}

/* ---------------- Ask Radar ---------------- */
type Turn = { question: string; lead?: string; points?: [string, number][]; meaning?: string; confidence?: number; sources?: string[]; fallback?: boolean; suggestions?: string[]; generated_by?: string };

export function AskRadar() {
  const app = useApp();
  const co = app.cur;
  const [threads, setThreads] = useState<Record<string, Turn[]>>({});
  const [sugg, setSugg] = useState<string[]>([]);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { api.askStart(co).then((r) => setSugg(r.suggestions)); }, [co]);
  const list = threads[co] || [];
  const ask = async (q: string) => {
    if (!q.trim()) return;
    const a = await api.ask(co, q.trim());
    setThreads((t) => ({ ...t, [co]: [...(t[co] || []), a] }));
    setTimeout(() => endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" }), 50);
  };
  const src = [...list].reverse().find((t) => !t.fallback)?.sources || [];
  return (
    <div className="cols">
      <div className="chat">
        <div className="top" style={{ gap: 8 }}>
          <span className="crumb"><b>{co}</b> / Ask Radar</span><span style={{ flex: 1 }} />
          <span className="pill">Scope: {co}</span><span className="lock">Answers from public signals only</span>
        </div>
        <ScopeNote />
        {!list.length && <p className="sub">Ask about the companies {co} watches, their recent signals, or how scores work. Every answer cites its sources.</p>}
        {list.map((t, i) => (
          <div key={i} style={{ display: "contents" }}>
            <div className="q">{t.question}</div>
            {t.fallback ? (
              <div className="a fallback">
                <p style={{ margin: 0 }}>I don't have a confident answer for that from the signals the radar holds. Here's what I can tell you about:</p>
                <div className="src" style={{ marginTop: 6 }}>{(t.suggestions || sugg).map((s) => <button key={s} type="button" className="askSug" onClick={() => ask(s)}><span>→</span><span>{s}</span></button>)}</div>
              </div>
            ) : (
              <div className="a">
                <p style={{ margin: 0 }}>{t.lead}</p>
                <ul>{t.points!.map((p, j) => <li key={j}>{p[0]}<sup>[{p[1]}]</sup></li>)}</ul>
                <p style={{ margin: 0 }}><b>What it means for {co}:</b> {t.meaning}</p>
                {t.generated_by
                  ? <span className="sub" style={{ fontSize: 12 }}>Drafted by {t.generated_by} from the radar's evidence · not fact-checked · {t.confidence}% confidence</span>
                  : (t.sources?.length ?? 0) >= 2
                    ? <span className="verified">✓ From {t.sources!.length} sources · {t.confidence}% confidence</span>
                    : <span className="sub" style={{ fontSize: 12 }}>From one source · {t.confidence}% confidence</span>}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
        <form className="prompt" onSubmit={(e) => { e.preventDefault(); ask(text); setText(""); }}>
          <input type="text" id="askInput" placeholder={`Ask about ${co}'s watched companies…`} autoComplete="off" value={text} onChange={(e) => setText(e.target.value)} />
          <button type="submit" className="rbtn" id="askSend">Send</button>
        </form>
      </div>
      <div className="panel">
        <h5>Sources</h5><div className="src">{src.length ? src.map((s, i) => <div key={i}><span>[{i + 1}]</span><p style={{ margin: 0 }}>{s}</p></div>) : <p className="sub" style={{ margin: 0 }}>None yet.</p>}</div>
        <h5 style={{ marginTop: 14 }}>Try asking</h5>
        <div className="src">{sugg.map((s) => <button key={s} type="button" className="askSug" onClick={() => ask(s)}><span>→</span><span>{s}</span></button>)}</div>
      </div>
    </div>
  );
}
