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
REBASE_OUTPUT=$(git rebase origin/main 2>&1)
REBASE_EXIT=$?
echo "$REBASE_OUTPUT" >> "$LOG"

if [ $REBASE_EXIT -ne 0 ]; then
  echo "[$TIMESTAMP] rebase conflict! aborting..." >> "$LOG"
  git rebase --abort >> "$LOG" 2>&1

  # === 原因診断 ===
  CAUSE=""
  DETAIL=""
  RECOMMENDATION=""

  # (A) 未追跡ファイルの衝突を検出
  UNTRACKED_CONFLICTS=$(echo "$REBASE_OUTPUT" | grep -A1 "untracked working tree files" | grep -v "untracked\|Please\|Aborting\|error" | sed 's/^\t//' | xargs)
  if [ -n "$UNTRACKED_CONFLICTS" ]; then
    CAUSE="未追跡（未コミット）ファイルがupstreamと衝突"
    DETAIL="*衝突ファイル:*"
    for f in $UNTRACKED_CONFLICTS; do
      # 本家に同じファイルがあるか確認
      if git show origin/main:"$f" >/dev/null 2>&1; then
        LOCAL_LINES=$(wc -l < "$f" 2>/dev/null || echo "?")
        UPSTREAM_LINES=$(git show origin/main:"$f" 2>/dev/null | wc -l)
        DETAIL="${DETAIL}
• \`$f\` — ローカル:${LOCAL_LINES}行 / 本家:${UPSTREAM_LINES}行（本家にも存在）"
      else
        DETAIL="${DETAIL}
• \`$f\` — ローカルのみ（本家には未存在）"
      fi
    done
    RECOMMENDATION="*推奨対応:*
1. 本家にも存在するファイル → ローカル版を削除（本家版が上位互換の可能性大）
2. ローカルのみのファイル → \`.gitignore\` に追加するか、コミットする
3. 対処後 \`git rebase origin/main\` → \`git push iyu13 main --force-with-lease\`"
  fi

  # (B) コミット同士の衝突を検出
  if [ -z "$CAUSE" ]; then
    CONFLICT_FILES=$(echo "$REBASE_OUTPUT" | grep "^CONFLICT" | sed 's/CONFLICT ([^)]*): //' | head -5)
    if [ -n "$CONFLICT_FILES" ]; then
      CAUSE="ローカルコミットとupstreamコミットがコード競合"
      DETAIL="*競合ファイル:*
$(echo "$CONFLICT_FILES" | sed 's/^/• /')"
      RECOMMENDATION="*推奨対応:*
1. 各ファイルの差分を確認し、ローカル変更が不要なら本家に合わせる
2. 必要な変更なら手動でマージする
3. 対処後 \`git rebase --continue\` → \`git push iyu13 main --force-with-lease\`"
    fi
  fi

  # (C) その他
  if [ -z "$CAUSE" ]; then
    CAUSE="不明（ログを確認してください）"
    DETAIL="*rebase出力:*
\`\`\`$(echo "$REBASE_OUTPUT" | tail -5)\`\`\`"
    RECOMMENDATION="*推奨対応:* ログを確認し、手動で対処してください"
  fi

  # ローカル独自コミット一覧
  LOCAL_COMMITS=$(git log --oneline origin/main..HEAD 2>/dev/null | head -10)
  LOCAL_COUNT=$(git log --oneline origin/main..HEAD 2>/dev/null | wc -l)

  # 未追跡ファイル一覧（.gitignore除外後）
  UNTRACKED_ALL=$(git ls-files --others --exclude-standard 2>/dev/null | head -10)

  /home/deploy/animaworks/.venv/bin/animaworks send mio y "AnimaWorksの自動アップデートでコンフリクトが発生しました。診断結果付きで報告します。ログ: $LOG" --intent report

  # Slack #ops-logs に診断付き通知
  SLACK_TOKEN_CONFLICT=$(python3 -c "import json; d=json.load(open('/home/deploy/.animaworks/shared/credentials.json')); print(d.get('SLACK_BOT_TOKEN',''))" 2>/dev/null)
  if [ -n "$SLACK_TOKEN_CONFLICT" ]; then
    SLACK_DIAG="⚠️ *AnimaWorks* 自動アップデート失敗

*🔍 原因:* ${CAUSE}

${DETAIL}

*📦 ローカル独自コミット（${LOCAL_COUNT}件）:*
$(echo "$LOCAL_COMMITS" | sed 's/^/• /')

*📄 未追跡ファイル:*
$(echo "${UNTRACKED_ALL:-（なし）}" | sed 's/^/• /')

${RECOMMENDATION}

*🕐 時刻:* ${TIMESTAMP}"

    if /home/deploy/animaworks/.venv/bin/animaworks-tool slack send "#ops-logs" "$SLACK_DIAG" >> "$LOG" 2>&1; then
      echo "[$TIMESTAMP] slack conflict notification sent (with diagnostics)" >> "$LOG"
    else
      echo "[$TIMESTAMP] ERROR: slack conflict notification failed (exit $?)" >> "$LOG"
      # (3) Slack通知失敗時のcall_human fallback
      /home/deploy/animaworks/.venv/bin/animaworks-tool call_human "AutoUpdate: rebaseコンフリクト" "原因: ${CAUSE} / 時刻: ${TIMESTAMP} / ログ: ${LOG}" --priority high 2>/dev/null || true
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
