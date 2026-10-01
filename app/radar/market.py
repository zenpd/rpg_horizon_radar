"""Indexed share-price series for the Market performance screen.
Mock: a seeded random walk that lands on each company's stated return, so the chart is stable
between reloads. Production: daily closes from the licensed NSE feed, indexed to 100."""
from __future__ import annotations

from .reference import REF

M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return ((a & M32) * (b & M32)) & M32


def _to_i32(x: int) -> int:
    x &= M32
    return x - (1 << 32) if x & 0x80000000 else x


def rng(seed: str):
    a = 0
    for ch in seed:
        a = _to_i32(a * 31 + ord(ch))
    state = {"a": a & M32}

    def nxt() -> float:
        a2 = (state["a"] + 0x6D2B79F5) & M32
        state["a"] = a2
        t = _imul(a2 ^ (a2 >> 15), 1 | a2)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & M32) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296

    return nxt


def series(key: str, c: dict, period: str) -> list[float]:
    n = REF["PERIODS"][period]["n"]
    r = rng(key + period)
    tgt = c["ret"][period]
    w, nz = 0.0, [0.0]
    step = 1.2 if period == "1M" else 2.2
    for _ in range(n):
        w += (r() - 0.5) * 2 * c["vol"] * step
        nz.append(w)
    return [round(100 * (1 + tgt / 100 * i / n) + v - nz[n] * i / n, 2) for i, v in enumerate(nz)]


def market_view(co: str, ws: dict, rival: str | None, period: str) -> dict:
    f = ws["fin"]
    names = list(f["rivals"].keys())
    rival = rival if rival in f["rivals"] else names[0]
    rv = f["rivals"][rival]
    a, b = series(co, f["base"], period), series(rival, rv, period)
    base_name = co if f["listed"] else f.get("baseName", "Sector index")
    ra, rb = a[-1] - 100, b[-1] - 100
    return {
        "company": co, "listed": f["listed"], "base_name": base_name, "rival": rival, "rivals": [{"name": n, "segment": f["rivals"][n]["seg"]} for n in names],
        "more_tracked": ws["tracked"] - len(names), "period": period, "periods": list(REF["PERIODS"].keys()), "labels": REF["PERIODS"][period]["lab"],
        "base_series": a, "rival_series": b, "base_return": round(ra, 1), "rival_return": round(rb, 1),
        "event": {"at": rv["ev"][0], "label": rv["ev"][1]}, "why": rv["why"], "act": rv["act"],
        "metrics": [{"metric": m, "base": f["base"]["m"][i], "rival": rv["m"][i]} for i, m in enumerate(REF["FROWS"])],
    }
