#!/usr/bin/env python3
"""Safe-ish, conservative B+ punctuation normalization for Obsidian Markdown.

Requires Python >= 3.9; standard library only. Preview-only by default.
This program intentionally skips ambiguous structures rather than guessing.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

MAPPING = {"，": ",", "。": ".", "．": ".", "；": ";", "：": ":", "？": "?", "！": "!"}
ASCII_PUNCT = ",.;:?!"
CLOSING = set(")]}>】）》」』”’\"'」』、，。；：？！,.;:?!*_~")
SKIP_DIRECTORIES = {".obsidian", ".git", ".trash", ".venv", "venv", "node_modules", "__pycache__"}
SKIP_SECTION_TITLES = {"原题", "题目", "题干", "试题原文", "原文", "引用原文", "原始题目", "试题"}
HEADING_RE = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)\s*$")
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>，。；：？！]+", re.I)
HTML_RAW_RE = re.compile(r"<\s*/?\s*(?:script|style|pre|textarea)\b", re.I)
HTML_RAW_START_RE = re.compile(r"<\s*(script|style|pre|textarea)\b", re.I)
LATEX_ENV_START = re.compile(r"(?<!\\)\\begin\{([A-Za-z*]+)\}")
LATEX_ENV_END = re.compile(r"(?<!\\)\\end\{([A-Za-z*]+)\}")


class UnsafeMarkdown(ValueError):
    """Encountered a delimiter that could not be safely interpreted."""


@dataclass
class Converted:
    text: str
    math_tokens: list[str] = field(default_factory=list)
    protected_lines: int = 0
    changed_lines: int = 0


@dataclass
class Change:
    path: Path
    relative: str
    old: bytes
    new: bytes
    changed_lines: int
    protected_lines: int


def escaped(source: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and source[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def mark(mask: list[bool], a: int, b: int) -> None:
    for i in range(a, b):
        mask[i] = True


def find_unescaped(text: str, needle: str, start: int) -> int:
    index = text.find(needle, start)
    while index >= 0:
        if not escaped(text, index):
            return index
        index = text.find(needle, index + len(needle))
    return -1


def code_mask(line: str) -> list[bool]:
    """Return masked positions for paired inline backtick code spans."""
    mask = [False] * len(line)
    i = 0
    while i < len(line):
        if line[i] != "`" or escaped(line, i):
            i += 1
            continue
        j = i
        while j < len(line) and line[j] == "`":
            j += 1
        n = j - i
        end = j
        while end < len(line):
            found = line.find("`" * n, end)
            if found < 0:
                raise UnsafeMarkdown("未闭合的行内反引号代码；可能跨行")
            if (found > 0 and line[found - 1] == "`") or (found + n < len(line) and line[found + n] == "`"):
                end = found + n
                continue
            mark(mask, i, found + n)
            i = found + n
            break
        else:
            raise UnsafeMarkdown("未闭合的行内反引号代码")
        if i == j:  # Defensive check, should not occur.
            raise UnsafeMarkdown("行内代码解析异常")
    return mask


def match_brackets(line: str, start: int, left: str, right: str) -> int:
    """Return index after matching closing bracket, honoring escapes/nesting."""
    if line[start] != left:
        raise UnsafeMarkdown("括号解析异常")
    depth = 0
    for i in range(start, len(line)):
        if escaped(line, i):
            continue
        if line[i] == left:
            depth += 1
        elif line[i] == right:
            depth -= 1
            if depth == 0:
                return i + 1
    raise UnsafeMarkdown("未闭合的 Markdown 链接结构")


def inline_mask(line: str, codes: list[bool]) -> tuple[list[bool], list[str]]:
    """Conservatively protect math, code, URLs, links, tags and wiki links."""
    mask = codes[:]
    math_tokens: list[str] = []
    i = 0
    while i < len(line):
        if mask[i]:
            i += 1
            continue
        if escaped(line, i):
            # Escaped punctuation can be literal Markdown syntax, leave as-is.
            mask[i] = True
            i += 1
            continue

        if line.startswith("[[", i):
            end = line.find("]]", i + 2)
            if end < 0:
                raise UnsafeMarkdown("未闭合的 Obsidian 双链 [[...]]")
            mark(mask, i, end + 2)
            i = end + 2
            continue

        if line.startswith("\\(", i) or line.startswith("\\[", i):
            close = "\\)" if line[i + 1] == "(" else "\\]"
            end = find_unescaped(line, close, i + 2)
            if end < 0:
                raise UnsafeMarkdown("未闭合的 LaTeX \\( \\) 或 \\[ \\] 数学区域")
            end += 2
            math_tokens.append(line[i:end])
            mark(mask, i, end)
            i = end
            continue

        if line[i] == "$":
            if line.startswith("$$", i):
                raise UnsafeMarkdown("检测到未作为块保护的 $$ 符号")
            end = find_unescaped(line, "$", i + 1)
            if end < 0:
                raise UnsafeMarkdown("未闭合的 $...$ 数学区域；可能是货币符号")
            math_tokens.append(line[i:end + 1])
            mark(mask, i, end + 1)
            i = end + 1
            continue

        url = URL_RE.match(line, i)
        if url:
            mark(mask, i, url.end())
            i = url.end()
            continue

        if line[i] == "<" and i + 1 < len(line) and re.match(r"[A-Za-z/!?]", line[i + 1]):
            end = line.find(">", i + 1)
            if end < 0:
                raise UnsafeMarkdown("未闭合的 HTML 标签或自动链接")
            mark(mask, i, end + 1)
            i = end + 1
            continue

        if line[i] == "[":
            # Wikilinks handled above. Ordinary Markdown links and reference links.
            try:
                after_label = match_brackets(line, i, "[", "]")
            except UnsafeMarkdown:
                # A lone '[' is not necessarily a link; protect the line instead.
                raise UnsafeMarkdown("不确定的 [ Markdown 结构")
            if after_label < len(line) and line[after_label] == "(":
                after_target = match_brackets(line, after_label, "(", ")")
                mark(mask, i, after_target)
                i = after_target
                continue
            if after_label < len(line) and line[after_label] == "[":
                after_ref = match_brackets(line, after_label, "[", "]")
                mark(mask, i, after_ref)
                i = after_ref
                continue
            # Nonlink [a,b] is not changed here; math-like content remains intact
            # by protecting all text inside any square brackets.
            mark(mask, i, after_label)
            i = after_label
            continue

        i += 1
    return mask, math_tokens


def is_han(c: str) -> bool:
    return bool(c) and ("\u3400" <= c <= "\u9fff" or "\uf900" <= c <= "\ufaff")


def wants_space(line: str, index: int, char: str, is_converted: bool) -> bool:
    """Whether punctuation needs a single space before following content."""
    j = index + 1
    while j < len(line) and line[j] in " \t":
        j += 1
    if (j == len(line) or line[j] in "\r\n" or line[j] in CLOSING
            or line.startswith("</", j)):
        return False
    if line[j] in " \t":
        return False
    if is_converted:
        return True
    # Only correct pre-existing ASCII punctuation when Chinese prose is evident.
    prev = line[index - 1] if index else ""
    next_char = line[j]
    if escaped(line, index):
        return False
    if is_han(prev):
        return True
    if is_han(next_char) and (char != "." or prev in ")]}$"):
        return True
    return False


def convert_line(line: str, mask: list[bool]) -> str:
    out: list[str] = []
    i = 0
    while i < len(line):
        char = line[i]
        if mask[i] or escaped(line, i):
            out.append(char)
            i += 1
            continue
        converted = char in MAPPING
        if converted or char in ASCII_PUNCT:
            replacement = MAPPING.get(char, char)
            if wants_space(line, i, replacement, converted):
                out.append(replacement)
                # Normalize existing horizontal spaces to one ASCII space only.
                j = i + 1
                while j < len(line) and line[j] in " \t" and not mask[j]:
                    j += 1
                out.append(" ")
                i = j
                continue
            out.append(replacement)
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def math_markers(line: str, code_positions: list[bool]) -> tuple[list[int], list[tuple[int, str]]]:
    dollar_positions: list[int] = []
    slash_markers: list[tuple[int, str]] = []
    i = 0
    while i < len(line):
        if code_positions[i] or escaped(line, i):
            i += 1
            continue
        if line.startswith("$$", i) and not code_positions[i + 1]:
            dollar_positions.append(i)
            i += 2
            continue
        if line.startswith(("\\[", "\\]", "\\(", "\\)"), i) and not code_positions[i + 1]:
            slash_markers.append((i, line[i:i + 2]))
            i += 2
            continue
        i += 1
    return dollar_positions, slash_markers


def transform(text: str) -> Converted:
    lines = text.splitlines(keepends=True)
    if not lines:
        return Converted(text)
    result: list[str] = []
    math_tokens: list[str] = []
    protected_lines = 0
    changed_lines = 0
    yaml = lines[0].lstrip("\ufeff").strip("\r\n") == "---"
    yaml_finished = not yaml
    fence: tuple[str, int] | None = None
    math_dollars = False
    math_slash: str | None = None
    latex_stack: list[str] = []
    html_comment = False
    html_raw: str | None = None
    obsidian_comment = False
    manual_off = False
    skip_heading_level: int | None = None

    for line_number, line in enumerate(lines, 1):
        stripped = line.strip()
        def protect() -> None:
            nonlocal protected_lines
            result.append(line)
            protected_lines += 1

        # Manual protection block. The markers themselves always stay unchanged.
        if re.search(r"<!--\s*punctuation:\s*off\s*-->", line, re.I):
            if manual_off:
                raise UnsafeMarkdown(f"第 {line_number} 行: 重复的 punctuation: off")
            manual_off = True
            protect()
            continue
        if re.search(r"<!--\s*punctuation:\s*on\s*-->", line, re.I):
            if not manual_off:
                raise UnsafeMarkdown(f"第 {line_number} 行: 缺少对应 off 的 punctuation: on")
            manual_off = False
            protect()
            continue
        if manual_off:
            protect()
            continue

        if yaml:
            protect()
            if line_number > 1 and stripped in ("---", "..."):
                yaml = False
                yaml_finished = True
            continue

        # Fenced code, e.g. ```python or ~~~ (including mathematical examples).
        if fence:
            protect()
            if re.match(r"^[ \t]{0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*$", line.rstrip("\r\n")):
                fence = None
            continue
        opening_fence = FENCE_RE.match(line)
        if opening_fence:
            token = opening_fence.group(1)
            fence = (token[0], len(token))
            protect()
            continue

        # HTML raw-text blocks must remain unmodified across all lines.
        if html_raw:
            protect()
            if re.search(r"</\s*" + re.escape(html_raw) + r"\s*>", line, re.I):
                html_raw = None
            continue
        raw_start = HTML_RAW_START_RE.search(line)
        if raw_start:
            raw_kind = raw_start.group(1).lower()
            if not re.search(r"</\s*" + re.escape(raw_kind) + r"\s*>", line[raw_start.end():], re.I):
                html_raw = raw_kind
            protect()
            continue

        # Full-line, extended protected blocks.
        if html_comment:
            protect()
            if "-->" in line:
                html_comment = False
            continue
        if obsidian_comment:
            protect()
            if "%%" in line:
                # Two markers on same line can end and restart.
                obsidian_comment = line.count("%%") % 2 == 0
            continue
        if "<!--" in line:
            html_comment = line.count("<!--") > line.count("-->")
            protect()
            continue
        if "%%" in line:
            obsidian_comment = line.count("%%") % 2 == 1
            protect()
            continue

        codes = code_mask(line)
        dollars, slashes = math_markers(line, codes)
        if math_dollars or dollars:
            math_tokens.append(line)
            if len(dollars) % 2:
                math_dollars = not math_dollars
            protect()
            continue

        if math_slash or slashes:
            # Support opening/closing on different lines; single-line paired
            # math delimiters are handled by inline_mask, so surrounding prose
            # can still be converted.
            started_in_block = bool(math_slash)
            for _, token in slashes:
                if math_slash:
                    correct_close = "\\]" if math_slash == "\\[" else "\\)"
                    if token == correct_close:
                        math_slash = None
                    elif token in ("\\[", "\\("):
                        raise UnsafeMarkdown(f"第 {line_number} 行: 嵌套或混用 LaTeX 数学分隔符")
                else:
                    if token in ("\\[", "\\("):
                        math_slash = token
                    else:
                        raise UnsafeMarkdown(f"第 {line_number} 行: 多余的 LaTeX 数学结束分隔符")
            if started_in_block or math_slash:
                math_tokens.append(line)
                protect()
                continue

        begins = [m for m in LATEX_ENV_START.finditer(line) if not codes[m.start()]]
        ends = [m for m in LATEX_ENV_END.finditer(line) if not codes[m.start()]]
        if latex_stack or begins or ends:
            events = sorted([(m.start(), True, m.group(1)) for m in begins] +
                            [(m.start(), False, m.group(1)) for m in ends])
            for _, opening, name in events:
                if opening:
                    latex_stack.append(name)
                elif not latex_stack or latex_stack[-1] != name:
                    raise UnsafeMarkdown(f"第 {line_number} 行: 不匹配的 LaTeX begin/end 环境")
                else:
                    latex_stack.pop()
            math_tokens.append(line)
            protect()
            continue

        heading = HEADING_RE.match(line)
        if heading and skip_heading_level is not None and len(heading.group(1)) <= skip_heading_level:
            skip_heading_level = None
        if heading and heading.group(2).strip(" *:：") in SKIP_SECTION_TITLES:
            skip_heading_level = len(heading.group(1))
        if skip_heading_level is not None:
            protect()
            continue
        # Obsidian heading links include the literal heading text.  Rewriting
        # punctuation in headings without rewriting inbound links from every
        # vault would risk breaking #heading targets. Keep all ATX headings
        # byte-identical; normal prose elsewhere can still be normalized.
        if heading:
            protect()
            continue

        # Skip entire lines containing structures that can resemble Markdown or
        # unmarked math (tables, blockquotes, indented code, HTML raw blocks).
        if (line.startswith(("    ", "\t"))
            or re.match(r"^[ \t]{0,3}>", line)
            or re.match(r"^[ \t]{0,3}\[[^\]]+\]:", line)
            or re.match(r"^[ \t]*([-*_])[ \t]*(?:\1[ \t]*){2,}$", stripped)
            or HTML_RAW_RE.search(line)):
            protect()
            continue

        mask, inline_math = inline_mask(line, codes)
        # A pipe outside a protected span may denote a Markdown table or
        # an unmarked math expression; do not guess.
        if any(c == "|" and not mask[i] for i, c in enumerate(line)):
            protect()
            continue
        math_tokens.extend(inline_math)
        changed = convert_line(line, mask)
        if changed != line:
            changed_lines += 1
        result.append(changed)

    if not yaml_finished:
        raise UnsafeMarkdown("YAML frontmatter 没有闭合")
    if fence:
        raise UnsafeMarkdown("代码围栏没有闭合")
    if math_dollars:
        raise UnsafeMarkdown("$$ 数学环境没有闭合")
    if math_slash:
        raise UnsafeMarkdown("\\[ 或 \\( 数学环境没有闭合")
    if latex_stack:
        raise UnsafeMarkdown("LaTeX begin/end 环境没有闭合")
    if html_comment or obsidian_comment:
        raise UnsafeMarkdown("注释块没有闭合")
    if html_raw:
        raise UnsafeMarkdown("HTML 原始文本块没有闭合")
    if manual_off:
        raise UnsafeMarkdown("punctuation: off 保护区域没有关闭")
    return Converted("".join(result), math_tokens, protected_lines, changed_lines)


def files_in(root: Path):
    if root.is_file():
        if root.suffix.lower() == ".md" and not root.is_symlink():
            yield root
        return
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRECTORIES
                         and not (Path(base) / d).is_symlink())
        for name in sorted(names):
            path = Path(base) / name
            if path.suffix.lower() == ".md" and not path.is_symlink():
                yield path


def compare_math(before: Converted, after: Converted) -> bool:
    return before.math_tokens == after.math_tokens


def analyze(root: Path):
    changes: list[Change] = []
    skipped: list[tuple[str, str]] = []
    scanned = 0
    protected = 0
    for path in files_in(root):
        scanned += 1
        relative = str(path.relative_to(root)) if root.is_dir() else path.name
        try:
            old = path.read_bytes()
            text = old.decode("utf-8")  # Keep UTF-8 BOM and original CRLF characters intact.
            before = transform(text)
            # An independent second parse validates balanced markup/math and
            # identical extracted math tokens in the prospective output.
            after = transform(before.text)
            if not compare_math(before, after):
                raise UnsafeMarkdown("数学内容在转换后发生变化")
            if after.text != before.text:
                raise UnsafeMarkdown("重复运行转换器结果不同（不满足幂等性）")
            protected += before.protected_lines
            new = before.text.encode("utf-8")
            if new != old:
                changes.append(Change(path, relative, old, new, before.changed_lines, before.protected_lines))
        except (OSError, UnicodeError, UnsafeMarkdown) as exc:
            skipped.append((relative, str(exc)))
    return scanned, protected, changes, skipped


def generate_report(root: Path, scanned: int, protected: int,
                    changes: list[Change], skipped: list[tuple[str, str]],
                    *, max_diffs: int = 15, max_diff_lines: int = 120, backup: str | None = None) -> str:
    lines = ["# Obsidian 数学库标点规范化报告", "",
             f"- 扫描目标：`{root}`",
             f"- 扫描 Markdown 文件：**{scanned}**",
             f"- 待修改文件：**{len(changes)}**",
             f"- 因不确定或错误而跳过的文件：**{len(skipped)}**",
             f"- 被保护而未处理的行数（含代码、公式块、题干等）：**{protected}**",
             f"- 模式：{'已执行写入' if backup else '只读预览（未修改任何笔记）'}",
             ""]
    if backup:
        lines += [f"- 原文件备份：`{backup}`", ""]
    lines += ["## 待修改文件清单", ""]
    if changes:
        for c in changes:
            lines.append(f"- `{c.relative}`（{c.changed_lines} 行变更）")
    else:
        lines.append("（没有需要修改的文件）")
    lines += ["", "## 跳过文件及原因", ""]
    if skipped:
        for name, why in skipped:
            lines.append(f"- `{name}`：{why}")
    else:
        lines.append("（无）")
    lines += ["", "## 前后对照（仅展示部分文件）", ""]
    for c in changes[:max_diffs]:
        old_text = c.old.decode("utf-8").splitlines(keepends=True)
        new_text = c.new.decode("utf-8").splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_text, new_text,
                                         fromfile="before/" + c.relative,
                                         tofile="after/" + c.relative,
                                         lineterm=""))
        # Some original lines retain a final \n, normalize display in code fences.
        lines += [f"### `{c.relative}`", "", "```diff"]
        for part in diff[:max_diff_lines]:
            lines.append(part.rstrip("\r\n"))
        if len(diff) > max_diff_lines:
            lines.append(f"... 还有 {len(diff) - max_diff_lines} 行差异未显示")
        lines += ["```", ""]
    if len(changes) > max_diffs:
        lines += [f"另外 {len(changes) - max_diffs} 个文件的详细差异未写入报告，但已列入清单。", ""]
    lines += ["## 注意", "",
              "- 本工具故意保留 `、`、括号、引号和书名号；它们属于另一项排版选择。",
              "- 本工具跳过 Markdown 表格、引用块、原题/题干等章节；复杂或含糊的文件会整体跳过。",
              "- 原文引用如果写在普通段落中，程序无法理解它是否应保持原貌；请用保护标记圈出。",
              "- 转换后仍需人工抽查，自动检测不能证明 Markdown/LaTeX 在一切插件中都绝对安全。", ""]
    return "\n".join(lines)


def atomic_write(path: Path, content: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp_path = tempfile.mkstemp(prefix=".punctuation-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def create_backup(root: Path, changes: list[Change], backup_dir: Path | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = backup_dir if backup_dir is not None else root.parent
    destination.mkdir(parents=True, exist_ok=True)
    backup_path = destination / f"{root.stem if root.is_file() else root.name}-punctuation-backup-{stamp}.zip"
    manifest = {"root": str(root), "created": stamp, "files": []}
    with zipfile.ZipFile(backup_path, "x", zipfile.ZIP_DEFLATED) as bundle:
        for change in changes:
            bundle.writestr("original/" + change.relative.replace(os.sep, "/"), change.old)
            manifest["files"].append({"path": change.relative,
                                      "sha256_before": hashlib.sha256(change.old).hexdigest(),
                                      "sha256_after": hashlib.sha256(change.new).hexdigest()})
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    # Verify archive contents before allowing any writes.
    with zipfile.ZipFile(backup_path, "r") as bundle:
        for change in changes:
            packed = bundle.read("original/" + change.relative.replace(os.sep, "/"))
            if packed != change.old:
                raise OSError(f"备份校验失败：{change.relative}")
    return backup_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="安全预览/转换 Obsidian 数学库的 B+ 英文标点（默认不修改文件）。")
    parser.add_argument("target", type=Path, help="Obsidian 库的文件夹路径（也可指定单个 .md 文件）")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--dry-run", action="store_true", help="只预览，不修改文件（默认）")
    actions.add_argument("--apply", action="store_true", help="创建备份后写入所有安全的变更")
    parser.add_argument("--report", type=Path, help="Markdown 报告的保存位置（默认在知识库旁边）")
    parser.add_argument("--backup-dir", type=Path, help="--apply 时保存 ZIP 备份的目录；推荐选知识库之外的本地目录")
    parser.add_argument("--max-diffs", type=int, default=15, help="报告展示详细差异的文件数，默认 15")
    args = parser.parse_args(argv)

    root = args.target.expanduser().resolve()
    if not root.exists() or (root.is_file() and root.suffix.lower() != ".md"):
        parser.error("目标必须是已经存在的 Obsidian 文件夹或 .md 文件")
    if args.max_diffs < 0:
        parser.error("--max-diffs 不能小于 0")

    report = (args.report.expanduser().resolve() if args.report else
              root.parent / f"{root.stem if root.is_file() else root.name}-punctuation-{'applied' if args.apply else 'preview'}.md")
    if root.is_dir() and (report == root or root in report.parents):
        parser.error("报告应保存在知识库外，避免在扫描/同步时混入知识笔记")
    if root.is_file() and report == root:
        parser.error("报告不能覆盖原始 Markdown 文件")
    backup_dir = args.backup_dir.expanduser().resolve() if args.backup_dir else None
    if backup_dir is not None and (backup_dir == root or (root.is_dir() and root in backup_dir.parents)):
        parser.error("备份目录必须位于目标知识库之外")

    print(f"扫描：{root}")
    scanned, protected, changes, skipped = analyze(root)
    print(f"共 {scanned} 篇 Markdown；拟修改 {len(changes)} 篇；跳过 {len(skipped)} 篇。")
    backup_str = None
    if args.apply and changes:
        try:
            backup = create_backup(root, changes, backup_dir=backup_dir)
        except OSError as exc:
            print(f"无法创建或校验备份，未执行写入：{exc}", file=sys.stderr)
            return 2
        backup_str = str(backup)
        print(f"原文件备份：{backup}")
        done = 0
        try:
            for change in changes:
                # Abort if anything changed since the preview scan.
                if change.path.read_bytes() != change.old:
                    raise OSError(f"文件已在扫描后变化，停止写入：{change.relative}")
                atomic_write(change.path, change.new)
                done += 1
        except OSError as exc:
            print(f"写入中断（已经修改 {done} 篇，保留备份用于恢复）：{exc}", file=sys.stderr)
            return 3
        print(f"已写入 {done} 篇。")
    elif not args.apply:
        print("只读预览：未修改任何笔记。")

    try:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(generate_report(root, scanned, protected, changes, skipped,
                                          max_diffs=args.max_diffs,
                                          backup=backup_str), encoding="utf-8")
    except OSError as exc:
        print(f"报告写入失败：{exc}", file=sys.stderr)
        return 4
    print(f"报告：{report}")
    if skipped:
        print("注意：部分文件因为不确定的语法而被跳过；请查看报告。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
