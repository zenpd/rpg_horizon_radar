# Horizon Radar — remaining work

Status as of 8 Oct 2026, branch `remove-demo-data`. The app holds no demo data: every screen shows
watched companies' public signals, rule-based scores and what users did, or an empty state that says
what would fill it. There are no roles, sector gates or approvals: every signed-in user sees and can
change everything (DESIGN.md §4). See DESIGN.md §15–16.

## 0. Next up (requested 8 Oct 2026)

- [ ] **A common landing page, and every other tab specific to the selected company.**
  - The landing page is the same for all users and all subsidiaries: M&A-related news across every
    opportunity, whichever RPG company it belongs to (new M&A signals, Sector Scout finds, deals,
    stake sales, distress and fund-raise news), each item tagged with the RPG company it is for.
  - Every other tab (M&A Signals, Competitor Analysis, Ask Radar, Shortlisted signals, Radar settings,
    Self analysis, Weekly digest, The financial market) shows only the subsidiary picked in the
    company box. Today some tabs accept "All companies"; decide whether "All" stays as a choice
    outside the landing page.
- [ ] **Rename "Connections" in the acquisition thesis.** The word reads like social connections. The
  section lists shareholders, the promoter group, parent, subsidiaries, joint ventures, partners, key
  customers and suppliers, and directors. Candidate names: "Ownership and business ties",
  "Corporate relationships" or "Group structure and partners". Rename the thesis tab, the section
  heading, the graph's label and the agent's wording together.

## 1. Before anyone outside the build team uses it

- [ ] **Licence and terms checks.**
  - [ ] NSE's terms on automated access to its site API. The connector can be switched off with
    `NSE_ENABLED=false`.
  - [ ] Glassdoor via Fetchlayer, which scrapes Glassdoor. This connector is not built until it is
    cleared.
- [ ] **Rotate every API key** that was pasted into chat or shown in a screenshot during the build:
  NVIDIA, Groq, Azure OpenAI, Tavily, GNews, YouTube, EPO, Alpha Vantage, Fincrux, Fetchlayer and
  Marketstack. In deployed environments, move them to Key Vault (`*_kv_uri` settings).
- [ ] **First user per environment.** Set `FIRST_USER_EMAIL` and `FIRST_USER_PASSWORD_KV_URI` before
  the first start; that user adds the others. Every user sees all data, so decide who gets an account.
- [ ] **Run migrations `0004` to `0008`** on every existing database (`alembic upgrade head`): demo
  data removed, approvals removed, opportunity findings, entity role, Ask Radar conversations. Tested
  on SQLite; not yet run on PostgreSQL. 0005 turns every proposed company into a watched one.

## 2. Real sources still to build

| Area | Today | To do |
|---|---|---|
| SWOT | Built weekly for all six from public research, following each company's SWOT parameters | Fincrux's 5 calls a day cover only about five companies a day; Raychem RPG (unlisted) has only web and news facts |
| Saved acquisition theses (Radar settings) | Criteria are saved; no matches | Match the saved theses against the discovered targets |
| Watch rules | Opportunity score only | Add metrics as data arrives (promoter pledge %, credit rating) |
| NewsData.io, Adzuna | Built but off (no keys) | Add `NEWSDATA_API_KEY`, `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` |
| Azure OpenAI (gpt-5.6-luna for theses, overviews, Ask Radar and the Sector Scout) | Reachable only over the VPN; without it the agents fall back to Groq or NVIDIA | Allow the deployed app's network on the `zaf-ai-foundry` resource, or a private endpoint |

## 3. Code and tests

- [ ] **Dark theme for the desk screens.** Digest archive and Users and watchlist stay light in dark
  theme; theme them if needed.
- [ ] **One place to manage the watchlist.** Users and watchlist → Watchlist and Radar settings →
  Watched companies both show watchlist information, and the radar's "universe" list overlaps with it.
  Decide which screen owns it.
- [ ] **Archive the old prototype folder** (`Claude outputs/RPG_Horizon_Radar`) once the team is on
  this repo. Its live caches and `.env` are local only.
