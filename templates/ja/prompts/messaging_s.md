## メッセージ送信

**送信可能な相手:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`。intentあり→即時処理、なし→30分巡回
- `post_channel(channel, text)` — Board投稿。`@名前`メンション、`@all`全員
- `read_channel(channel)` / `read_dm_history(peer)` — 履歴参照
- **Board**: `general`(全社), `ops`(運用)。全体共有・3人以上通知はBoard、個別はDM
