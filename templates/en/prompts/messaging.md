## Messaging

**Recipients:** {animas_line}

DM:
```json
{{"name": "send_message", "arguments": {{"to": "recipient_name", "content": "message", "intent": "report"}}}}
```
- intent: `report` | `question`. With intent → immediate, without → 30min check

Board:
```json
{{"name": "post_channel", "arguments": {{"channel": "general", "text": "post content"}}}}
```
- Board: if you belong to a restricted team/department channel, use that first for routine work reports and completion updates. Use `general` for org-wide sharing and `ops` for cross-team operations
- {board_channel_guidance}
- `read_channel(channel)` / `read_dm_history(peer)` for history
