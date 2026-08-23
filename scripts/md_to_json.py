#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md_to_json.py — 语法 markdown 解析器

将 `语法/*.md` 章节化内容按 ## / ### 切分,转换为结构化 JSON。
设计原则:
  - 纯 stdlib,无第三方依赖
  - 输出 schema 与 data/schema/vocab.schema.json / scene.schema.json 风格一致
  - 支持 --input / --output / --pretty 三个 CLI 参数

约定 markdown 结构:
  # <语言名> 语法  (H1,作为顶层 language 字段)
  ## <语法大类>  (H2,如"动词时态""助词")
  ### <语法点>  (H3,如"现在完成时""は/が")
  <正文内容,支持多行,直到下一个 ### 或 ## 或 # 结束>

输出 JSON 结构:
  {
    "language": "英语",
    "sections": [
      {
        "name": "动词时态",
        "level": 2,
        "points": [
          {
            "name": "现在完成时",
            "level": 3,
            "content": "..."
          }
        ]
      }
    ]
  }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


H1_RE = re.compile(r"^#\s+(.+?)\s*$")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")
H3_RE = re.compile(r"^###\s+(.+?)\s*$")


def parse_markdown(text: str) -> dict[str, Any]:
    """解析 markdown 文本 → 章节树。"""
    language: str | None = None
    sections: list[dict[str, Any]] = []

    current_section: dict[str, Any] | None = None
    current_point: dict[str, Any] | None = None
    buffer: list[str] = []

    def flush_buffer() -> None:
        """把 buffer 中的正文写入当前 point(若有)。"""
        if current_point is not None and buffer:
            content = "\n".join(buffer).strip()
            if content:
                current_point["content"] = content
        buffer.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        m1 = H1_RE.match(line)
        if m1:
            flush_buffer()
            current_point = None
            current_section = None
            language = m1.group(1).strip()
            continue

        m2 = H2_RE.match(line)
        if m2:
            flush_buffer()
            current_point = None
            current_section = {
                "name": m2.group(1).strip(),
                "level": 2,
                "points": [],
            }
            sections.append(current_section)
            continue

        m3 = H3_RE.match(line)
        if m3:
            flush_buffer()
            if current_section is None:
                # 出现 H3 但没有 H2:为它建一个匿名 section
                current_section = {
                    "name": "_未分类",
                    "level": 2,
                    "points": [],
                }
                sections.append(current_section)
            current_point = {
                "name": m3.group(1).strip(),
                "level": 3,
            }
            current_section["points"].append(current_point)
            continue

        # 普通行,加入 buffer
        buffer.append(line)

    flush_buffer()

    return {
        "language": language or "",
        "sections": sections,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="解析语法 markdown 文件 → JSON",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="输入 markdown 文件路径",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="输出 JSON 文件路径",
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

    text = args.input.read_text(encoding="utf-8")
    data = parse_markdown(text)

    indent = 2 if args.pretty else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )

    sections_n = len(data["sections"])
    points_n = sum(len(s["points"]) for s in data["sections"])
    print(
        f"[OK] {args.input} → {args.output}  "
        f"(language={data['language']!r}, sections={sections_n}, points={points_n})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
