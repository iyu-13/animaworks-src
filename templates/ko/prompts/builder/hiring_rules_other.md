## 채용 규칙

새로운 Anima를 채용할 때는 아래 절차를 따르세요.
identity.md 등의 파일을 수동으로 개별 생성하지 마세요.

1. 캐릭터 시트를 하나의 Markdown 파일로 작성
   - 필수 섹션: `## Basic Information`, `## Personality`, `## Role and Action Guidelines`
2. Bash에서 다음 명령을 실행:
   ```
   animaworks anima create --from-md <캐릭터_시트_경로> --supervisor $(basename $ANIMAWORKS_ANIMA_DIR)
   ```
3. 서버의 Reconciliation이 자동으로 새 Anima를 감지하고 시작합니다
