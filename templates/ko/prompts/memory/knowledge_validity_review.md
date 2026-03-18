당신은 {anima_name}입니다. 오늘의 활동을 돌아보고, 다음 기존 knowledge/procedure 파일이 현재도 정확한지 자체 리뷰해 주세요.

【오늘의 에피소드 요약】
{episodes_summary}

【리뷰 대상 파일】
{review_files}

각 파일에 대해 다음 세 가지 중 하나로 판정해 주세요:
- **valid**: 내용이 현재도 정확하며 수정 불필요
- **stale**: 진부화됨 (해결된 문제를 미해결로 기술, 폐지된 절차, 변경된 사양 등)
- **needs_update**: 대체로 올바르지만, 오늘의 활동을 반영하여 부분적으로 업데이트 필요

답변은 아래 JSON 배열로만 출력해 주세요 (설명문은 불필요):
```json
[
  {{"file": "파일명", "verdict": "valid|stale|needs_update", "reason": "판정 이유 (1-2문장)", "correction": "stale/needs_update의 경우 수정 내용 (valid이면 null)"}}
]
```

판정 가이드라인:
- 오늘의 활동에서 해결된 문제가 "미해결"로 기술되어 있으면 stale
- 절차가 오늘의 경험과 모순되면 stale 또는 needs_update
- 정보가 오래되었지만 해가 없으면 valid (보수적으로 판정)
- 수정이 필요한 경우 correction에 구체적인 수정 텍스트를 기술
