# ZHIDAO Protocol Economy Passport

Snapshot: 2026-05-15

## Core Model

- `points` are the live spendable wallet (`★`).
- `rep_score` is the public protocol rating (`REP`).
- Public leaderboard is built from `rep_score`, not from wallet balance.
- Wallet movements are logged through `economy_log` when they go through the FastAPI layer.

## Final REP Rules

### REP grows automatically

- Diary stars:
  - `1` star: `+15 REP`;
  - `2` stars: `+30 REP`;
  - `3` stars: `+50 REP`;
  - diary bonus: additional `+20 REP`.

### REP decreases automatically

- Mandatory presence penalties:
  - morning check;
  - evening check;
  - manual check when an admin marks the participant for penalty.
- The REP delta mirrors the actual wallet penalty, for example `-50★` and `-50 REP`.

### REP is changed manually by admins

- Real help to the group.
- Initiative.
- Discipline.
- Learning progress.
- Any contribution that should affect public status but cannot be measured safely by automation.

### REP never changes from

- Cases and prayers.
- Shop purchases.
- Gifts.
- Contracts and P2P flows.
- Salary.
- Passive income.
- Raids.
- Random drops.
- Resale of items.

Short rule:

`REP` is for learning, contribution, and discipline.
`★` are for wallet movement.
Luck and trade do not raise public status.

## Automatic Sources

| Source | Wallet | REP | Notes |
| --- | ---: | ---: | --- |
| Diary stars | `15 / 30 / 50★`, optional `+20★` bonus | same delta | Implemented in `/api/diary/stars/rate`. |
| Raid win | `+100★` | `0` | Entry is `-50★`; 40% win chance; EV is `-10★` per attempt after the latest nerf. |
| Card/implant duplicate dismantle | `+50★ / +100★` | `0` | Sink recovery only. |
| Sunday salary | configurable, default `+100★` | `0` | Bot-only; Red Dragon doubles it. |
| NetWatch morning | `+25★` | `0` | Bot-only passive. |
| Caishen morning | `+15★` | `0` | Bot-only passive. |
| Qilin morning | `10★ x number_of_qilin_owners` per owner | `0` | Total mint is quadratic: `10 * N^2` per day. |

## Manual Sources

| Source | Wallet | REP | Notes |
| --- | ---: | ---: | --- |
| Admin points action in Mini App | configurable | `0` | `/api/admin/points`, wallet only. |
| Admin REP action in Mini App | `0` | configurable | `/api/admin/rep`, REP only. |
| Legacy bot `/award` | configurable | `0` | Direct DB write, bypasses REP split and `economy_log`. |

## Sinks

| Sink | Wallet | REP | Notes |
| --- | ---: | ---: | --- |
| Shop purchase | item price | `0` | Clean sink. |
| Case / prayer | `-50★` plus prize payout | `0` | Three free attempts per day, extras via shop. |
| Raid entry | `-50★` | `0` | Max 2 personal attempts/day, max 3 public raids/day, extras via shop. |
| Presence penalty | up to `-50★` | same negative delta | Mandatory presence failures reduce both wallet and public rating. |
| Contract fee | `10%`, minimum `2★` | `0` | Burned only after successful completion. |
| Gift tax | `-20★` | `0` | Max 5 gifts/day for non-admins. |

## Transfer Channels

### Contract Board

- Customer freezes the full reward on creation.
- Worker receives `reward - fee`.
- Fee is burned.
- Limits:
  - students: `5-50★` per contract;
  - admins: up to `100★`;
  - max `3` active contracts;
  - max `5` completed contracts/day per worker;
  - max `150★` daily spend;
  - max `150★` daily earn;
  - no self-accept;
  - completion under 5 minutes is flagged suspicious.
- Admin monitor already tracks repeated pairs, suspicious deals, disputes, gifts, and contract/gift overlap.

### Gifts

- Sender pays `20★` tax.
- Recipient gets the item.
- Recipient can currently sell the gifted item for `50%` of original shop price.
- Current protection:
  - only `5` gifts/day;
  - every gift costs `20★`;
  - monitor shows repeated gift pairs and cross-links with contract pairs.

## Random Systems

### Cases

