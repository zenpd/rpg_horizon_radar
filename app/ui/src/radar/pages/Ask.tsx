import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type ChatMessage, type ChatSource, type ChatThread } from "../api";
import { useApp } from "../state";

const SUGGESTIONS = (co: string) => [
  `Which companies could ${co} acquire right now?`,
  `What are ${co}'s biggest weaknesses?`,
  `Who are ${co}'s main competitors and what are they doing?`,
  "How is the opportunity score calculated?",
];

/** A line of the answer with **bold** and [R1] / [W2] citations as links to that answer's sources. */
function inline(text: string, msgId: number): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\[(?:R|W)\d{1,3}\])/g).filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <b key={i}>{part.slice(2, -2)}</b>;
    const m = part.match(/^\[((?:R|W)\d{1,3})\]$/);
    if (m) return <sup key={i}><a href={`#src-${msgId}-${m[1]}`} title={m[1].startsWith("W") ? "Web source" : "Radar data"}>[{m[1]}]</a></sup>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/** The answer's light markdown: paragraphs and bullet lists. */
function Answer({ m }: { m: ChatMessage }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => { if (list.length) { blocks.push(<ul key={blocks.length}>{list.map((l, i) => <li key={i}>{inline(l, m.id)}</li>)}</ul>); list = []; } };
  for (const line of m.content.split("\n")) {
    const b = line.match(/^\s*[-*•]\s+(.*)$/);
    if (b) { list.push(b[1]); continue; }
    flush();
    if (line.trim()) blocks.push(<p key={blocks.length} style={{ margin: "4px 0" }}>{inline(line, m.id)}</p>);
  }
  flush();
  return <>{blocks}</>;
}

function Sources({ m }: { m: ChatMessage }) {
  if (!m.sources.length) return null;
  return (
    <details className="chat-src">
      <summary>{m.sources.length} source{m.sources.length === 1 ? "" : "s"}{m.used_web ? " · searched the web" : " · from the radar"}</summary>
      <ol>{m.sources.map((s: ChatSource) => (
        <li key={s.id} id={`src-${m.id}-${s.id}`}>
          <span className={`pill2 ${s.kind === "web" ? "src-web" : "src-radar"}`}>{s.id}</span>{" "}
          {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.text}</a> : s.text}
          <span className="sub"> · {s.source}{s.date ? ` · ${s.date}` : ""}</span>
        </li>
      ))}</ol>
    </details>
  );
}

/* ---------------- Ask Radar: a chat over the radar's data and the web, conversations saved per user ---------------- */
export function AskRadar() {
  const app = useApp();
  const co = app.scope;
  const [threads, setThreads] = useState<ChatThread[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const scroll = () => setTimeout(() => endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" }), 50);

  const loadThreads = () => api.chats().then(setThreads).catch((e) => app.toast(e.message));
  useEffect(() => { loadThreads(); }, []);
  useEffect(() => {
    if (open === null) { setMsgs([]); return; }
    api.chat(open).then((t) => { setMsgs(t.messages); scroll(); }).catch((e) => app.toast(e.message));
  }, [open]);

  const send = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    setBusy(true);
    setText("");
    try {
      const id = open ?? (await api.newChat(co)).id;
      if (open === null) setOpen(id);
      setMsgs((m) => [...m, { id: -Date.now(), role: "user", content: question, company: co, sources: [], used_web: false, model: "", created_at: "" }]);
      scroll();
      const r = await api.sendChat(id, question, co);
      setMsgs((m) => [...m.filter((x) => x.id > 0), r.question, r.answer]);
      if (r.errors.length) app.toast(`Some searches failed: ${r.errors[0]}`);
      loadThreads();
      scroll();
    } catch (e) {
      app.toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = (id: number) => api.deleteChat(id).then(() => { if (open === id) setOpen(null); loadThreads(); }).catch((e) => app.toast(e.message));

  return (
    <div className="ask-wrap">
      <aside className="panel ask-threads">
        <button className="btnx pri" style={{ width: "100%" }} onClick={() => setOpen(null)}>+ New conversation</button>
        <h5 style={{ margin: "12px 0 6px" }}>Your conversations</h5>
        <p className="sub" style={{ fontSize: 11.5, marginTop: 0 }}>Private to you: other users cannot see them.</p>
        {!threads ? <p className="sub">Loading…</p> : threads.length ? threads.map((t) => (
          <div key={t.id} className={`ask-thread${t.id === open ? " on" : ""}`}>
            <button type="button" onClick={() => setOpen(t.id)} title={t.title}>
              <span>{t.title}</span><small>{t.company === "All" ? "All companies" : t.company} · {new Date(t.updated_at + "Z").toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}</small>
            </button>
            <button type="button" className="info-x" aria-label={`Delete ${t.title}`} onClick={() => remove(t.id)}>×</button>
          </div>
        )) : <p className="sub" style={{ fontSize: 12.5 }}>None yet.</p>}
      </aside>

      <div className="chat ask-main">
        <div className="top" style={{ gap: 8 }}>
          <span className="crumb"><b>Radar</b> / Ask Radar</span><span style={{ flex: 1 }} />
          <span className="pill">Asking about: {co === "All" ? "all companies" : co}</span>
        </div>
        {!msgs.length && (
          <div style={{ marginTop: 8 }}>
            <p className="sub">Ask anything about {co === "All" ? "the RPG companies" : co}, the companies it watches, its M&A signals, SWOT or finances. Ask Radar checks the radar's own data first and searches the web when that does not answer it. Every answer cites its sources.</p>
            <div className="src">{SUGGESTIONS(co === "All" ? "CEAT" : co).map((s) => <button key={s} type="button" className="askSug" onClick={() => send(s)}><span>→</span><span>{s}</span></button>)}</div>
          </div>
        )}
        {msgs.map((m) => m.role === "user"
          ? <div key={m.id} className="q">{m.content}</div>
          : <div key={m.id} className="a">
              <Answer m={m} />
              <Sources m={m} />
              {m.model && <span className="sub" style={{ fontSize: 11.5 }}>Ask Radar ({m.model}) · public information only · check the sources before acting</span>}
            </div>)}
        {busy && <div className="a typing"><span className="sub">Checking the radar's data, and the web if needed…</span></div>}
        <div ref={endRef} />
        <form className="prompt" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input type="text" placeholder={`Ask about ${co === "All" ? "the RPG companies" : co}…`} autoComplete="off" value={text} onChange={(e) => setText(e.target.value)} disabled={busy} />
          <button type="submit" className="rbtn" disabled={busy || !text.trim()}>Send</button>
        </form>
      </div>
    </div>
  );
}
