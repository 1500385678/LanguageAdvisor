#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
root_md_to_json.py — 词根 markdown 解析器

将 `词根/*.md` 章节化内容(## 词族 / ### 词根) 拍平为 root 对象数组,
匹配 `data/schema/root.schema.json` 单条词根 schema。

设计原则:
  - 纯 stdlib,无第三方依赖
  - 复用 `md_to_json.py` 的 ## / ### 切分约定
  - 解析 ### 词根正文中**结构化字段**(`- 词源:` `- 本义:` 等) → schema 字段
  - `- 派生:` 多行 → `derivatives[]`
  - `- 例句:` 多行 → `examples[]`
  - `- 标签:` 多行 → `tags[]`
  - 输出 JSON 结构:
    {
      "language": "英语",
      "section_count": 3,
      "root_count": 50,
      "roots": [
        {
          "root": "vid",
          "language": "la",
          "origin": "latin",
          "meaning": "看",
          "meaning_en": "see",
          "difficulty": 2,
          "derivatives": [
            {"word": "evident", "pos": "adj", "meaning_cn": "明显的", "affix": "ex-+vid"},
            ...
          ],
          "examples": ["The evidence is evident from the video.", ...],
          "tags": ["词族-看", "高考", "四级"],
          "section": "看"
        },
        ...
      ]
    }

约定 markdown 结构(继承自 md_to_json.py):
  # <语言名> 词根词缀 样章     (H1,作为 language 字段)
  ## <词族大类>                  (H2,如"看 · 词族")
  ### <词根本体>                 (H3,如"vid")
  <正文字段,每行以 "- key: value" 形式定义>

CLI:
  python3 scripts/root_md_to_json.py \\
    --input 词根/英语_词根样章.md \\
    --output data/json/英语_词根样章.json \\
    --language-la la \\
    --pretty
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
# 字段行:以 "- " 开头,后接 "key: value" 或 "key：value"
FIELD_RE = re.compile(r"^-\s*([^:：]+?)\s*[:：]\s*(.*)$")
# 派生词子条目:"- word(pos 释义, affix 前后缀)" 或 "- word(释义)"
DERIV_RE = re.compile(
    r"^([a-zA-Z\u4e00-\u9fff]+)\(([^)]+)\)\s*$"
)


def parse_deriv_line(text: str) -> dict[str, str] | None:
    """解析一行派生词条目: `word(说明)` → {word, pos?, meaning_cn?, affix?}。

    支持的内部格式:
      - `pos 释义, affix 描述`       → {pos, meaning_cn, affix}
      - `pos 释义`                  → {pos, meaning_cn}
      - `释义`                       → {meaning_cn}
      - `affix 描述`                 → {affix, meaning_cn=affix 描述}

    启发式:
      - 第一个空白前的短字母 token(1-5 个 [a-z]) 判为 pos
      - 含 +/-/→ 等特殊符号或 ex-/in-/re-/con- 前缀的 token 判为 affix
      - 其余判为 meaning_cn
    """
    text = text.strip()
    m = DERIV_RE.match(text)
    if not m:
        return None
    word = m.group(1).strip()
    inner = m.group(2).strip()
    if not inner:
        return {"word": word, "pos": "", "meaning_cn": "", "affix": ""}

    # 先按逗号拆成多个 part
    parts = [p.strip() for p in inner.split(",") if p.strip()]
    pos = ""
    affix = ""
    meaning_cn_parts: list[str] = []

    for p in parts:
        # 在 part 内找 pos:开头 token 或首词
        tokens = p.split()
        first = tokens[0] if tokens else ""
        # 规则 1:首 token 是纯字母短串(1-5)且是已知词性 → pos
        if re.fullmatch(r"[a-z]{1,5}(/[a-z]{1,5})?", first) and first in {
            "n", "v", "adj", "adv", "pron", "prep", "conj", "num", "aux", "int",
            "art", "det",
        }:
            pos = first
            # 剩下的 tokens 是释义
            rest = " ".join(tokens[1:]).strip()
            if rest:
                meaning_cn_parts.append(rest)
        # 规则 2:含 →/+/-/ex-/in-/re-/con-/de-/pro-/pre-/dis-/com- 等形态 → affix
        elif any(
            marker in p
            for marker in ("→", "ex-", "in-", "re-", "con-", "de-", "pro-",
                           "pre-", "dis-", "com-", "sub-", "trans-", "ad-",
                           "ab-", "ob-", "over-", "under-", "out-", "up-",
                           "down-", "fore-", "with-", "mis-", "un-", "non-",
                           "anti-", "auto-", "co-", "inter-", "mono-", "poly-",
                           "super-", "sur-")
        ) and len(p) < 60:
            affix = p
        # 规则 3:以 "-" 开头或 "+" 开头,后跟描述(如 -ion 名词后缀)
        elif re.match(r"^[-+]\s*\w+", p) and len(p) < 60:
            affix = p
        else:
            meaning_cn_parts.append(p)

    meaning_cn = ", ".join(meaning_cn_parts)
    return {
        "word": word,
        "pos": pos,
        "meaning_cn": meaning_cn,
        "affix": affix,
    }


def parse_field_line(line: str) -> tuple[str, str] | None:
    """解析 `- key: value` 行 → (key, value)。"""
    m = FIELD_RE.match(line)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def extract_difficulty(text: str) -> int | None:
    """从 "难度: 2 (A2-B1)" 或 "难度: 3" 提取数字 1-5,失败返 None。"""
    m = re.search(r"(\d)", text)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 5:
            return v
    return None


def split_tag_list(text: str) -> list[str]:
    """`tags` 字段:`高考, 四级, 雅思, 托福` → ["高考", "四级", "雅思", "托福"]"""
    parts = re.split(r"[,，、]", text)
    return [p.strip() for p in parts if p.strip()]


def map_origin(text: str) -> tuple[str, str]:
    """`- 词源: 拉丁 videre` → ("latin", "拉丁 videre")。

    自由文本 → enum:
      - 拉丁/la → latin
      - 希腊/grc → greek
      - 古英语/日耳曼/germanic → germanic
      - 古法语/法语/french → french
      - 梵语/sanskrit → sanskrit
      - 本族/原生/native → native
      - 混合/mixed → mixed
    """
    t = text.strip()
    source_text = t  # 默认保留原文作为详细描述
    lower = t.lower()
    if "拉丁" in t or "la " in lower or lower.startswith("la "):
        return "latin", source_text
    if "希腊" in t or "grc" in lower:
        return "greek", source_text
    if "古英语" in t or "日耳曼" in t or "germanic" in lower:
        return "germanic", source_text
    if "古法语" in t or "french" in lower:
        return "french", source_text
    if "梵语" in t or "sanskrit" in lower:
        return "sanskrit", source_text
    if "本族" in t or "原生" in t or "native" in lower:
        return "native", source_text
    if "混合" in t or "mixed" in lower:
        return "mixed", source_text
    return "latin", source_text  # 未识别默认 latin


def parse_markdown_roots(text: str, default_root_language: str) -> dict[str, Any]:
    """解析词根 markdown → {language, section_count, root_count, roots[]}。"""
    language: str | None = None
    current_section: str | None = None
    current_root: dict[str, Any] | None = None
    current_field: str | None = None  # 当前正在累积内容的字段名(派生/例句/标签)
    current_list: list[Any] | None = None  # 累积列表(derivatives 或 examples 或 tags)

    roots: list[dict[str, Any]] = []
    sections_seen: set[str] = set()

    def flush_root() -> None:
        nonlocal current_root, current_field, current_list
        if current_root is not None:
            # 收尾:把累积列表写入 root
            if current_list is not None and current_field is not None:
                if current_field in ("derivatives", "examples", "tags"):
                    # tags 字段若空,尝试从刚结束的累积 list 取
                    if current_field == "tags" and not current_list:
                        pass
                    else:
                        current_root[current_field] = current_list
            roots.append(current_root)
        current_root = None
        current_field = None
        current_list = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        m1 = H1_RE.match(line)
        if m1:
            flush_root()
            language = m1.group(1).strip()
            continue

        m2 = H2_RE.match(line)
        if m2:
            flush_root()
            current_section = m2.group(1).strip()
            # 词族名可能含 " · 词族" 后缀,只取前半(如"看 · 词族" → "看")
            section_name = re.split(r"[·•\s]+", current_section)[0]
            current_root = None
            sections_seen.add(section_name)
            continue

        m3 = H3_RE.match(line)
        if m3:
            flush_root()
            root_name = m3.group(1).strip()
            current_root = {
                "root": root_name,
                "language": default_root_language,
                "origin": "latin",  # 默认值,后续 - 词源 字段可覆盖
                "meaning": "",
                "meaning_en": "",
                "difficulty": 3,
                "derivatives": [],
                "examples": [],
                "tags": [],
                "section": (
                    re.split(r"[·•\s]+", current_section)[0]
                    if current_section
                    else "_未分类"
                ),
            }
            current_field = None
            current_list = None
            continue

        # 普通行
        if current_root is None:
            continue  # H1/H2 之间的导言行,跳过

        field = parse_field_line(line)
        if field:
            # 字段边界:先 flush 上一字段的累积
            if current_field == "derivatives" and current_list:
                current_root["derivatives"] = current_list
            elif current_field == "examples" and current_list:
                current_root["examples"] = current_list
            elif current_field == "tags" and current_list:
                current_root["tags"] = current_list

            key, value = field
            current_field = None
            current_list = None

            if key == "词源":
                origin_enum, source_text = map_origin(value)
                current_root["origin"] = origin_enum
                current_root["source_text"] = source_text
            elif key == "本义":
                current_root["meaning"] = value
            elif key == "本义英文" or key == "英文":
                current_root["meaning_en"] = value
            elif key == "难度":
                d = extract_difficulty(value)
                if d is not None:
                    current_root["difficulty"] = d
            elif key == "派生":
                # 派生: 开始累积 list
                # 关键:不用逗号切分(派生内部有逗号),用 regex 找 word(...) 模式
                current_field = "derivatives"
                current_list = []
                # 找所有 `word(...)` 模式,word 是字母或中文,括号内可有逗号
                deriv_pattern = re.compile(r"([a-zA-Z\u4e00-\u9fff]+)\(([^)]+)\)")
                for match in deriv_pattern.finditer(value):
                    word = match.group(1).strip()
                    inner = match.group(2).strip()
                    # 构造一个伪行让 parse_deriv_line 处理
                    fake_line = f"{word}({inner})"
                    d = parse_deriv_line(fake_line)
                    if d and d.get("word"):
                        current_list.append(d)
            elif key == "例句":
                current_field = "examples"
                current_list = []
                # value 可能含 " / " 分隔多句
                for s in re.split(r"\s*/\s*", value):
                    s = s.strip().rstrip("。.").rstrip(",")
                    if s:
                        current_list.append(s)
            elif key == "标签":
                current_field = "tags"
                current_list = split_tag_list(value)
            # 忽略其他未知字段
            continue

        # 非字段行:若是当前累积字段的延续
        if current_field == "derivatives":
            # 多行派生条目
            d = parse_deriv_line(line)
            if d:
                current_list.append(d) if current_list is not None else None
        elif current_field == "examples":
            stripped = line.strip()
            if stripped and current_list is not None:
                # 去掉尾部句号/逗号
                stripped = stripped.rstrip("。.,，；;")
                if stripped:
                    current_list.append(stripped)
        elif current_field == "tags":
            # 多行标签
            if current_list is not None:
                current_list.extend(split_tag_list(line))

    flush_root()

    return {
        "language": language or "",
        "section_count": len(sections_seen),
        "root_count": len(roots),
        "roots": roots,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="解析词根 markdown 文件 → root schema JSON 数组",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="输入 markdown 文件路径(词根样章)",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="输出 JSON 文件路径(将创建 data/json/ 下子目录)",
    )
    parser.add_argument(
        "--language-la",
        dest="root_language",
        default="la",
        help="词根语种代码,默认 la(拉丁)。例:希腊 grc、日耳曼 germanic、英语 en",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="输出美化格式(2 空格缩进)",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"[ERROR] 输入文件不存在: {args.input}", file=sys.stderr)
        return 1

    text = args.input.read_text(encoding="utf-8")
    data = parse_markdown_roots(text, default_root_language=args.root_language)

    indent = 2 if args.pretty else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )

    print(
        f"[OK] {args.input} → {args.output}  "
        f"(language={data['language']!r}, sections={data['section_count']}, "
        f"roots={data['root_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
