# 기억 통합 태스크 (주간)

{anima_name}, 일주일간의 기억을 정리할 시간입니다.

## 현재 knowledge 파일 (총 {total_knowledge_count}건)

{knowledge_files_list}

## 병합 후보 (유사 파일 쌍)

{merge_candidates}

## 중요한 제약 사항
- **이 작업은 반드시 직접 수행하세요(MUST)**. `delegate_task`, `submit_tasks`, `send_message`는 사용 금지. 기억 조작 도구만으로 작업을 완료하세요

## 작업 절차

### Step 1: 중복 파일 통합 (최우선 — MUST)

병합 후보가 제시된 경우, **모든 쌍에 대해** 통합을 수행하세요.
또한, 위 파일 목록을 확인하여 같은 주제를 다루는 중복 파일을 직접 찾으세요.

통합 절차:
1. `read_memory_file`로 양쪽 내용을 확인
2. 정보를 합쳐서 `write_memory_file`로 한쪽에 기록
3. 불필요해진 쪽을 `archive_memory_file`로 아카이브
4. `[IMPORTANT]` 태그가 있으면 통합 대상 파일에도 유지

- "나중에 통합" 또는 "복잡해서 보류"는 금지. 지금 여기서 완료하세요

### Step 2: [IMPORTANT] knowledge의 개념 승화

생성 후 30일 이상 경과한 `[IMPORTANT]` 태그 포함 knowledge/ 파일을 개념 통합합니다.

1. `search_memory`로 `[IMPORTANT]`가 포함된 knowledge/를 검색하고, 30일 이상된 것을 확인
2. 관련 주제별로 그룹화하여 각 그룹에서 추상적인 원칙을 추출
3. `concept-{theme}.md`로 생성 (본문 첫 부분에 `[IMPORTANT]` 추가)
4. 원본 파일에서 `[IMPORTANT]` 태그 제거 (파일 자체는 유지)

고립된 `[IMPORTANT]` 항목이나 30일 미만인 것은 스킵하세요.

### Step 3: procedure knowledge 정리

procedures/ 내의 파일을 확인하고:
- 오래된 절차 → 업데이트 또는 아카이브
- 유사한 절차 → 통합

### Step 4: 오래된 에피소드 압축

episodes/에 30일 이상 된 파일이 있으면:
- `[IMPORTANT]` 태그가 없는 것은 요점만 남기고 압축

### Step 5: knowledge 모순 해소

모순되는 knowledge 파일이 없는지 확인하고, 정확한 쪽을 유지하고 오래된 쪽을 아카이브하세요.

완료 후 실시 내용의 요약을 출력하세요 (통합한 쌍 수와 아카이브한 파일 수 포함).
