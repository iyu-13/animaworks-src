#!/bin/bash
# AnimaWorks 本家リポジトリの変更を取り込み、fork(iyu13)に同期するスクリプト
# - git rebase でyの独自変更を保持しつつupstream変更を取り込む
# - rebase後は iyu13(fork) にpushしてVPSローカルと常に一致させる
# - コンフリクト時はrebaseを中断（手動対応が必要）

LOG="/root/.animaworks/animas/leader/shortterm/auto_update.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

cd ~/animaworks

echo "[$TIMESTAMP] auto_update start" >> "$LOG"

# upstream の変更を取得
git fetch origin >> "$LOG" 2>&1

# originの方がローカルより進んでいるか確認
AHEAD=$(git rev-list HEAD..origin/main --count)

if [ "$AHEAD" -eq 0 ]; then
  echo "[$TIMESTAMP] already up to date, skipping rebase" >> "$LOG"
  exit 0
fi

echo "[$TIMESTAMP] ${AHEAD} new commit(s) found, rebasing..." >> "$LOG"

# 自動生成ファイル(uv.lock)の変更をリセット（rebaseの邪魔になるため）
git checkout -- uv.lock 2>/dev/null || true

# 未コミット変更があればstashで退避（uv.lock等の自動生成ファイル対策）
STASHED=0
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "[$TIMESTAMP] uncommitted changes found, stashing..." >> "$LOG"
  git stash push -m "auto_update pre-rebase stash" >> "$LOG" 2>&1
  STASHED=1
fi

# yの独自変更を保持しつつ取り込む
if ! git rebase origin/main >> "$LOG" 2>&1; then
  echo "[$TIMESTAMP] rebase conflict! aborting..." >> "$LOG"
  git rebase --abort >> "$LOG" 2>&1
  /root/animaworks/.venv/bin/animaworks send leader y "AnimaWorksの自動アップデートでコンフリクトが発生しました。手動対応が必要です。ログ: $LOG" --intent report
  # Slack #ops-logs にもコンフリクト通知
  SLACK_TOKEN_CONFLICT=$(python3 -c "import json; d=json.load(open('/root/.animaworks/shared/credentials.json')); print(d.get('SLACK_BOT_TOKEN',''))" 2>/dev/null)
  if [ -n "$SLACK_TOKEN_CONFLICT" ]; then
    /root/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "⚠️ *AnimaWorks* 自動アップデート失敗

*原因:* rebaseコンフリクト（手動対応が必要）
*🕐 時刻:* ${TIMESTAMP}
*📋 ログ:* \`${LOG}\`

yさん、手動でコンフリクト解消をお願いします 🙏" >> "$LOG" 2>&1
    echo "[$TIMESTAMP] slack conflict notification sent" >> "$LOG"
  fi
  exit 1
fi

echo "[$TIMESTAMP] rebase done" >> "$LOG"

if [ "$STASHED" = "1" ]; then
  echo "[$TIMESTAMP] restoring stash..." >> "$LOG"
  if ! git stash pop >> "$LOG" 2>&1; then
    echo "[$TIMESTAMP] stash pop failed, manual recovery needed" >> "$LOG"
    /root/animaworks/.venv/bin/animaworks send leader y "【AnimaWorks自動アップデート】rebaseは成功しましたが、stash popに失敗しました。手動確認が必要です。ログ: $LOG" --intent report
  fi
fi

# 取り込んだコミット一覧を取得
COMMITS=$(git log --oneline origin/main~${AHEAD}..origin/main 2>/dev/null || echo "(コミット一覧取得失敗)")

# fork(iyu13)にpushしてVPSローカルと同期
echo "[$TIMESTAMP] pushing to iyu13 fork..." >> "$LOG"
if ! git push iyu13 main --force-with-lease >> "$LOG" 2>&1; then
  echo "[$TIMESTAMP] push to iyu13 failed!" >> "$LOG"
  /root/animaworks/.venv/bin/animaworks send leader y "【AnimaWorks自動アップデート】rebaseは成功しましたが、forkへのpushが失敗しました。手動で確認してください。ログ: $LOG" --intent report
  exit 1
fi

echo "[$TIMESTAMP] push to iyu13 done" >> "$LOG"

# yに通知（restartは手動で行ってもらう）
/root/animaworks/.venv/bin/animaworks send leader y "【AnimaWorks自動アップデート完了】本家から${AHEAD}件のコミットを取り込み、forkにも反映しました。反映するにはAnimaWorksの再起動が必要です。
---
${COMMITS}" --intent report

# Slack #ops-logs にも通知
SLACK_TOKEN=$(python3 -c "import json; d=json.load(open('/root/.animaworks/shared/credentials.json')); print(d.get('SLACK_BOT_TOKEN',''))" 2>/dev/null)
if [ -n "$SLACK_TOKEN" ]; then
  COMMIT_BULLETS=$(echo "$COMMITS" | sed 's/^[a-f0-9]* /• /')
  SLACK_MSG="🔄 *AnimaWorks* 自動アップデート完了

*📋 取り込んだ変更（${AHEAD}コミット）:*
${COMMIT_BULLETS}

*🕐 時刻:* ${TIMESTAMP}

⚠️ *反映にはAnimaWorksの再起動が必要です。*
yさん、再起動をお願いします 🙏"
  /root/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "$SLACK_MSG" >> "$LOG" 2>&1
  echo "[$TIMESTAMP] slack notification sent" >> "$LOG"
fi

echo "[$TIMESTAMP] notification sent to y" >> "$LOG"
