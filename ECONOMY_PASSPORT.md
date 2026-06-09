# ZHIDAO Protocol Economy Passport

Snapshot: 2026-06-06

## Core Model

- `points` are the spendable wallet: `★`.
- `rep_score` is public protocol reputation: `REP`.
- Public leaderboard uses `rep_score`, not wallet balance.
- `★` can be earned, spent, transferred through controlled mechanics, and burned by fees.
- `REP` cannot be spent, transferred, gifted, or bought through P2P.

Short rule:

`REP` shows contribution. `★` show wallet power.

## REP Rules

REP grows automatically only from diary rating:

| Action | REP |
| --- | ---: |
| Diary 1 star | `+15` |
| Diary 2 stars | `+30` |
| Diary 3 stars | `+50` |
| Diary bonus | `+20` |

REP decreases automatically from presence penalties:

| Action | REP |
| --- | ---: |
| Morning/evening/manual presence penalty | same negative delta as wallet penalty |

Admins can adjust REP manually through `/api/admin/rep`.

REP does not change from:

- shop purchases;
- gifts;
- contracts;
- contract fees;
- raids;
- cases/prayers;
- card or implant passive income;
- salary;
- item resale;
- random drops.

## Wallet Sources

| Source | Wallet | REP | Notes |
| --- | ---: | ---: | --- |
| Diary rating | `+15/+30/+50★`, optional `+20★` | same delta | API-side, logged. |
| Presence scan reward | `+1 scan_attempt` | `0` | New morning/evening confirmation, cap `7`. |
| Admin wallet action | configurable | `0` | `/api/admin/points`. |
| Bot `/award` | configurable | `0` | Direct DB write; should be moved to API/log. |
| Sunday salary | default `+100★` | `0` | Bot-side; Red Dragon doubles it. |
| Raid win | `+100★` | `0` | Entry is `-50★`, win chance `40%`. |
| Case cash drop | `0/+30/+60/+250★` | `0` | Costs scan attempt, not direct ★. |
| Genshin prayer cash drop | `+30/+60★` | `0` | Costs scan attempt, not direct ★. |
| Card duplicate disassemble | `+50★` | `0` | Duplicate recovery. |
| Implant duplicate disassemble | `+100★` | `0` | Duplicate recovery. |
| Shop resale | `50%` or `60%` with Panda | `0` | Recovery, not profit if bought normally. |
| Contract payout | `reward - fee` | `0` | Transfer from creator's frozen reward. |

## Wallet Sinks

| Sink | Wallet | REP | Notes |
| --- | ---: | ---: | --- |
| Shop purchase | item price | `0` | Guanxi/Zhongli discounts can reduce price. |
| Gift tax | `20★`, or `15★` with Fox once/day | `0` | Non-admin gift limit: `5/day`. |
| Contract fee | `10%`, minimum `2★` | `0` | Burned after successful completion. |
| Raid entry | `-50★` | `0` | Max `2` personal attempts/day, `3` public raids/day. |
| Presence penalty | default `-50★` | same negative delta | Can be reduced/blocked by passives. |
| Admin/bot penalty | configurable | usually `0` REP unless API presence/admin REP is used | Bot penalty currently direct DB write. |
| Legendary attacks | `-10★/-15★/-5★ collateral` | `0` | Red Dragon / NetWatch actions. |

## Contracts

Rules:

- Student reward range: `5-50★`.
- Admin reward range: `5-100★`.
- Active contracts per creator: `3`.
- Completed contracts per worker per day: `5`.
- Daily creator spend limit: `150★`.
- Daily worker earn limit: `150★`.
- Fee: `10%`, minimum `2★`.
- Completion under `5` minutes is marked suspicious.
- Self-accept is blocked.
- Anonymous public posting is allowed, but admin monitor keeps real identities.

Card interaction:

- Zhongli: once/day reduces contract fee by `1★`.
- Sea: first completed contract as assignee per day gives `+5★`.

## Gifts

Rules:

- Non-admins can send up to `5` gifts/day.
- Sender pays gift tax.
- Recipient receives the item.
- Gifted items can still be sold, so gifts remain an indirect value-transfer channel.

Current protection:

- `20★` tax, or `15★` once/day with Fox.
- Daily cap.
- Admin monitor tracks repeated gift pairs and contract/gift overlap.

If abuse appears later, the next strict option is: gifted items cannot be sold, or gifted resale rate is reduced.

## Raids

Current math:

