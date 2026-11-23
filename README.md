# Obsidian 数学库标点规范化工具（B+）

这是一个**本地运行、只使用 Python 标准库**的 Markdown 批量转换工具（安全修订版 v1.1）。不上传你的笔记、不调用 API、不需要 Codex，也不需要安装第三方 Python 包。

**请先完整备份知识库，且始终先预览差异。脚本通过自动化测试不代表能够理解任何 Markdown 插件的所有语法。**

## 1. B+ 规则是什么

只在普通文字中，将下列标点改为西文半角形式，并在行内文字继续时按规则补一个空格：

| 原标点 | 目标标点 |
|---|---|
| `，` | `,` |
| `。`、`．` | `.` |
| `；` | `;` |
| `：` | `:` |
| `？` | `?` |
| `！` | `!` |

示例：

```markdown
修改前：设函数 $f(x,y)$，因此，得到结论。
修改后：设函数 $f(x,y)$, 因此, 得到结论.
```

还会在能判断是中文正文标点的情况下，补全**已有半角标点**后缺失的空格，例如 `因此,成立` 变为 `因此, 成立`。不会在小数 `3.14` 中加空格。

当前版本**刻意保留**中文顿号 `、`、中文括号 `（）`、引号 `“”`、书名号 `《》`，避免擅自决定这些字符的排版体例。此工具不是全面的英文翻译或所有标点的一键半角化。

## 2. 保护哪些内容

- `$...$`、`$$...$$`、`\(...\)`、`\[...\]` 中的数学表达；`\begin{...}` 到 `\end{...}` 的数学环境。
- 反引号包围的行内代码、围栏代码块。
- YAML frontmatter、HTML 注释、Obsidian `%%...%%` 注释。
- Markdown 链接和地址、`[[双链]]`、裸露网址。
- **所有 Markdown 标题行（`#` 至 `######`）原样保留。** 这样不会把原有标题改名，避免 `[[笔记#原标题]]`、跨目录或跨知识库的标题引用失效。标题可能仍然使用中文标点；这是刻意的安全取舍。
- Markdown 表格、引用块、缩进代码、脚注定义等会被保守跳过。
- `## 原题`、`## 题目`、`## 题干` 等特定标题下的正文会跳过，直到同级或更高级标题出现。
- 不确定边界的文件会**整体跳过，并在报告中注明**，不会冒险修改。

**限制：** 无法自动判断一段普通正文是否为教材或试题的逐字引用；没有可识别分隔符的数学表达也不一定能被识别；较复杂的插件私有语法可能无法被完整解析。需要保持原文的段落，请用下面的保护标记：

```markdown
<!-- punctuation: off -->
这里是教材原文，保留原样。
<!-- punctuation: on -->
```

保护标记必须独占一行并成对出现。

## 3. 在 Mac 上使用（不需要编程知识）

1. 将 ZIP 解压到 Mac 的 `下载` 文件夹。**不要把脚本文件放进 Obsidian 知识库。**
2. 打开终端，输入 `python3 --version`，确认已安装 Python 3.9 或更新版本。
3. **使用 Finder 将整个数学知识库文件夹完整复制一份**，避免任何不可预见的文件损失。
4. 在终端运行下面的命令。将双引号内的文件夹路径替换为你自己的数学知识库路径。路径中有空格时也能使用：

```bash
python3 ~/Downloads/math-punctuation-tool/normalize_math_vault.py "/Users/你的用户名/Obsidian/数学知识库"
```

> 路径不确定？在终端输入 `python3`、一个空格，再将脚本拖进终端；之后再输入一个空格，把 Obsidian 知识库文件夹拖进终端。按回车即可。拖入会自动填充真实路径。

默认是**只读预览**。脚本会显示扫描和待修改文件数量，并在知识库**同级目录**创建报告，例如：

```text
数学知识库-punctuation-preview.md
```

使用 Obsidian 或文本编辑器打开这个报告，检查 `diff`：以 `-` 开头的行为修改前，以 `+` 开头的行为修改后。

### 确认报告无问题后，才执行修改

```bash
python3 ~/Downloads/math-punctuation-tool/normalize_math_vault.py "/Users/你的用户名/Obsidian/数学知识库" --apply
```

执行时脚本先把所有待修改的**原文件**打包成一个 ZIP 备份，放在知识库的同级目录，然后逐篇写入：

