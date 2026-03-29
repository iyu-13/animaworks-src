---
name: skill-creator
description: >-
  Markdown 스킬을 만드는 메타 스킬. SKILL.md frontmatter·본문과 Progressive Disclosure·create_skill 절차를 다룬다.
  Use when: 신규 스킬 추가, skill 도구용 기술 규칙 확인, references·templates 포함 생성이 필요할 때.
---

# skill-creator

## 스킬 파일 구조

스킬 파일은 YAML frontmatter와 Markdown 본문으로 구성됩니다.
frontmatter의 필수 필드는 `name`과 `description`입니다.
선택 필드: `allowed_tools` (허용 도구 목록), `tags` (분류 태그).

```yaml
---
name: skill_name
description: >-
  스킬 설명.
  「키워드1」「키워드2」
---
```

`description`은 스킬 발동을 결정하는 가장 중요한 필드입니다.
사용자의 메시지와 description이 매칭될 때만 본문이 시스템 프롬프트에 주입됩니다.
즉, description이 "주요 트리거 메커니즘"으로 기능합니다.

## description 작성법

### 핵심 규칙: 도메인 고유하고 구체적으로 작성

description은 벡터 검색(의미 유사도) 매칭에 사용됩니다.
**일반적이거나 추상적인 description은 다른 스킬과 오매칭을 일으킵니다.**
해당 스킬에 고유한 용어, 조작, 대상을 반드시 포함하세요.

**나쁜 예시 (일반적 → 오탐 유발)**:

```yaml
description: >-
  AnimaWorks 서버를 관리합니다. 코드 업데이트 후 리로드 및 시스템 상태 확인을 처리합니다.
```

→ "관리", "확인", "상태"는 너무 일반적이어서 관련 없는 메시지와도 매칭됩니다.

**좋은 예시 (도메인 고유 → 정확한 매칭)**:

```yaml
description: >-
  AnimaWorks 서버 프로세스 조작 스킬.
  코드 업데이트 후 핫 리로드(server reload), Anima 프로세스 재시작,
  서버 상태 확인(실행 중인 Anima 목록, 메모리 사용량)을 실행합니다.
  「리로드」「업데이트 반영」「시스템 상태」「서버 재시작」「프로세스 확인」
```

→ "핫 리로드", "server reload", "Anima 프로세스", "메모리 사용량"이 구체적인 어휘입니다.

### 기본 구조

1. **첫 문장**: **구체적인 대상과 조작**으로 스킬의 목적을 기술 ("~를 관리"가 아니라 "~의 핫 리로드, 재시작, 상태 확인")
2. **이후 문장**: 도구명, API명, 구체적인 절차 단계를 포함
3. **끝**: `「」` 형식으로 키워드를 나열

### description 구체성 점검

다음이 단독으로 나타나면 더 구체적인 표현으로 교체하세요:

| 피해야 할 표현 | 더 나은 표현 |
|--------------|------------|
| 관리를 수행 | 핫 리로드, 프로세스 재시작, 상태 확인 |
| 확인을 수행 | slack_search 도구로 DM 조회, 미읽음 확인 |
| 응답을 수행 | chatwork_search로 룸 미읽음 조회, 답장 전송 |
| 구조와 사용법 | RAG/Priming/Consolidation, 실행 모드(S/A/B) |
| 생성을 위한 메타 스킬 | YAML frontmatter 형식으로 생성, 「」키워드 설계 |

### 키워드 설계 팁

- 사용자가 자연스럽게 말할 짧은 구문(2~5글자) 선택
- 동의어와 변형 포함 (예: "정기 실행", "cron 설정", "스케줄")
- 영어 description의 경우 쉼표 구분이나 사용 사례 예시도 가능
- 키워드가 너무 많으면 오탐이 발생하므로 3~6개 정도로 유지
- 키워드를 도메인 고유하게 작성 ("확인"이 아니라 "cron 확인", "Slack 확인")

### 예시

