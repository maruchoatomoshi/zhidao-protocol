# ZHIDAO Protocol Economy Passport

Last audit: 2026-04-26

This document is the working map of the in-app economy: where points are created, where they are burned, what limits protect the system, and what should be watched before adding new rewards.

## Core Currency

- Currency: `★` / points.
- Backend balance source: `users.points`.
- Main status counters: `user_status.extra_cases`, `extra_raids`, `double_win`, `immunity`.
- Admin changes should go through `/api/admin/points` so they are recorded in `admin_action_logs`.

## Point Sources

### Diary

- Auto diary reward: `20★` clean entry.
- Auto diary reward with warnings: `15★`.
- Manual diary points are capped by backend helper at `0..20`.
- Diary stars UI currently displays:
  - 1 star: `15★`
  - 2 stars: `30★`
  - 3 stars: `50★`
  - bonus: `+20★`
- Risk: diary/star rewards can become the largest predictable daily faucet if used every day for many students.
- Guardrail: keep diary rewards predictable, but avoid stacking too many passive multipliers on top of them.

### Raid

- Entry cost: `50★`.
- Success reward: `150★`.
- Success chance: `40%`.
- Net result:
  - success: `+100★`
  - failure: `-50★`
- Expected value per completed raid:
  - `0.4 * 100 + 0.6 * -50 = +10★`
- Base public daily limit: `3`.
- Expected base daily raid income if all three raids complete: about `+30★`.
- Extra raid attempt price: `80★`.
- Extra raid expected value is still about `+10★`, so it is not profitable as a pure point strategy.

### Standard Cases

- Backend cost: `50★`.
- Frontend entry threshold: `80★` balance, intentionally preventing players from dropping to near-zero.
- Daily limit: `3 + extra_cases`.
- Case pool:
  - gold: `78.9%`
  - purple: `21.0%`
  - black: `0.1%`
- Gold direct point rewards:
  - empty: weight `20`, `0★`
  - small: weight `35`, `30★`
  - medium: weight `25`, `60★`
  - jackpot: weight `1`, `250★`
  - utility prizes have no direct points.
- Gold direct point EV before cost: about `28★`.
- Overall direct point EV before cost: `0.789 * 28 = 22.1★`.
- Overall direct point EV after cost: about `-27.9★`.
- Interpretation: standard cases are a point sink with utility/collection upside.

### Genshin Prayers

- Backend cost: `50★`.
- Frontend entry threshold: `80✦` balance.
- Daily limit: `3 + extra_cases`.
- Pool:
  - blue: `79%`
  - purple: `20%`
  - gold: `1%`
- Blue direct point EV:
  - `+30` weight `300`
  - `+60` weight `150`
  - total blue item weight `780`
  - blue direct EV: about `23.1★`
- Overall direct point EV before cost: `0.79 * 23.1 = 18.2★`.
- Overall direct point EV after cost: about `-31.8★`.
- Duplicate `card_moon` refunds `50★`, making that specific duplicate effectively free.
- Card disassembly refunds `50★`.
- Interpretation: prayers are a sink early, but duplicate-heavy mature accounts need watching.

### Duplicate Disassembly

- Duplicate implant disassembly: `+100★`.
- Duplicate card disassembly: `+50★`.
- Risk: if duplicate rates rise, disassembly becomes a faucet.
- Current standard case duplicate implant risk is acceptable because purple/black hits are limited by case cost and daily limits.
- Current Genshin duplicate card risk should be watched once many players have full collections.

### Admin Adjustments

- `/api/admin/points` can add or remove points.
- Backend prevents negative balances with `MAX(0, points + delta)`.
- Backend caps one operation at `5000★`.
- Frontend asks confirmation for operations from `100★`.
- Every operation is logged to `admin_action_logs`.
- Risk: admin actions are the strongest possible faucet/sink and should be used with clear reasons.

## Point Sinks

### Shop

Current notable sinks:

- Immunity: `150★`
- Laundry VIP: `80★`
- DJ: `100★`
- Solo seat: `120★`
- Amnesty: `80★`
- KFC: `300★`
- Bubble tea: `250★`
- Snack: `200★`
- No report: `400★`
- Poizon: `600★`
- Extra case: `180★`
- Double win: `130★`
- Daily title: `150★`
- Extra raid attempt: `80★`
- Path change: `500★`

Design reading:

- Food/cosmetic/status items are good aspirational sinks.
- `path_change` at `500★` is a strong premium sink.
- `extra_case` at `180★` is safe because cases/prayers are negative EV by points.
- `extra_raid_attempt` at `80★` is safe because raid EV is much lower than its price.
- `double_win` at `130★` is a fun sink, not a profit tool.

### Gifting And Selling

- Gift tax: `20★`.
- Selling shop item: refund `50%`.
- Risk: if an item has immediate non-point utility and can then be sold, check for use-then-sell loops.

## Current Anti-Abuse Rules

- Cases/prayers require frontend balance threshold `80`, despite backend cost `50`.
- Standard cases decrement `extra_cases` after the base daily limit.
- Genshin prayers now decrement `extra_cases` after the base daily limit.
- Raids decrement `extra_raids` after the base public daily limit.
- Non-admin raid limit ignores admin-only finished raids.
- Shop daily counts prevent global overbuy for limited items.
- Admin point adjustments are logged and cannot push balances below zero.

## High-Risk Areas

### 1. Genshin Extra Attempts

Status: fixed in `zhidao_api_ready.py`.

Before the fix, Genshin checked `extra_cases` but did not decrement it after the daily limit. One extra case could unlock unlimited extra prayers. The fix mirrors standard case behavior.

Deployment note: the server `/root/zhidao_api.py` must be updated from this repo copy for the fix to become live.

### 2. Duplicate Refunds

Risk: medium.

Duplicates currently return:

- implants: `100★`
- cards: `50★`

This is okay while duplicates are rare. If future banners/pools make duplicates common, reduce refunds or add daily disassembly limits.

### 3. Manual/Admin Rewards

Risk: medium-high.

Admin rewards are powerful and flexible. The new action log helps, but the team should keep a simple rule: every manual adjustment needs a clear reason.

### 4. Raid Upgrade

Risk: medium.

Current raid EV is only `+10★`, safe. Raid 2.0 should not stack guaranteed rewards, role bonuses, and high success chance without recalculating EV.

## Recommended Balance Targets

- Normal daily reliable income: `20-80★`.
- Good active day: `80-150★`.
- Exceptional day/event: `150-300★`.
- Premium sink price range: `300-600★`.
- Avoid repeatable loops with positive EV above `+30★` per action.
- Keep daily repeatable faucets capped unless they are tied to real learning/tasks.

## Pre-Release Checklist For New Rewards

Before adding any new economy feature, answer:

1. Does it create points, burn points, or convert items into points?
2. Is it repeatable daily?
3. Can admins trigger it manually?
4. Can it stack with `double_win`, duplicate refunds, raid rewards, diary rewards, or passive cards/implants?
5. Does it have a daily limit?
6. What is the expected value per use?
7. Can the player buy the input and sell/output for more than the cost?

## Suggested Next Pass

1. Add admin action logs for duplicate disassembly and casino/prayer opens if deeper audit history is needed.
2. Add a small `/api/economy/audit` admin endpoint that summarizes daily points created/burned.
3. Add daily disassembly limits if duplicate refunds start becoming common.
4. Recalculate economy before Raid 2.0 goes live.
