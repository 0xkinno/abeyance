# Design

Near-black ground (`#0b0d10`), hairline rules (`#232830`), one amber for "waiting" (`#e0a84a`), one
cool green for "done" (`#5fbf8f`). Text `#e8eaed`, muted `#9aa3ad`. Plain system fonts and a monospace
for commands. No emoji, no dashes used as pauses, no hype words (`scripts/check_copy.py`).

Cards say what stopped, why, where, what already happened, how to answer and when it expires, in that
order, and every word comes from `abeyance/card.py`. The Desktop page uses the same order with an amber
left rule for waiting and green for executed. Motion: one signature (a card slides into a held slot and
releases on resume) on the landing page only, and `prefers-reduced-motion` is respected.
