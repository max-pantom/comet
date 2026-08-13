---
name: slideshow-distribution-app-growth
description: Playbook for validating and growing a consumer app by building it around a TikTok slideshow format that's already proven to go viral, then running a network of accounts to distribute it — instead of building an app first and hoping for distribution. Use this whenever the user is picking a new app idea, validating demand for one, planning TikTok/IG growth for an app or product, designing a UGC/slideshow content strategy, or building a network of posting accounts. Trigger even if the user just says things like "help me find an app idea," "how do I market this app," "grow my app on TikTok," or "find a viral format," without naming slideshows or this skill explicitly.
---

# Slideshow Distribution → App Growth Playbook

## Core thesis

Distribution beats product. A great app nobody sees makes $0; a mediocre app in
front of the right audience prints money. Most founders build the app first,
ship it, and only then ask "now what?" — that's the wall.

This playbook inverts the order: **find a content format that is already
winning on TikTok, reverse-engineer why it works, then design the app's core
feature to slot directly into that format.** Slideshows are the vehicle of
choice — cheap and fast to produce, they convert as well as video, and they
currently move more views per dollar/effort than any other TikTok format,
especially in "utility" niches (self-improvement, wellness, looksmaxxing,
money, relationships, gym, etc.).

Whenever this skill is in use, keep steering the user back to this order:
**format first → app second → distribution engine third.** Don't let them
skip to building the app before step 1 and 2 are done.

## Step 1 — Pick a niche with a pulse, then narrow it hard

1. Start from a broad, obviously-viral category (mental wellness, looksmaxxing,
   money/finance, relationships, gym/fitness, productivity, sleep, skincare,
   etc.).
2. Narrow it into a specific sub-niche — broad categories are saturated,
   narrow angles are winnable. Example: `mental wellness → women → mental
   state inside a relationship`. Use Claude/an LLM to help expand a broad
   niche into 5-10 candidate sub-niches.
3. Validate the sub-niche is real demand, not a guess: check TikTok Search
   Insights for the actual search terms people use inside that sub-niche.
   Look for high volume and a rising trend line (e.g. "climbing 190%+ this
   week"), and pull ~30 search-backed content angles out of it.
4. Sanity-check the opportunity: are there only a handful of apps actually
   serving this narrow angle? If a small app in the space is already pulling
   meaningful monthly revenue (check public tools like Sensor Tower, but treat
   their numbers as a lowball floor, not a ceiling — real revenue is often
   materially higher), that's a strong signal, not a reason to avoid it.

## Step 2 — Find the accounts already winning this format

Use an LLM to generate a batch of TikTok search keywords for the sub-niche,
then manually scroll and save every strong slideshow post into a swipe file.
The goal is volume — enough saved examples that patterns start repeating and
your own remix ideas start coming naturally.

**The single biggest mistake:** saving an account because ONE post went
viral. That's copying luck, not a format. Only save accounts that pass ALL of:

- An active, repeatable format/pattern — not a one-off.
- Posts daily (or near-daily).
- At least 100k+ views in the last 30 days, spread across multiple posts —
  not concentrated in a single fluke.
- Bonus (best signal): run by a normal person posting for fun or for
  platform content-reward money, with **no product behind it at all**. That's
  an unclaimed distribution channel sitting there waiting for a product to
  drop into it.

## Step 3 — Reverse-engineer why the format works

For every account that passed the filters, study the top posts like an
autopsy:

- What's the slide-1 hook? (Common pattern: an emotionally loaded
  "expertise" hook — e.g. a crying-face image establishing the poster as an
  authority in a relatable role.)
- How many slides total?
- Where in the sequence does the actual value/payoff land?
- What specifically makes someone stop scrolling and save it (not just
  watch it)?

Write this DNA down explicitly before designing anything. If an account has a
*wall* of hits (not just one), the format is systematically reproducible —
that's what makes it worth building on top of.

## Step 4 — Design the app around the format, not the other way around

Once the format's DNA is documented, the format tells you what to build:
identify the one core feature that is literally what the slides are
demonstrating (the "how to use the product" moment), and build that first.
Everything else — onboarding, monetization, polish — comes after that single
feature works and slots naturally into the proven slide sequence (typically:
hook slide → 4-6 slides showing the product doing the thing).

Two known real-world patterns worth citing to the user as reference points:
- A niche utility app in an emotional/self-expression space grew almost
  entirely on this slideshow-only model, running the same format across
  dozens of accounts.
- "Clone-maxxing": taking a slideshow format + distribution strategy that's
  already proven on an existing successful app, and adapting it 1:1 for a new
  app in a similar space, with a creator reproducing the exact format.

## Step 5 — Build the distribution engine

The daily loop is: make slideshows by hand (there's currently no tool that
produces slide art at human-passable quality — anything auto-generated reads
as an image-with-text-slapped-on and underperforms), and post every day
across a network of accounts running the same proven format.

**If targeting the same country you're in:**
- TikTok allows roughly up to 10 accounts per device before flagging — so
  scale via cheap secondhand phones, one SIM per device, ~10 accounts each.
- Hire younger posters (teens who already live on TikTok) to handle the
  actual posting volume — they already understand the platform's native
  feel and are inexpensive.

**If targeting a country you're not based in (the higher-leverage route):**
- Don't build new accounts from scratch — rent access to accounts that are
  already native to that market and already have an audience.
- Find creators in public Discord servers built around TikTok posting/growth
  communities, and DM in bulk (100+/day is the baseline volume needed) to
  offer to pay them to post your slideshow content on their existing
  accounts.
- A workable payout structure to start from and adjust: **$100 at 100k
  views, $350 at 1M views, capped around $500 at 2M views.** Start offers
  low and flex per creator. Layer in occasional bonus payouts on top of the
  agreed rate — it costs little relative to the views bought, and it buys
  loyalty so the same creators keep posting for you repeatedly instead of
  one-and-done.
- Avoid proxies/VPNs/spoofed-location accounts — fragile and high
  maintenance compared to the Discord creator-rental route.
- Either way, the underlying principle is constant: **one proven format,
  posted daily, across many accounts.**

## Optional tooling note

There are MCP-based tools built specifically for this workflow (e.g. one
called scroll.show) that plug into Claude Code/Codex to search TikTok for
accounts matching filters like view-count thresholds and posting frequency,
bulk-download top posts from a set of accounts for analysis, and suggest
where a given product fits a format's DNA — useful if the user wants to
automate steps 2-3 instead of doing them by hand. Don't assume the user has
this tool; ask before recommending workflow steps that depend on it.

## When helping the user apply this playbook

- If they already have app ideas in mind, ask which one you're validating
  first, and start at Step 1 with THAT niche rather than a generic one.
- If they don't have an app idea yet, that's fine — this format-first
  approach explicitly supports finding the format before the app exists.
- Push back gently if they want to jump straight to building an app without
  having done Steps 1-3 (finding + validating a proven format) — that's the
  exact trap this playbook exists to avoid.
- Keep the tone practical and execution-focused: the bottleneck in this
  model is daily reps (searching, saving, studying, posting), not more
  planning.
