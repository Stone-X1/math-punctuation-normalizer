#!/usr/bin/env python3
"""Conservatively restore originals from an archive created by the normalizer.

Default is a preview. Only restores a file if its current checksum equals the
checksum of the converted file recorded in the backup manifest. This protects
post-conversion edits from being accidentally overwritten.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import hashlib
import json
import sys
import zipfile

from normalize_math_vault import Change, atomic_write, create_backup


def sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从标点规范化 ZIP 中恢复旧笔记，默认只预览。")
    parser.add_argument("vault", type=Path, help="原 Obsidian 数学库路径")
    parser.add_argument("archive", type=Path, help="规范化程序创建的原文备份 ZIP")
    parser.add_argument("--apply", action="store_true", help="验证并创建二次备份后真正恢复")
    args = parser.parse_args(argv)

    vault = args.vault.expanduser().resolve()
    archive = args.archive.expanduser().resolve()
    if not vault.is_dir() or not archive.is_file():
        parser.error("知识库目录或备份 ZIP 不存在")

    eligible: list[Change] = []
    skipped: list[str] = []
    try:
        with zipfile.ZipFile(archive, "r") as z:
            manifest = json.loads(z.read("manifest.json"))
            for record in manifest["files"]:
                relative = record["path"]
                if not isinstance(relative, str) or not relative:
                    skipped.append("备份包含无效文件路径，拒绝恢复")
                    continue

                relative_path = Path(relative)
                if relative_path.is_absolute() or ".." in relative_path.parts or "." in relative_path.parts:
                    skipped.append(f"{relative}：路径越界或包含非法路径段，拒绝恢复")
                    continue

                # Inspect the original path before resolve(): resolving a symlink
                # hides the fact that the target or a parent was a symlink.
                unresolved_target = vault / relative_path
                if any((vault.joinpath(*relative_path.parts[:i])).is_symlink()
                       for i in range(1, len(relative_path.parts) + 1)):
                    skipped.append(f"{relative}：路径包含符号链接，拒绝恢复")
                    continue

                target = unresolved_target.resolve()
                if target == vault or vault not in target.parents:
                    skipped.append(f"{relative}：路径越界，拒绝恢复")
                    continue
                if not target.is_file():
                    skipped.append(f"{relative}：文件已不存在或不是普通文件")
                    continue
                name = "original/" + relative.replace("\\", "/")
                old = z.read(name)
                if sha256(old) != record["sha256_before"]:
                    skipped.append(f"{relative}：备份校验失败")
                    continue
                current = target.read_bytes()
                if sha256(current) == record["sha256_before"]:
                    continue  # Already restored.
                if sha256(current) != record["sha256_after"]:
                    skipped.append(f"{relative}：自转换后又有变化，不自动覆盖")
                    continue
                eligible.append(Change(target, relative, current, old, 0, 0))
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"无法读取或核对备份：{exc}", file=sys.stderr)
        return 2

    print(f"准备恢复 {len(eligible)} 篇；跳过 {len(skipped)} 篇。")
    for change in eligible[:25]:
        print("  恢复：", change.relative)
    if len(eligible) > 25:
        print(f"  还有 {len(eligible) - 25} 篇未逐条显示。")
    for message in skipped[:25]:
        print("  跳过：", message)
    if not args.apply:
        print("只读预览；如需实际恢复，请添加 --apply。")
        return 0
    if skipped:
        print("存在冲突文件；未执行任何写入，请先处理跳过原因。", file=sys.stderr)
        return 3
    if not eligible:
        print("没有需要恢复的文件。")
        return 0
    try:
        backup = create_backup(vault, eligible)
        print("恢复前的现有文件也已备份到：", backup)
        for change in eligible:
            if change.path.read_bytes() != change.old:
                raise OSError(f"文件在扫描后发生变化：{change.relative}")
            atomic_write(change.path, change.new)
    except OSError as exc:
        print(f"恢复中断；请检查二次备份：{exc}", file=sys.stderr)
        return 4
    print(f"完成恢复 {len(eligible)} 篇。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
