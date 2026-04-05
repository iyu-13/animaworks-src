#!/bin/bash
# AnimaWorks ヘルスチェック
# - 全AnimaのActivity_logに(no response)が検出されたらSlackに通知
# - 直近35分以内のエントリを確認。通知済みフラグで重複送信を防ぐ（Anima別）
# - /home/deploy/.animaworks/animas/ 配下のディレクトリを自動検出（新Anima追加も自動対応）

ANIMAS_DIR="/home/deploy/.animaworks/animas"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 検出結果を格納する変数
ALERT_LINES=""
FLAGGED_ANIMAS=()

# 全Animaディレクトリをループ
for ANIMA_DIR in "${ANIMAS_DIR}"/*/; do
  ANIMA_NAME=$(basename "$ANIMA_DIR")
  LOG_DIR="${ANIMA_DIR}activity_log"
  LOGFILE="${LOG_DIR}/$(date +%Y-%m-%d).jsonl"
  FLAG_FILE="${ANIMA_DIR}shortterm/health_alert_sent_${ANIMA_NAME}.flag"

  # activity_logディレクトリが存在しないAnimaはスキップ
  if [ ! -d "$LOG_DIR" ]; then
    continue
  fi

  # 直近35分以内の(no response)件数と正常レスポンス件数を取得
  HEALTH_RESULT=$(python3 -c "
import sys, json
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(minutes=35)
no_resp = 0
ok_resp = 0
try:
    with open('${LOGFILE}') as f:
        for line in f:
            try:
                d = json.loads(line)
                ts_str = d.get('ts','')[:19]
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
                if d.get('type') != 'response_sent':
                    continue
                content = str(d.get('content',''))
                if content.strip() == '(no response)':
                    no_resp += 1
                else:
                    ok_resp += 1
            except:
                pass
except:
    pass
print(f'{no_resp} {ok_resp}')
" 2>/dev/null || echo "0 0")

  NO_RESP_COUNT=$(echo "$HEALTH_RESULT" | awk '{print $1}')
  OK_RESP_COUNT=$(echo "$HEALTH_RESULT" | awk '{print $2}')

  # 正常レスポンスが1件でもあれば、LLM接続自体は生きている → アラート不要
  if [ "$NO_RESP_COUNT" -gt 0 ] && [ "$OK_RESP_COUNT" -eq 0 ]; then
    # 既に通知済みなら重複送信しない（フラグが30分以内なら skip）
    if [ -f "$FLAG_FILE" ]; then
      FLAG_AGE=$(( $(date +%s) - $(date -r "$FLAG_FILE" +%s 2>/dev/null || echo 0) ))
      if [ "$FLAG_AGE" -lt 1800 ]; then
        continue
      fi
    fi

    # アラート行を追加
    ALERT_LINES="${ALERT_LINES}• ${ANIMA_NAME} で \`(no response)\` ${NO_RESP_COUNT}件\n"
    FLAGGED_ANIMAS+=("$ANIMA_NAME")
    touch "$FLAG_FILE"
  else
    # 正常時はフラグをリセット
    rm -f "$FLAG_FILE"
  fi
done

# アラートがあればまとめて1通のSlack通知を送信
if [ -n "$ALERT_LINES" ]; then
  /home/deploy/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "🔴 *AnimaWorks ヘルスアラート*

*検出:* LLM接続エラー（直近35分）
$(echo -e "${ALERT_LINES}")
*考えられる原因:*
• Claude Agent SDK の OAuth トークン無効化
• API キー未設定 / 期限切れ
• Anthropic サービス障害

*🕐 検出時刻:* ${TIMESTAMP}

対応が必要な場合は AnimaWorks の接続設定を確認してください 🙏" 2>/dev/null
fi
