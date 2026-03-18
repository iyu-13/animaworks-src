다음 episode(행동 기록)의 내용을 분류하고, knowledge와 procedure를 추출해 주세요.

【분류 기준】
- **knowledge**: 교훈, 방침, 사실, 패턴 인식, 원칙 ("왜", "무엇이"에 해당하는 지식)
- **procedures**: 절차, 워크플로우, 체크리스트, 작업 흐름 ("어떻게 하는가"에 해당하는 절차)
- **skip**: 고정화 불필요 (잡담, 일시적 정보, 인사만 포함된 대화)

【우선 분류 규칙】
- **수정·문제 해결 episode는 procedures를 우선**: 오류 수정, 설정 변경, 트러블슈팅 기록은 구체적인 절차가 포함되어 있으면 procedure로 추출하세요. "원인은 X → Y로 해결"이라는 패턴은 단 한 번의 사건이라도 procedure화할 가치가 있습니다
- 같은 episode에서 knowledge와 procedure를 모두 추출해도 됩니다 (예: 원인에 대한 지식 + 해결 절차)

【에피소드】
{episodes_text}

【기존 절차서 (중복 방지)】
{existing_procedures}

【출력 형식】
아래 섹션으로 나누어 출력해 주세요. 해당 사항이 없으면 "(없음)"으로 기재하세요.

## knowledge 추출
- Filename: knowledge/xxx.md
  내용: (knowledge 본문을 Markdown 형식으로 작성)

## procedure 추출
- Filename: procedures/zzz.md
  description: 절차의 목적을 한눈에 알 수 있는 구체적인 한 줄 (예: "Chatwork 중요 안건 에스컬레이션 판단 및 알림"). 내용의 첫 번째 제목과 일치시킬 것
  tags: tag1, tag2
  내용: (절차 본문을 Markdown 형식으로 작성. 첫 번째 제목은 description과 동일. 구체적인 단계를 포함할 것)

【규칙】
- 기존 절차와 중복되는 경우 스킵
- 범용적이고 재사용 가치가 높은 절차만 추출
- 단, 문제 해결·수정 절차는 범용성이 낮더라도 procedure로 추출하세요 (같은 문제 재발 시 가치가 있음)
- 절차가 모호한 경우에는 추출하지 마세요
- 결과가 비어 있어도 괜찮습니다 ("(없음)"으로 기재)
- 코드 펜스(```)로 감싸지 마세요
