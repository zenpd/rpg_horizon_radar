"""Horizon Radar's LLM agents and the model clients they use. Nothing outside
this package calls a language model. See DESIGN.md §7.

  swot_analyst         Drafts each RPG company's SWOT and TOWS moves from cited
                       evidence; rule checks send a failing draft back for revision.
  watchlist_discovery  Proposes competitors and adjacent players from web search
                       results, keeping only names the cited results contain.
  llm_routes           The reasoning-model routes both agents draft through
                       (Groq, then NVIDIA, then Azure OpenAI).
  llm_azure            One-shot Azure OpenAI calls for thesis parsing and Ask
                       Radar, each with a rule-based fallback in its caller.

No agent scores a signal or values a company: scoring stays rule-based
(services/scoring.py), as do routing, digests and the Escalation Brief."""
