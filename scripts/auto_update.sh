#!/bin/bash
# AnimaWorks 本家リポジトリの変更を取り込み、fork(iyu13)に同期するスクリプト
# - git rebase でyの独自変更を保持しつつupstream変更を取り込む
# - rebase後は iyu13(fork) にpushしてVPSローカルと常に一致させる
# - コンフリクト時はrebaseを中断（手動対応が必要）

LOG="/home/deploy/.animaworks/animas/leader/shortterm/auto_update.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

cd /home/deploy/animaworks

echo "[$TIMESTAMP] auto_update start" >> "$LOG"

# (2) slack_sdk import可否確認
if python3 -c "from slack_sdk import WebClient" 2>/dev/null; then
  echo "[$TIMESTAMP] slack_sdk available" >> "$LOG"
else
  echo "[$TIMESTAMP] WARNING: slack_sdk not available, Slack notifications may fail" >> "$LOG"
fi

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

# (1) git config チェック: rebase前にuser.emailが未設定なら自動設定
if [ -z "$(git config user.email)" ]; then
  git config user.email "anima@animaworks.local"
  git config user.name "AnimaWorks"
  echo "[$TIMESTAMP] git config user.email/name set automatically" >> "$LOG"
fi

# yの独自変更を保持しつつ取り込む
if ! git rebase origin/main >> "$LOG" 2>&1; then
  echo "[$TIMESTAMP] rebase conflict! aborting..." >> "$LOG"
  git rebase --abort >> "$LOG" 2>&1
  /home/deploy/animaworks/.venv/bin/animaworks send mio y "AnimaWorksの自動アップデートでコンフリクトが発生しました。手動対応が必要です。ログ: $LOG" --intent report
  # Slack #ops-logs にもコンフリクト通知
  SLACK_TOKEN_CONFLICT=$(python3 -c "import json; d=json.load(open('/home/deploy/.animaworks/shared/credentials.json')); print(d.get('SLACK_BOT_TOKEN',''))" 2>/dev/null)
  if [ -n "$SLACK_TOKEN_CONFLICT" ]; then
    if /home/deploy/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "⚠️ *AnimaWorks* 自動アップデート失敗

*原因:* rebaseコンフリクト（手動対応が必要）
*🕐 時刻:* ${TIMESTAMP}
*📋 ログ:* \`${LOG}\`

yさん、手動でコンフリクト解消をお願いします 🙏" >> "$LOG" 2>&1; then
      echo "[$TIMESTAMP] slack conflict notification sent" >> "$LOG"
    else
      echo "[$TIMESTAMP] ERROR: slack conflict notification failed (exit $?)" >> "$LOG"
      # (3) Slack通知失敗時のcall_human fallback
      /home/deploy/animaworks/.venv/bin/animaworks-tool call_human "AutoUpdate: rebaseコンフリクト" "AnimaWorksの自動アップデートでrebaseコンフリクトが発生しました。手動対応が必要です。時刻: ${TIMESTAMP} ログ: ${LOG}" --priority high 2>/dev/null || true
    fi
  fi
  exit 1
fi

echo "[$TIMESTAMP] rebase done" >> "$LOG"

if [ "$STASHED" = "1" ]; then
  echo "[$TIMESTAMP] restoring stash..." >> "$LOG"
  if ! git stash pop >> "$LOG" 2>&1; then
    echo "[$TIMESTAMP] stash pop failed, manual recovery needed" >> "$LOG"
    /home/deploy/animaworks/.venv/bin/animaworks send mio y "【AnimaWorks自動アップデート】rebaseは成功しましたが、stash popに失敗しました。手動確認が必要です。ログ: $LOG" --intent report
  fi
fi

# 取り込んだコミット一覧を取得
COMMITS=$(git log --oneline origin/main~${AHEAD}..origin/main 2>/dev/null || echo "(コミット一覧取得失敗)")

# fork(iyu13)にpushしてVPSローカルと同期
echo "[$TIMESTAMP] pushing to iyu13 fork..." >> "$LOG"
if ! git push iyu13 main --force-with-lease >> "$LOG" 2>&1; then
  echo "[$TIMESTAMP] push to iyu13 failed!" >> "$LOG"
  /home/deploy/animaworks/.venv/bin/animaworks send mio y "【AnimaWorks自動アップデート】rebaseは成功しましたが、forkへのpushが失敗しました。手動で確認してください。ログ: $LOG" --intent report
  # push失敗時もSlack通知
  SLACK_TOKEN_PUSH=$(python3 -c "import json; d=json.load(open('/home/deploy/.animaworks/shared/credentials.json')); print(d.get('SLACK_BOT_TOKEN',''))" 2>/dev/null)
  if [ -n "$SLACK_TOKEN_PUSH" ]; then
    if /home/deploy/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "⚠️ *AnimaWorks* 自動アップデート: forkへのpush失敗

*原因:* \`git push iyu13 main\` が失敗
*🕐 時刻:* ${TIMESTAMP}
*📋 ログ:* \`${LOG}\`

yさん、手動確認をお願いします 🙏" >> "$LOG" 2>&1; then
      echo "[$TIMESTAMP] slack push-failure notification sent" >> "$LOG"
    else
      echo "[$TIMESTAMP] ERROR: slack push-failure notification also failed" >> "$LOG"
      # (3) Slack通知失敗時のcall_human fallback
      /home/deploy/animaworks/.venv/bin/animaworks-tool call_human "AutoUpdate: forkへのpush失敗" "AnimaWorksの自動アップデートでforkへのpushが失敗しました。Slack通知も失敗しています。時刻: ${TIMESTAMP} ログ: ${LOG}" --priority high 2>/dev/null || true
    fi
  fi
  exit 1
fi

echo "[$TIMESTAMP] push to iyu13 done" >> "$LOG"

# yに通知（restartは手動で行ってもらう）
/home/deploy/animaworks/.venv/bin/animaworks send mio y "【AnimaWorks自動アップデート完了】本家から${AHEAD}件のコミットを取り込み、forkにも反映しました。反映するにはAnimaWorksの再起動が必要です。
---
${COMMITS}" --intent report

# Slack #ops-logs にも通知
SLACK_TOKEN=$(python3 -c "import json; d=json.load(open('/home/deploy/.animaworks/shared/credentials.json')); print(d.get('SLACK_BOT_TOKEN',''))" 2>/dev/null)
if [ -n "$SLACK_TOKEN" ]; then
  COMMIT_BULLETS=$(echo "$COMMITS" | sed 's/^[a-f0-9]* /• /')
  SLACK_MSG="🔄 *AnimaWorks* 自動アップデート完了

*📋 取り込んだ変更（${AHEAD}コミット）:*
${COMMIT_BULLETS}

*🕐 時刻:* ${TIMESTAMP}

⚠️ *反映にはAnimaWorksの再起動が必要です。*
yさん、再起動をお願いします 🙏"
  if /home/deploy/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "$SLACK_MSG" >> "$LOG" 2>&1; then
    echo "[$TIMESTAMP] slack notification sent" >> "$LOG"
  else
    echo "[$TIMESTAMP] ERROR: slack notification failed (exit $?)" >> "$LOG"
    # (3) Slack通知失敗時のcall_human fallback
    /home/deploy/animaworks/.venv/bin/animaworks-tool call_human "AutoUpdate完了(Slack通知失敗)" "AnimaWorks自動アップデートは完了しましたが、Slack通知が失敗しました。${AHEAD}件取り込み済み。時刻: ${TIMESTAMP} ログ: ${LOG}" 2>/dev/null || true
  fi
fi

echo "[$TIMESTAMP] notification sent to y" >> "$LOG"
