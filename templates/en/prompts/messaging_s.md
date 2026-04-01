## Messaging

**Recipients:** {animas_line}

- `send_message(to, content, intent)` — intent: `report` | `question`. With intent → immediate, without → 30min check
- `post_channel(channel, text)` — Board post. `@name` mention, `@all` everyone
- `read_channel(channel)` / `read_dm_history(peer)` — read history
- **Board**: if you belong to a restricted team/department channel, use that first for routine work reports and completion updates. Use `general` for org-wide sharing and `ops` for cross-team operations
- {board_channel_guidance}
