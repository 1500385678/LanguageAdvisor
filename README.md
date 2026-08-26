# LanguageAdvisor

> 13-语言-Language 行业 Web 项目 · 内部代号 LanguageAdvisor

## 项目说明
基于张勇的 36 行业架构,LanguageAdvisor 是 语言-Language 行业的 Web 端顾问产品。

## 同步
- GitHub: https://github.com/1500385678/LanguageAdvisor
- Gitee: https://gitee.com/architectzy/LanguageAdvisor

## 自动化
- T4 每日 02:00 检查项目并更新开发计划
- T5 每日 03:00 完成小步开发并 commit + push

## 目录结构

```
LanguageWeb/
├── README.md                  # 本文件
├── 项目开发计划.md              # 大计划(v1.0,Phase 0-4)
├── Inspiration/               # AI 写的技术架构/方案备查档案(给 AI 读,不入 Defense)
├── scripts/                   # 数据解析与转换脚本(纯 stdlib)
│   ├── md_to_json.py          # 语法 markdown → JSON(按 ##/### 切分)
│   └── csv_to_json.py         # 词表 CSV → JSON(归一化到 vocab schema)
├── data/
│   └── schema/                # JSON Schema 定义(数据入库前必校验)
│       ├── vocab.schema.json  # 词条 schema(对应 §4.3 vocab 表)
│       └── scene.schema.json  # 场景 schema(预留,场景库任务时启用)
├── 词表/                       # 英/日/法/西 主流词表 CSV(待建)
├── 语法/                       # 10 种语言核心语法 markdown(待建)
├── 场景语料/                   # 20+ 场景对话 JSON(待建)
└── 翻译规则/                   # 中英/中日思维差异(待建)
```

## Inspiration 目录说明

`Inspiration/` 收**给 AI 读的备查档案**(技术架构草稿、模型对比、外部研究综述),与项目根目录的 `Mobile/`(给张勇读的英语/语文知识点内容库)用途不同——两个目录都叫"灵感/内容",但读者和入库去向完全不同,本节用来消除命名混淆。

- **收什么**:技术架构方案、知识图谱视角、模型选型对比、外部研究综述、AI 写的多视角草稿
- **不收什么**:张勇读的英语/语文知识点内容(走项目根 `Mobile/`)、武器库条目(走项目根 `Attack/`)、知识盾条目(走项目根 `Defense/`)
- **入库去向**:`Inspiration/*.md` 不入 `Defense/`,只在 LanguageWeb 仓库内自闭环
- **首篇入库**:8/26 `00-技术架构v2-知识图谱版.md`(20K,8/25 写的 v2 视角架构,知识图谱/训练场/批改工具/智能讲解/多端 5 模块,与本仓库 v1 视角互补不冲突)

## scripts/ 使用说明

两个解析器均**纯 stdlib**(argparse / json / csv / re),不引入第三方依赖。

### md_to_json.py

将 `语法/*.md` 按章节切分为 JSON,产出结构:

```json
{ "language": "英语", "sections": [ { "name": "动词时态", "points": [ { "name": "现在完成时", "content": "..." } ] } ] }
```

```bash
# 用法
python3 scripts/md_to_json.py --input 语法/英语.md --output data/json/英语语法.json --pretty
```

### csv_to_json.py

将 `词表/*.csv` 解析为 vocab schema 兼容的 JSON 数组。约定列名(大小写/下划线无关):

> `word, pos, pronunciation, meaning_cn, difficulty, tags`
> 可选:`language`(若 CSV 无此列,可用 `--language en` 兜底)、`examples`、`root_id`、`root`

- `difficulty` 自动取首个数字,钳制到 1-5
- `tags` 支持 `|` / `,` / `,` / `;` / `；` 多分隔符
- `examples` 支持 JSON 数组或纯文本(纯文本将打包为单元素数组)

```bash
# 用法
python3 scripts/csv_to_json.py --input 词表/英语_5000.csv --output data/json/英语词表.json --language en --pretty
```

### 入库前校验

```bash
# 用 jsonschema CLI 校验(可选,需 pip install jsonschema)
python3 -m jsonschema -i data/json/英语词表.json data/schema/vocab.schema.json
```