- Entry: `50★`.
- Win reward: `100★`.
- Win chance: `40%`.
- Expected value: `0.4 * 100 - 50 = -10★`.

This means raid is a mild sink, not a farm.

Card interaction:

- Pyro: first failed raid/day refunds `10★`.
- Star: first failed raid/day refunds `15★`.
- Star: first successful raid/day gives `+10★`.

If a player has both Pyro and Star, first failed raid loss becomes `-25★` instead of `-50★`.

## Cases And Prayers

Current model:

- Cases and Genshin prayers spend `scan_attempts`, not direct `★`.
- `scan_attempts` come from activity and shop item `extra_case`.
- Non-admin scan attempts are capped at `7`.

Scan attempt sources:

- New morning/evening confirmation: `+1`.
- First diary reaching `3★`: `+1`.
- Shop item `extra_case`: `+1`.
- Zhongli first shop purchase/day: `+1`.
- Moon evening confirmation/day: `+1`.

Cases:

- Gold/purple/black roll.
- Possible cash prizes: `+30★`, `+60★`, `+250★`.
- Possible utility/item/implant drops.

Genshin prayers:

- Blue/purple/gold pools.
- Possible cash prizes: `+30★`, `+60★`.
- Possible cards, immunity, free-time item.
- Fox can turn first `+30★` prayer/day into `+60★`.
- Sea grants `+20★` on every 3rd prayer/day.
- Moon duplicate grants `+50★`.

## Implant Passives

Implemented:

- Guanxi: `-10%` shop discount.
- Terracota: blocks one penalty/day; after block, next penalty reduced by `5★`.
- Panda: `min(10★, 40% of price)` cashback on shop purchase (caps arbitrage even on cheap future items); resale `60%` instead of `50%`.
- Shaolin: `+20★` for timely morning/evening confirmation; `+10★` for full morning+evening day.
- Linguasoft: `+30★` for new `3★` diary; `+20★` for three consecutive `3★` diary entries.
- Caishen: `+15★` daily bot-side.
- Qilin: diminishing-returns daily payout, `max(8★, 40★ - (N-1)*6★)` per owner (already capped, see Inflation Risks).
- Red Dragon: salary/award multiplier in bot; active legendary actions.
- NetWatch: `+25★` daily bot-side; active legendary actions.

## Card Passives

Ordinary cards:

- Pyro: first penalty/day refunds up to `25★`; first failed raid/day refunds `10★`.
- Fox: first `+30★` prayer/day becomes `+60★`; first gift/day tax is `15★` instead of `20★`.
- Fairy: `+10★` for first new morning/evening confirmation; `+10★` for full morning+evening day.
- Literature: `+15★` for new `3★` diary; `+10★` for diary bonus line.
- Forest: `+8★` for morning confirmation; `+6★` for first manual presence confirmation/day.
- Sea: every 3rd prayer/day gives `+20★`; first completed contract/day gives `+5★`.
- Moon: duplicate gives `+50★`; evening confirmation gives `+1 scan_attempt`.

Legendary cards:

- Zhongli: `-5%` shop discount; first contract/day reduces fee by `1★`; first shop purchase/day gives `+1 scan_attempt`.
- Star: first penalty/day is reduced by `15★`; new `3★` diary gives `+10★`; first raid win/day gives `+10★`; first raid failure/day refunds `15★`.

## Main Inflation Risks

1. ~~Qilin can scale fastest: total daily mint is `10 * N^2`.~~ Fixed: diminishing-returns formula caps per-owner payout, total mint grows ~linearly with N.
2. Bot-side salary and passive payouts bypass `economy_log`.
3. Gifts are still indirect value transfer through resale.
4. Cards now add more daily bonuses, but all new effects are capped by daily keys.
5. Scan attempts can convert activity into random value, so the cap `7` matters.
6. ~~Panda cashback + 60% resale could exceed item price for items priced ≤25★.~~ Fixed: cashback is now `min(10★, 40% of price)`, so buy+resell can never net a profit regardless of future item pricing.

## Required Follow-Up

1. Move bot `/award`, `/penalize`, `/зп`, Caishen, Qilin, NetWatch payouts to API or add `economy_log` writes.
2. ~~Decide a Qilin cap before trip launch.~~ Done — diminishing returns formula in `zhidao_bot_ready.py`.
3. Keep gift/contract monitoring enabled.
4. After server deploy, run `python3 -m py_compile /root/zhidao_api.py`.
5. Do one real Telegram smoke test for: diary rating, presence, shop purchase, gift, contract completion, raid.