```yaml
description: >-
  AnimaWorks cron 작업(APScheduler) 설정 및 관리 스킬.
  crontab 형식의 정기 태스크 추가, 편집, 삭제,
  다음 실행 시간 확인, 실행 로그 조회 절차를 제공합니다.
  「cron 설정」「정기 실행」「스케줄」「예약 태스크」「cron 확인」
```

## Progressive Disclosure

스킬 정보는 3단계로 공개됩니다.

| 레벨 | 내용 | 표시 시점 |
|------|------|----------|
| Level 1 | description | 항상 스킬 테이블에 표시. 스킬 선택 판단 재료 |
| Level 2 | body (본문) | description이 매칭되었을 때 시스템 프롬프트에 주입 |
| Level 3 | 외부 리소스 | 본문의 지시에 따라 필요 시 파일을 읽어들임 |

Level 1은 항상 컨텍스트를 소비하므로 description을 간결하게 유지하세요.
Level 2 본문에는 구체적인 절차를 기재하세요.
Level 3은 긴 참조 자료나 코드 예시를 외부 파일에 분리할 때 사용합니다.

## 생성 절차

### Step 1: 확인

사용자의 요구를 이해합니다. 다음을 확인하세요:

- 무엇을 자동화하거나 문서화하고 싶은지
- 개인 스킬인지 공통 스킬인지
- 트리거 키워드 (어떤 말로 발동시키고 싶은지)

### Step 2: 설계

다음을 결정합니다:

- **name**: 스킬명 (케밥 케이스, 예: `my-skill`)
- **description**: 트리거 텍스트와 키워드
- **body**: 섹션 구성

### Step 3: 생성

`create_skill` 도구를 사용하여 스킬을 생성합니다:

```
create_skill(skill_name="{name}", description="{description}", body="{body}")
```

공통 스킬의 경우:

```
create_skill(skill_name="{name}", description="{description}", body="{body}", location="common")
```

참고: `write_memory_file`로 기존 스킬을 편집할 수 있지만, 새 스킬 생성에는 `create_skill`을 사용하세요.
(`write_memory_file`의 플랫 형식 `skills/foo.md`로 생성한 파일은 스킬 도구가 해석할 수 없습니다.)

### Step 4: 확인

저장 후 다시 읽어서 내용을 검증합니다:

```
read_memory_file("skills/{name}.md")
```

## 체크리스트

저장 전에 다음을 확인하세요:

- [ ] YAML frontmatter가 `---`로 시작하고 `---`로 끝나는가
- [ ] `name` 필드가 있는가
- [ ] `description` 필드가 있는가
- [ ] description에 `「」` 키워드가 1개 이상 있는가
- [ ] **description이 도메인 고유하고 구체적인가** ("관리를 수행", "확인을 수행" 같은 일반적 표현 대신 도구명, 조작명, 대상을 명기)
- [ ] body에 구체적인 절차 단계가 있는가
- [ ] 구 형식 `## 개요` / `## 트리거 조건`을 사용하지 않는가
- [ ] `create_skill` 도구로 생성하는가 (`write_memory_file`의 플랫 형식은 스킬 도구가 해석 불가)

## 템플릿

다음을 시작점으로 사용하세요:

```markdown
---
name: {skill_name}
description: >-
  {구체적인 대상}의 {구체적인 조작} 스킬.
  {도구/API명}으로 {구체적인 절차 요약}을 실행합니다.
  「{도메인 고유 키워드 1}」「{도메인 고유 키워드 2}」「{도메인 고유 키워드 3}」
---

# {skill_name}

## 절차

1. ...
2. ...

## 주의사항

- ...
```

## 주의사항

- 스킬은 Markdown 절차서이며, Python 코드(도구)와는 다릅니다
- frontmatter 필수 필드: `name`과 `description`
- 선택 필드: `allowed_tools` (허용 도구 목록), `tags` (분류 태그)
- body가 약 150행을 넘지 않도록 하여 컨텍스트 압박을 방지하세요
- 외부 리소스 참조(Level 3)를 활용하여 본문을 간결하게 유지하세요
