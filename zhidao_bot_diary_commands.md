# ZHIDAO Bot — Diary Commands Proposal

## Recommendation

Yes, add bot commands for the diary, but keep them minimal.

Do not try to turn the bot into a full diary editor.
The diary itself should remain inside the Mini App UI.

Use the bot only for fast admin actions.

## Good commands to add now

### `/diary_status YYYY-MM-DD`

Purpose:
- show admin summary for one date
- who filled the diary
- who submitted it
- who is still missing
- which entries already have scores

Suggested backend call:
- `GET /api/diary/admin/overview?entry_date=YYYY-MM-DD`

### `/diary_score TELEGRAM_ID YYYY-MM-DD LESSON_SCORE DIARY_SCORE`

Purpose:
- quickly put two scores without opening the full web interface
- useful in field conditions

Suggested backend call:
- `POST /api/diary/score`

Payload:
```json
{
  "telegram_id": 123456789,
  "entry_date": "2026-07-05",
  "lesson_score": "5/5",
  "diary_score": "4/5"
}
```

### `/diary_lock TELEGRAM_ID YYYY-MM-DD`

Purpose:
- lock one day after review
- prevent later edits

Suggested backend call:
- `POST /api/diary/lock`

Payload:
```json
{
  "telegram_id": 123456789,
  "entry_date": "2026-07-05",
  "locked": true
}
```

### `/diary_unlock TELEGRAM_ID YYYY-MM-DD`

Purpose:
- reopen a day if something needs fixing

Suggested backend call:
- `POST /api/diary/lock`

Payload:
```json
{
  "telegram_id": 123456789,
  "entry_date": "2026-07-05",
  "locked": false
}
```

## Commands I would NOT add yet

### Full text editing in bot

Bad fit because:
- too much text
- easy to make mistakes
- hard to review
- terrible UX for 15 word rows

### Entering all vocabulary rows in bot

Also bad fit.
This belongs in the Mini App.

### Long comment workflows in bot

Possible later, but not first.
Start with fast scores and lock/unlock only.

## Best division of responsibilities

Mini App:
- child writes diary
- child edits words
- child writes daily text
- adults can later review in a proper UI

Bot:
- admins check completion summary
- admins quickly set scores
- admins lock or unlock entries

## Practical conclusion

Yes, bot commands are worth adding.

But only these 3-4 admin shortcuts:
- `/diary_status`
- `/diary_score`
- `/diary_lock`
- `/diary_unlock`

Everything else should stay in the Mini App.
