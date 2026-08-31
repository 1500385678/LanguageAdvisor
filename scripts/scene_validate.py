#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scene_validate.py — 场景 JSON 校验器

校验 `场景语料/*.json` 是否符合 `data/schema/scene.schema.json`。
支持两种输入形态:
  - 单个场景: 文件内容就是 1 个 scene object
  - 多场景数组: 文件内容是 scene object 数组
失败抛出 jsonschema.ValidationError 列出第一条错;成功打印 OK 行。

CLI:
  python3 scripts/scene_validate.py \\
    --input 场景语料/英语_机场过境.json \\
    --schema data/schema/scene.schema.json

约定:
  - 依赖 jsonschema(`pip install jsonschema`),校验链路已在 Phase 0 准备
  - required 字段取 schema `required` 列表
  - enum 字段按 schema `enum` 校验
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft7Validator


def load_scene(path: Path) -> list[dict]:
    """加载场景文件,支持单 object 或数组,统一返回 list。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError(f"{path}: 顶层必须是 object 或 array,实际 {type(data).__name__}")


def validate_scenes(scenes: list[dict], schema: dict) -> list[str]:
    """逐条校验,返回错误列表(空列表 = 全部通过)。"""
    validator = Draft7Validator(schema)
    errors: list[str] = []
    for i, scene in enumerate(scenes):
        for err in validator.iter_errors(scene):
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"#{i} [{scene.get('name', '?')}] {loc}: {err.message}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="场景 JSON schema 校验")
    parser.add_argument("--input", required=True, help="场景 JSON 文件路径")
    parser.add_argument("--schema", required=True, help="scene schema JSON 文件路径")
    args = parser.parse_args()

    in_path = Path(args.input)
    schema_path = Path(args.schema)

    if not in_path.exists():
        print(f"❌ 找不到输入: {in_path}", file=sys.stderr)
        return 2
    if not schema_path.exists():
        print(f"❌ 找不到 schema: {schema_path}", file=sys.stderr)
        return 2

    scenes = load_scene(in_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = validate_scenes(scenes, schema)

    if errors:
        print(f"❌ {in_path} 校验失败,{len(errors)} 条错:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"✅ {in_path} 校验通过,{len(scenes)} 个场景符合 {schema_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
