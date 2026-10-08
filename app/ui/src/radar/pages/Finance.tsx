import { useEffect, useState } from "react";
import { api, type Market, type MarketRow, type SignalJob } from "../api";
import { QuarterlyResults } from "../components/charts";
import { useApp } from "../state";

const PALETTE = ["var(--watch)", "var(--high)", "var(--crit)", "var(--opp)", "#8B5CF6", "#0EA5E9", "#D946EF", "#64748B"];
const pct = (v: number | null | undefined, signed = true) => v === null || v === undefined ? "—" : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
const cr = (v: number | null | undefined) => v === null || v === undefined ? "—" : `₹${Math.round(v).toLocaleString("en-IN")} cr`;
const ZONE: Record<string, string> = { safe: "fit-strong", grey: "fit-moderate", distress: "fit-weak" };
const tone = (v: number | null | undefined) => v === null || v === undefined ? "" : v > 0 ? "up" : v < 0 ? "down" : "";

/** Lines on one chart, each a list of [x label, value]; the company's own line drawn thicker. */
function LineChart({ title, sub, series, xs, unit, base }: {
  title: string; sub: string; xs: string[]; unit: string; base?: number;
  series: { name: string; own: boolean; color: string; values: (number | null)[] }[];
}) {
  const W = 680, H = 280, L = 48, R = 664, T = 14, B = 248;
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  if (!all.length || xs.length < 2) return null;
  let lo = Math.min(...all, base ?? Infinity), hi = Math.max(...all, base ?? -Infinity);
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const X = (i: number) => L + ((R - L) * i) / (xs.length - 1), Y = (v: number) => B - ((B - T) * (v - lo)) / (hi - lo);
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4);
  const every = Math.max(1, Math.ceil(xs.length / 6));
  return (
    <div className="panel">
      <h5 style={{ margin: 0 }}>{title}</h5>
      <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 8px" }}>{sub}</p>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={title}>
        {ticks.map((t) => <g key={t}><line x1={L} x2={R} y1={Y(t)} y2={Y(t)} stroke="var(--rule)" /><text x={L - 6} y={Y(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--faint)">{t.toFixed(0)}{unit}</text></g>)}
        {base !== undefined && <line x1={L} x2={R} y1={Y(base)} y2={Y(base)} stroke="var(--muted)" strokeDasharray="4 3" />}
        {xs.map((x, i) => i % every === 0 || i === xs.length - 1 ? <text key={x + i} x={X(i)} y={B + 16} textAnchor="middle" fontSize="10.5" fill="var(--faint)">{x}</text> : null)}
        {[...series].sort((a, b) => Number(a.own) - Number(b.own)).map((s) => {
          const d = s.values.map((v, i) => (v === null ? null : `${X(i)},${Y(v)}`)).filter(Boolean);
          return d.length > 1 ? <polyline key={s.name} points={d.join(" ")} fill="none" stroke={s.color} strokeWidth={s.own ? 3 : 1.5} opacity={s.own ? 1 : 0.85}><title>{s.name}</title></polyline> : null;
        })}
      </svg>
      <div className="plegend" style={{ flexWrap: "wrap", gap: "4px 14px" }}>
        {series.map((s) => <span key={s.name}><svg width="18" height="10" aria-hidden="true"><line x1="0" x2="18" y1="5" y2="5" stroke={s.color} strokeWidth={s.own ? 3 : 2} /></svg>{s.own ? <b>{s.name}</b> : s.name}</span>)}
      </div>
    </div>
  );
}

function priceChart(rows: MarketRow[]) {
  // indexed to 100 on the first day all shown companies have a price, on the own company's (or the longest) dates
  const withPx = rows.filter((r) => r.prices && r.prices.length > 1);
  if (!withPx.length) return null;
  const axis = (withPx.find((r) => r.own) || withPx.reduce((a, b) => (b.prices!.length > a.prices!.length ? b : a))).prices!.map((p) => p[0]);
  const series = withPx.map((r, i) => {
    const m = new Map(r.prices!.map(([d, c]) => [d, c]));
    const first = axis.map((d) => m.get(d)).find((v) => v !== undefined);
    return { name: r.name, own: r.own, color: r.own ? "var(--accent)" : PALETTE[i % PALETTE.length], values: axis.map((d) => (m.has(d) && first ? (m.get(d)! / first) * 100 : null)) };
  });
  const fmt = (d: string) => new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  return { xs: axis.map(fmt), series };
}

function marginChart(rows: MarketRow[]) {
  const withQ = rows.filter((r) => r.opm_series && r.opm_series.length > 1 && r.quarters);
  if (!withQ.length) return null;
  const axis = (withQ.find((r) => r.own) || withQ[0]).quarters!;
  const series = withQ.map((r, i) => {
    const m = new Map(r.quarters!.map((q, j) => [q, r.opm_series![j]]));
    return { name: r.name, own: r.own, color: r.own ? "var(--accent)" : PALETTE[i % PALETTE.length], values: axis.map((q) => m.get(q) ?? null) };
  });
  return { xs: axis, series };
}

/** Self reflection → The financial market: the company's results, shareholding and share price against its listed watched companies'. */
export default function Finance() {
  const app = useApp();
  const co = app.cur;
  const [d, setD] = useState<Market | null>(null);
  const [job, setJob] = useState<SignalJob | null>(null);
  const load = () => api.market(co).then(setD).catch((e) => app.toast(e.message));
  useEffect(() => { load(); }, [co, app.version]);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setTimeout(() => api.marketJob(job.id).then((j) => {
      setJob(j);
      if (j.status !== "running") { load(); app.toast(j.status === "completed" ? "Market figures refreshed." : j.error || "The refresh failed"); }
    }).catch((e) => app.toast(e.message)), 2500);
    return () => clearTimeout(t);
  }, [job]);

  if (!d) return <p className="sub">Loading…</p>;
  const rows = [d.own, ...d.peers];
  const px = priceChart(rows), opm = marginChart(rows);
  const o = d.own, running = job?.status === "running";
  const used = (k: "Fincrux" | "Alpha Vantage", limit: number) => {
    const b = d.budget[k];
    return b && b.date === new Date().toISOString().slice(0, 10) ? `${b.used} of ${limit}` : `0 of ${limit}`;
  };

  return (
    <>
      <div>
        <span className="crumb"><b>Self reflection</b> / The financial market · {co}</span>
        <h4>{co}'s finances and share price against its competitors</h4>
        <p className="sub">Quarterly results and shareholding (Fincrux), daily BSE closing prices (Alpha Vantage) and market cap, for {co} and its listed watched companies. Rule-based, no AI.
          {app.scope === "All" && <> Showing {co} — pick a company above to change.</>}</p>
      </div>
      <div className="btnrow" style={{ alignItems: "center" }}>
        <button className="btnx" disabled={running} onClick={() => api.marketRefresh(co).then(setJob).catch((e) => app.toast(e.message))}>{running ? "Fetching figures…" : "Fetch missing figures"}</button>
        <span className="sub" style={{ fontSize: 12 }}>Calls used today: Alpha Vantage {used("Alpha Vantage", 25)}, Fincrux {used("Fincrux", 5)}. {co}'s own figures refresh daily after the news run; its competitors' with their news checks.</span>
      </div>

      {!d.listed ? (
        <div className="callout" style={{ marginTop: 12 }}><b>{co} is not listed</b><p>It publishes no share price or quarterly results, so it cannot be compared on them. Its listed competitors' figures are shown below.</p></div>
      ) : (
        <div className="kv" style={{ marginTop: 12 }}>
          <div><small>Market cap</small><b>{cr(o.market_cap)}</b></div>
          <div><small>Sales, last 4 quarters</small><b>{cr(o.ttm_sales)}</b></div>
          <div><small>Sales growth · {o.quarter || "latest quarter"} YoY</small><b className={tone(o.sales_yoy)}>{pct(o.sales_yoy)}</b></div>
          <div><small>Net profit growth · YoY</small><b className={tone(o.profit_yoy)}>{pct(o.profit_yoy)}</b></div>
          <div><small>Operating margin</small><b>{pct(o.opm, false)}</b></div>
          <div><small>Share price · 30 trading days</small><b className={tone(o.chg_30)}>{o.close ? `₹${o.close.toLocaleString("en-IN")} · ` : ""}{pct(o.chg_30)}</b></div>
        </div>
      )}

      {d.standing.length > 0 && (
        <div className="panel">
          <h5>Where {co} stands</h5>
          <ul className="cmp">{d.standing.map((s) => (
            <li key={s.measure}><span className={`pill2 ${s.verdict === "ahead" ? "rip-opportunity" : s.verdict === "behind" ? "rip-risk" : "rip-neutral"}`}>{s.verdict === "info" ? "size" : s.verdict}</span> <b>{s.measure}:</b> {s.text}</li>
          ))}</ul>
        </div>
      )}

      {rows.some((r) => (r.sales_series?.length || 0) > 1) && (
        <div className="panel">
          <h5 style={{ margin: 0 }}>Quarterly results, last year</h5>
          <p className="sub" style={{ fontSize: 12.5, margin: "2px 0 0" }}>The last five quarters for each company, so the latest quarter sits beside the same quarter a year earlier. Bars are sales and net profit in ₹ crore, each company on its own scale; the line is operating margin. Companies with no results on record are left out.</p>
          <div className="qcharts">
            {rows.filter((r) => (r.sales_series?.length || 0) > 1).map((r) => (
              <QuarterlyResults key={r.name} name={r.name} own={r.own} quarters={r.quarters || []} sales={r.sales_series || []} profit={r.profit_series || []} opm={r.opm_series || []} />
            ))}
          </div>
        </div>
      )}

      {px && <LineChart title="Share price, indexed to 100" sub={`Each company's BSE closing price over the last ~100 trading days, set to 100 on the first day, so moves compare whatever the price level. ${co} is the thick line.`} xs={px.xs} series={px.series} unit="" base={100} />}
      {opm && <LineChart title="Operating margin by quarter" sub={`Operating profit as a share of sales, quarter by quarter (Fincrux). ${co} is the thick line.`} xs={opm.xs} series={opm.series} unit="%" />}

      <div className="panel">
        <h5>Balance sheet and market multiples</h5>
        <p className="sub" style={{ marginTop: 0, fontSize: 12.5 }}>From each company's latest annual accounts (Fincrux). Multiples are market facts for comparing peers, not a valuation.</p>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl mkt">
            <thead><tr><th>Company</th><th>Year</th><th>Debt / equity</th><th>Interest cover</th><th>Free cash flow</th><th>ROCE</th><th>Sales growth · 3 yrs a year</th><th>Altman Z</th><th>P/E</th><th>P/B</th><th>EV / EBITDA</th><th>ROE</th></tr></thead>
            <tbody>{rows.map((r) => {
              const h = r.health || {};
              const x = (v: number | null | undefined, unit = "") => v === null || v === undefined ? "—" : `${v}${unit}`;
              return (
                <tr key={r.name} className={r.own ? "own" : ""}>
                  <td><b>{r.name}</b></td><td>{h.year || "—"}</td>
                  <td className="num">{x(h.debt_to_equity, "x")}</td><td className="num">{x(h.interest_cover, "x")}</td>
                  <td className={`num ${tone(h.fcf)}`}>{cr(h.fcf)}</td><td className="num">{pct(h.roce, false)}</td>
                  <td className={`num ${tone(h.sales_cagr_3y)}`}>{pct(h.sales_cagr_3y)}</td>
                  <td className="num">{h.altman_z ? <span className={`pill2 ${ZONE[h.altman_z.zone]}`} title={`${h.altman_z.zone} zone`}>{h.altman_z.z} · {h.altman_z.zone}</span> : "—"}</td>
                  <td className="num">{x(h.pe)}</td><td className="num">{x(h.pb)}</td><td className="num">{x(h.ev_ebitda)}</td><td className="num">{pct(h.roe, false)}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
        <details style={{ marginTop: 8 }}>
          <summary className="sub" style={{ fontSize: 12.5, cursor: "pointer" }}>How these are calculated</summary>
          <ul className="cmp" style={{ fontSize: 12.5 }}>
            <li><b>Debt / equity</b>: borrowings ÷ (equity capital + reserves). <b>Interest cover</b>: (profit before tax + interest) ÷ interest, last twelve months.</li>
            <li><b>Altman Z-score</b> = 1.2 × working capital/assets + 1.4 × reserves/assets + 3.3 × EBIT/assets + 0.6 × market cap/liabilities + 1.0 × sales/assets. Above 2.99 safe, 1.81–2.99 grey, below 1.81 distress. Built for listed manufacturers: read it with care for IT services. Fincrux does not split out working capital, so it is estimated from working-capital days.</li>
            <li><b>EV</b> = market cap + borrowings (Fincrux gives no cash figure, so cash is not subtracted). <b>EV / EBITDA</b> uses operating profit for the last twelve months.</li>
            <li>A distress-zone score, debt above 2× equity or interest cover below 1.5× raises a <b>Balance sheet</b> signal on the company.</li>
          </ul>
        </details>
      </div>

      <div className="panel">
        <h5>Side by side · {rows.length} companies</h5>
        <div style={{ overflowX: "auto" }}>
          <table className="tbl mkt">
            <thead><tr><th>Company</th><th>Market cap</th><th>Sales · 4 qtrs</th><th>Sales YoY</th><th>Profit YoY</th><th>Op. margin</th><th>Price · 30d</th><th>Price · ~100d</th><th>Promoters</th><th>FIIs</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.name} className={r.own ? "own" : ""}>
                <td><b>{r.name}</b>{r.nse_symbol && <span className="sub"> · {r.nse_symbol}</span>}{r.role === "target" && <span className="pill2" style={{ marginLeft: 6 }}>target</span>}</td>
                <td className="num">{cr(r.market_cap)}</td><td className="num">{cr(r.ttm_sales)}</td>
                <td className={`num ${tone(r.sales_yoy)}`}>{pct(r.sales_yoy)}</td><td className={`num ${tone(r.profit_yoy)}`}>{pct(r.profit_yoy)}</td>
                <td className="num">{pct(r.opm, false)}</td>
                <td className={`num ${tone(r.chg_30)}`}>{pct(r.chg_30)}</td><td className={`num ${tone(r.chg_period)}`}>{pct(r.chg_period)}</td>
                <td className="num">{pct(r.promoters, false)}</td><td className="num">{pct(r.fiis, false)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className="sub" style={{ fontSize: 12, marginBottom: 0 }}>
          Growth is the latest quarter against the same quarter a year earlier. — means not on record yet.
          {d.pending.length > 0 && <> Figures pending for {d.pending.join(", ")}: press Fetch missing figures (Fincrux allows 5 calls a day, so results fill over several days).</>}
          {d.unlisted.length > 0 && <> Not listed, so not compared: {d.unlisted.join(", ")}.</>}
        </p>
      </div>
    </>
  );
}
