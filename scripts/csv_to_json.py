#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csv_to_json.py — 词表 CSV 解析器

将 `词表/*.csv` 解析为结构化 JSON,字段对应项目开发计划 §4.3 vocab 表。
设计原则:
  - 纯 stdlib(csv / argparse / json / re),无第三方依赖
  - 支持可选 `--language` 字段标注语种(若 csv 内未提供 language 列)
  - 字段名映射灵活:实际 csv 列名与 schema 字段可大小写/下划线无关匹配
  - tags 字段支持以 `|` 或 `,` 或中文逗号 `,` 分隔的多种写法
  - difficulty 字段若为空则置 1,若非整数则尝试取首个数字

约定 csv 列(顺序不限,大小写不限):
  word, pos, pronunciation, meaning_cn, difficulty, tags
  可选列:
  language   — 若缺省且未传 --language,则抛错
  examples   — 例句,支持 JSON 字符串或纯文本(纯文本将打包为 [text])

输出 JSON 结构(数组):
  [
    {
      "word": "abandon",
      "pos": "v",
      "pronunciation": "/əˈbændən/",
      "meaning_cn": "放弃,抛弃",
      "difficulty": 4,
      "tags": ["高频", "六级"],
      "language": "en",
      "examples": ["They had to abandon the project."]
    }
  ]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any


# 允许的 schema 字段(对应 vocab 表)
SCHEMA_FIELDS = {
    "word",
    "pos",
    "pronunciation",
    "meaning_cn",
    "difficulty",
    "tags",
    "language",
    "examples",
    "root_id",
    "root",
}

# 列名归一化:strip + lower + 去空格/下划线
def _norm(name: str) -> str:
    return re.sub(r"[\s_]+", "", name.strip().lower())


# 别名 → schema 字段(允许 csv 用多种命名)
COLUMN_ALIASES = {
    "word": "word",
    "lemma": "word",
    "vocab": "word",
    "pos": "pos",
    "partofspeech": "pos",
    "speech": "pos",
    "pronunciation": "pronunciation",
    "pron": "pronunciation",
    "ipa": "pronunciation",
    "phonetic": "pronunciation",
    "meaningcn": "meaning_cn",
    "meaning": "meaning_cn",
    "translation": "meaning_cn",
    "cn": "meaning_cn",
    "difficulty": "difficulty",
    "level": "difficulty",
    "tags": "tags",
    "tag": "tags",
    "labels": "tags",
    "language": "language",
    "lang": "language",
    "examples": "examples",
    "example": "examples",
    "rootid": "root_id",
    "root": "root",
}


def parse_difficulty(raw: str) -> int:
    """解析 difficulty,失败时默认 1。"""
    if not raw:
        return 1
    s = raw.strip()
    m = re.search(r"\d+", s)
    if not m:
        return 1
    try:
        v = int(m.group(0))
    except ValueError:
        return 1
    # 钳制到 1-5
    return max(1, min(5, v))


def parse_tags(raw: str) -> list[str]:
    """tags 字段多分隔符兼容:`|` / `,` / `,` / `;` / `；`。"""
    if not raw:
        return []
    parts = re.split(r"[|,;，；]", raw)
    return [p.strip() for p in parts if p.strip()]


def parse_examples(raw: str) -> list[str]:
    """examples 字段:JSON 数组则解,否则整段作为单元素数组。"""
    if not raw:
        return []
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(x) for x in data]
        except json.JSONDecodeError:
            pass
    return [s]


def parse_csv(
    csv_path: Path,
    default_language: str | None = None,
) -> list[dict[str, Any]]:
    """读取 csv 并归一化到 schema 字段。"""
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []

        # 列名归一化映射
        col_map: dict[str, str] = {}
        for original in reader.fieldnames:
            key = _norm(original)
            target = COLUMN_ALIASES.get(key, key)
            if target in SCHEMA_FIELDS:
                col_map[original] = target

        rows: list[dict[str, Any]] = []
        for raw_row in reader:
            item: dict[str, Any] = {}
            for original_col, value in raw_row.items():
                target = col_map.get(original_col)
                if not target:
                    continue
                item[target] = value.strip() if isinstance(value, str) else value

            # language 兜底
            if not item.get("language") and default_language:
                item["language"] = default_language

            # 类型归一化
            item["difficulty"] = parse_difficulty(item.get("difficulty", ""))
            item["tags"] = parse_tags(item.get("tags", ""))
            item["examples"] = parse_examples(item.get("examples", ""))

            # word 必填,空行跳过
            if not item.get("word"):
                continue

            rows.append(item)

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="解析词表 CSV → JSON",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="输入 CSV 文件路径",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="输出 JSON 文件路径",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="当 CSV 中无 language 列时,提供默认语种(如 en/ja/fr)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="输出美化格式(2 空格缩进,中文友好)",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"[ERROR] 输入文件不存在: {args.input}", file=sys.stderr)
        return 1

    rows = parse_csv(args.input, default_language=args.language)

    # 检查:若仍有缺失 language 的行,报错
    missing_lang = [r["word"] for r in rows if not r.get("language")]
    if missing_lang:
        print(
            f"[ERROR] {len(missing_lang)} 行缺少 language 字段(无 --language 且 CSV 也无此列)。"
            f"示例: {missing_lang[:3]}",
            file=sys.stderr,
        )
        return 1

    indent = 2 if args.pretty else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )

    print(f"[OK] {args.input} → {args.output}  (rows={len(rows)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