```text
数学知识库-punctuation-backup-YYYYMMDD-HHMMSS-xxxxxx.zip
数学知识库-punctuation-applied.md
```

既有的 `.md` 文件名、相对路径、换行符、UTF-8 BOM 都会保留。`.obsidian`、`.git`、`.trash` 等目录及符号链接会跳过。重复执行应不会对已经符合规则的内容造成新的改动。

### 先单独测试一篇笔记

脚本也可以直接指定一个 `.md` 文件：

```bash
python3 ~/Downloads/math-punctuation-tool/normalize_math_vault.py "/Users/你的用户名/Obsidian/数学知识库/导数.md"
```

确认效果后可以对单篇执行 `--apply`，然后再处理全库。**测试阶段最好使用 Finder 复制出来的一篇笔记，而不是直接操作唯一原件。**

## 4. 如何恢复

如果执行过 `--apply`，运行 ZIP 中的恢复脚本。默认依然只预览：

```bash
python3 ~/Downloads/math-punctuation-tool/restore_math_vault.py "/Users/你的用户名/Obsidian/数学知识库" "/备份所在位置/数学知识库-punctuation-backup-XXXX.zip"
```

仔细检查输出后执行：

```bash
python3 ~/Downloads/math-punctuation-tool/restore_math_vault.py "/Users/你的用户名/Obsidian/数学知识库" "/备份所在位置/数学知识库-punctuation-backup-XXXX.zip" --apply
```

恢复脚本会验证 ZIP 中的原文件及**当前文件是否仍与当初转换的版本相同**。如果某篇笔记在转换后又被你修改，它会拒绝覆盖该文件，以免丢失后来的新内容；如果有任何这类冲突，默认会停止整批恢复。恢复前还会再创建一次当前文件的 ZIP 备份。

如果知识库在多台设备间同步，建议暂时停止其他设备编辑，并在备份完成后再批量执行。

**iCloud 用户建议：** 运行 `--apply` 时指定 `--backup-dir`，将备份放在本地非 iCloud 同步文件夹，例如：

```bash
python3 normalize_math_vault.py "/path/to/vault" --apply --backup-dir "$HOME/Developer/math-punctuation-normalizer/backups"
```

这项参数在 v1.1 中增加。不指定时，脚本仍在知识库同级目录备份；如果知识库位于 iCloud，则默认备份也位于 iCloud。

## 5. 运行自动测试

在终端进入解压后的文件夹：

```bash
cd ~/Downloads/math-punctuation-tool
python3 -m unittest -v test_normalize_math_vault.py
```

测试覆盖公式、代码块、表格、链接、标点间距、CRLF、备份和恢复等场景。测试在独立临时文件夹运行，不会读取或更改你的数学知识库。

## 6. 进阶参数

```bash
# 只预览，显式写法
python3 normalize_math_vault.py "/path/to/vault" --dry-run

# 更多文件的详细 diff（报告默认只列出前 15 个文件的详细 diff）
python3 normalize_math_vault.py "/path/to/vault" --max-diffs 100

# 将报告保存到指定位置（请选知识库以外的路径）
python3 normalize_math_vault.py "/path/to/vault" --report ~/Desktop/数学标点检查.md

# 帮助
python3 normalize_math_vault.py --help
```

## 7. 重要局限

这是一套保守的、确定性文本转换工具，而非完整 CommonMark、Obsidian 和 MathJax 联合语法解析器。脚本**可以保护其识别的标准公式环境**，但不应据此保证能识别所有手写数学语法和插件语法。对真实大型知识库，强烈建议先在备份副本运行，审查多种笔记类型，再对正式库执行。

## v1.1 修订说明

根据 217 篇笔记的 dry-run 报告发现：旧版会修改 `## 第一问：...` 这样的标题，
而原有 `[[笔记#第一问：...]]` 引用不会同时更新，存在跳转失效风险。
本版保守跳过全部 Markdown 标题，不转换其标点，并新增 `--backup-dir` 支持本地独立备份。原有预览报告须作废，
替换脚本后重新运行 `--dry-run`，确认差异后才能执行 `--apply`。

注意：自动测试并不能证明所有 Obsidian 插件语法都安全；对于跨知识库链接、
未标注的原题引用、标题以外的块引用等仍需抽查。
