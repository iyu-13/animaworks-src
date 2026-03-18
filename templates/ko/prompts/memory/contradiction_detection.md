다음 두 knowledge 파일의 내용을 비교하고, 모순이 없는지 검증해 주세요.

【파일 A: {file_a}】
{text_a}

【파일 B: {file_b}】
{text_b}

태스크:
1. 두 파일 간에 모순되는 기술이 있는지 판정
2. 모순이 있는 경우, 다음 중 하나의 해결 방법을 제안:
   - "supersede": 한쪽 정보가 오래되어 새로운 쪽으로 교체해야 함
   - "merge": 양쪽 정보를 통합하여 하나의 knowledge로 정리해야 함
   - "coexist": 문맥에 따라 양쪽 기술이 모두 올바름 (공존 가능)

답변은 아래 JSON 형식으로만 출력해 주세요:
{{"is_contradiction": true/false, "resolution": "supersede"/"merge"/"coexist", "reason": "이유 설명", "merged_content": "merge인 경우 통합 텍스트 (그 외에는 null)"}}