- Price: `50★`.
- Frontend enforces visible threshold `80★`, backend checks only `50★`.
- Daily limit: `3`, extras possible.
- Case type probabilities: gold `78.9%`, purple `21.0%`, black `0.1%`.
- Direct cash EV from gold prizes:
  - gross inside gold case: `28★`;
  - weighted across all cases: `22.092★`;
  - direct wallet EV per case: about `-27.9★`.
- Real value is higher because non-cash prizes exist, but this remains a sink by wallet math.

### Genshin prayers

- Price: `50★`.
- Frontend enforces visible threshold `80★`, backend checks only `50★`.
- Daily limit: `3`, extras possible.
- Pool probabilities: blue `79%`, purple `20%`, gold `1%`.
- Direct wallet EV from point drops:
  - blue pool gross wallet EV: about `23.08★`;
  - weighted across all prayers: about `18.23★`;
  - direct wallet EV per prayer: about `-31.77★`.

### Raids

- Entry: `50★`.
- Win reward: `100★`.
- Win chance: `40%`.
- Current EV: `0.4 * 100 - 50 = -10★`.
- After the latest change this is a mild sink, not a farm.

## Real vs Decorative Passives

Implemented:

- `Guanxi`: `-10%` to shop prices.
- `Terracota`: blocks one penalty per day.
- `Panda`: `+10★` cashback after a shop purchase.
- `Shaolin`: `+20★` for timely morning/evening presence confirmation.
- `Linguasoft`: `+30★` once for a top diary score on a given diary day.
- `Caishen`: `+15★` daily.
- `Qilin`: `+10★` per Qilin owner daily.
- `NetWatch`: `+25★` daily plus active API abilities.
- `Red Dragon`: bot salary/award multiplier exists.

Still pending:

- Card passives still look mostly decorative in the current backend, except the Moon duplicate refund path.

## Important Findings

### 1. REP split is only partly enforced

- Mini App admin tools support separate wallet and REP adjustments.
- Diary stars correctly change both wallet and REP.
- Mandatory presence penalties now change both wallet and REP.
- But legacy bot `/award` and `/penalize` still change only wallet.

### 2. Bot-side economy bypasses the audit log

- Bot salary and passive payouts write directly to `users.points`.
- Legacy bot `/award` and `/penalize` also write directly.
- These movements are not inserted into `economy_log`.
- Result: the admin monitor is good for API-side flows, but not yet a complete source of truth.

### 3. Qilin is the strongest inflation vector

- With `N` owners, total daily mint is `10 * N^2`.
- Examples:
  - 3 owners: `90★/day` total;
  - 5 owners: `250★/day`;
  - 10 owners: `1000★/day`.
- This is the first passive to watch if wallet inflation accelerates.

### 4. Gifts remain a weak indirect transfer path

- A child can buy an item, gift it, and the receiver can sell it for half price.
- Because the sender also pays `20★`, this is inefficient and capped at 5/day, so it is not a cheap laundering path.
- Still, it is a real value-transfer channel and should remain visible in monitoring.

### 5. Frontend and backend disagree on the 80★ threshold

- UI says cases/prayers require `80★`.
- Backend accepts anyone with `50★`.
- Normal users are protected by UI, but direct API calls or future alternate clients bypass the rule.

### 6. Some advertised passives are not active yet

- This is less a balance issue than a trust issue.
- If children start comparing catalog text with actual behavior, the system will feel inconsistent.

## Recommended Next Actions

1. Decide the canonical REP rules:
   - diary and selected admin awards definitely increase REP;
   - decide whether presence penalties and manual penalties also reduce REP.
2. Move bot money actions onto API routes or at least add `economy_log` writes for:
   - salary;
   - bot `/award`;
   - bot `/penalize`;
   - NetWatch/Caishen/Qilin morning payouts.
3. Enforce the `80★` reserve threshold in backend too, or remove the text from UI if it is only intended as guidance.
4. Finish the implant layer:
   - ordinary implant passives are now implemented;
   - legendary implant actions still need a dedicated controlled UI;
   - card passives should be designed separately after implants are complete.
5. Keep raids at the current `-10★` EV unless you want them to become a reward event rather than a sink.
6. Keep gift monitoring enabled; if needed later, add “gifted items cannot be sold” or a lower resale value for gifted items.
7. Watch Qilin ownership before launch; it can become the dominant mint faster than any other source.
