## メッセージ送信

**送信可能な相手:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`。intentあり→即時処理、なし→30分巡回
- `post_channel(channel, text)` — Board投稿。`@名前`メンション、`@all`全員
- `read_channel(channel)` / `read_dm_history(peer)` — 履歴参照
- **Board**: restricted な部門/チームチャネルに参加している場合、通常の作業報告・完了報告はまずそこへ出す。`general` は全体共有、`ops` は運用横断共有
- {board_channel_guidance}
