#!/bin/bash
# AnimaWorks ヘルスチェック
# - activity_logに(no response)が検出されたらSlackに通知
# - 直近35分以内のエントリを確認。通知済みフラグで重複送信を防ぐ

LOG_DIR="/root/.animaworks/animas/leader/activity_log"
FLAG_FILE="/root/.animaworks/animas/leader/shortterm/health_alert_sent.flag"
LOGFILE="${LOG_DIR}/$(date +%Y-%m-%d).jsonl"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 直近35分以内の(no response)件数を取得
NO_RESP_COUNT=$(python3 -c "
import sys, json
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(minutes=35)
count = 0
try:
    with open('${LOGFILE}') as f:
        for line in f:
            try:
                d = json.loads(line)
                ts_str = d.get('ts','')[:19]
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                # response_sent タイプで内容が (no response) のものだけを対象にする
                if d.get('type') != 'response_sent':
                    continue
                content = str(d.get('content',''))
                if ts >= cutoff and content.strip() == '(no response)':
                    count += 1
            except:
                pass
except:
    pass
print(count)
" 2>/dev/null || echo "0")

if [ "$NO_RESP_COUNT" -gt 0 ]; then
  # 既に通知済みなら重複送信しない（フラグが30分以内なら skip）
  if [ -f "$FLAG_FILE" ]; then
    FLAG_AGE=$(( $(date +%s) - $(date -r "$FLAG_FILE" +%s 2>/dev/null || echo 0) ))
    if [ "$FLAG_AGE" -lt 1800 ]; then
      exit 0
    fi
  fi

  # Slack通知
  /root/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "🔴 *AnimaWorks ヘルスアラート*

*検出:* LLM接続エラー（\`(no response)\` が直近35分で ${NO_RESP_COUNT}件）

*考えられる原因:*
• Claude Agent SDK の OAuth トークン無効化
• API キー未設定 / 期限切れ
• Anthropic サービス障害

*🕐 検出時刻:* ${TIMESTAMP}

対応が必要な場合は AnimaWorks の接続設定を確認してください 🙏" 2>/dev/null

  touch "$FLAG_FILE"
else
  # 正常時はフラグをリセット
  rm -f "$FLAG_FILE"
fi
