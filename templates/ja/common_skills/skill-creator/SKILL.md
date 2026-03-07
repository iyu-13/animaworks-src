---
name: skill-creator
description: >-
  Markdownスキルをディレクトリ構造で作成するメタスキル。
  create_skillツールでSKILL.md（frontmatter + 本文）を生成し、
  オプションでreferences/やtemplates/にファイルを配置する。
  description記述ルール、「」キーワード設計、Progressive Disclosure構造を提供する。
  「スキル作成」「スキルを作りたい」「新しいスキル」「手順書を作成」「スキルファイル」
---

# skill-creator

## スキルのディレクトリ構造

スキルは**ディレクトリ構造**で管理される（フラットな単一ファイルではない）。

| 種別 | パス |
|------|------|
| 個人スキル | `skills/{name}/SKILL.md` |
| 共通スキル | `common_skills/{name}/SKILL.md` |

`create_skill` ツールは以下を生成する:

- `{name}/SKILL.md` — メインのスキルファイル（YAMLフロントマター + Markdown本文）
- `{name}/references/` — 任意。参照資料（例: `description_guide.md`）
- `{name}/templates/` — 任意。テンプレートファイル群

## スキルファイルの構造

SKILL.md はYAMLフロントマターとMarkdown本文で構成される。
フロントマターには `name` と `description` を必須フィールドとして記載する。
任意フィールドとして `allowed_tools`（許可ツールリスト）も使用可能。

```yaml
---
name: スキル名
description: >-
  スキルの説明。
  「キーワード1」「キーワード2」
---
```

`description` はスキルの発動を決定する最重要フィールドである。
ユーザーのメッセージと description の内容がマッチした場合にのみ、本文がシステムプロンプトに注入される。
つまり description が「主要なトリガー機構」として機能する。

**descriptionの詳細な書き方**（具体化チェック、キーワード設計など）は `references/description_guide.md` を参照。

## Progressive Disclosure（段階的開示）

スキルの情報は3段階で開示される。

| Level | 内容 | 表示タイミング |
|-------|------|----------------|
| Level 1 | description | 常にスキルテーブルに表示。スキル選択の判断材料 |
| Level 2 | body（本文） | descriptionがマッチした時にシステムプロンプトに注入 |
| Level 3 | 外部リソース | 本文中の指示に従い、必要時に `references/` 内のファイルを読み込む |

Level 1 は常にコンテキストを消費するため、descriptionは簡潔に保つ。
Level 2 の本文には具体的な手順を記載する。
Level 3 は長大な参照資料やコード例を `references/` に分離する場合に使う。

## 作成手順

### Step 1: ヒアリング

ユーザーの要求を理解する。以下を確認する:

- 何を自動化・手順化したいか
- 対象は個人スキルか共通スキルか
- どのような言葉で発動させたいか（トリガーキーワード）

### Step 2: 設計

以下を決定する:

- **name**: スキル名（ケバブケース、例: `my-skill`）
- **description**: トリガーとなる説明文とキーワード（`references/description_guide.md` を参照）
- **body**: 手順の構成（セクション分け）
- **references** / **templates**: 必要なら外部ファイルの設計

### Step 3: 作成

`create_skill` ツールでスキルをディレクトリ構造として作成する。

**基本（個人スキル）**:

```
create_skill(skill_name="{name}", description="{description}", body="{body}")
```

**共通スキル**:

```
create_skill(skill_name="{name}", description="{description}", body="{body}", location="common")
```

**references と templates を含める場合**:

```
create_skill(
  skill_name="{name}",
  description="{description}",
  body="{body}",
  location="personal",
  references=[
    {"filename": "description_guide.md", "content": "..."},
  ],
  templates=[
    {"filename": "skill_template.md", "content": "..."},
  ],
  allowed_tools=["read_memory_file", "write_memory_file"]
)
```

| パラメータ | 必須 | 説明 |
|-----------|------|------|
| skill_name | ✓ | スキル名（ケバブケース） |
| description | ✓ | frontmatter description（トリガーキーワード含む） |
| body | ✓ | SKILL.md本文（Markdown） |
| location | | `personal`（デフォルト）または `common` |
| references | | `references/` に配置するファイル群。`[{filename, content}, ...]` |
| templates | | `templates/` に配置するファイル群。`[{filename, content}, ...]` |
| allowed_tools | | frontmatter の allowed_tools（任意） |

※ 新規作成には必ず `create_skill` を使うこと。`write_memory_file` で単一ファイルを作っても、skill ツールは `{name}/SKILL.md` のディレクトリ構造を期待するため参照できない。

テンプレートは `templates/skill_template.md` を参照。

### Step 4: 確認

個人スキルの場合、保存後に読み直して内容を検証する:

```
read_memory_file(path="skills/{name}/SKILL.md")
```

共通スキルは skill ツールで一覧に表示されれば作成成功。

## チェックリスト

保存前に以下を確認する:

- [ ] `---` で始まり `---` で閉じるYAMLフロントマターがある
- [ ] `name` フィールドがある
- [ ] `description` フィールドがある
- [ ] descriptionに `「」` キーワードが1つ以上ある
- [ ] **descriptionがドメイン固有で具体的**（「管理を行う」「確認する」のような汎用表現を避け、ツール名・操作名・対象を明記）
- [ ] bodyに具体的な手順が記載されている
- [ ] `## 概要` / `## 発動条件` の旧形式を使っていない
- [ ] `create_skill` ツールで作成している（ディレクトリ構造 `{name}/SKILL.md` が必須）

## テンプレート

`templates/skill_template.md` をコピーして使用する。または以下を参照:

```markdown
---
name: {スキル名}
description: >-
  {具体的な対象}の{具体的な操作}スキル。
  {使用するツール名/API名}で{具体的な手順の概要}を実行する。
  「{ドメイン固有キーワード1}」「{ドメイン固有キーワード2}」「{ドメイン固有キーワード3}」
---

# {スキル名}

## 手順

1. ...
2. ...

## 注意事項

- ...
```

## 注意事項

- スキルはMarkdown手順書であり、Pythonコード（ツール）とは異なる
- フロントマターの必須フィールドは `name` と `description`
- 任意フィールド: `allowed_tools`（許可ツールリスト）
- bodyが長くなりすぎるとコンテキストを圧迫するため、150行以内を目安にする
- 外部リソース参照（Level 3）は `references/` を活用して本文を簡潔に保つ
