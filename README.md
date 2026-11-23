# Math Punctuation Normalizer

**A conservative, dependency-free Python CLI for normalizing punctuation in Chinese mathematical Markdown notes while protecting commonly recognized LaTeX and Markdown syntax.**

[中文说明](#中文说明) · [English](#english)

> **Important:** Preview changes first and keep an independent backup. This tool is not a complete Markdown, Obsidian, or MathJax parser. It may skip supported-looking but ambiguous content, and unrecognized syntax may still be changed.

## 中文说明

### 简介

Math Punctuation Normalizer 是一个使用 Python 标准库实现的命令行工具，用于将中文数学 Markdown 笔记中的部分标点统一为 **B+ 风格**：正文主要使用西文半角句读，并在后面需要接续文字时添加一个空格。工具尽量保留已识别的 LaTeX 公式与 Markdown 结构；默认只生成预览报告，不修改笔记。

它可以处理 Obsidian 知识库中的 Markdown 文件，但**不是 Obsidian 插件**，不需要安装 Obsidian 或连接云端服务。

### 转换示例

**输入：**

```markdown
设函数 $f(x,y)=x^2+y^2$，则有：

$$
f(1,2)=5.
$$

因此，结论成立。
```

**输出：**

```markdown
设函数 $f(x,y)=x^2+y^2$, 则有:

$$
f(1,2)=5.
$$

因此, 结论成立.
```

常规映射：`， → ,`、`。/． → .`、`； → ;`、`： → :`、`？ → ?`、`！ → !`。在可判定的中文正文场景下，也会为已有半角标点补足空格。保留 `、`、中文括号、引号、书名号等字符；并非全面 ASCII 化。

### 功能与保护范围

- 默认只读预览；使用 `--apply` 才写入。
- 扫描单篇 `.md` 文件或整个目录；忽略常见配置、代码缓存目录及符号链接。
- 尽量保护 `$...$`、`$$...$$`、`\(...\)`、`\[...\]`、`\begin{...}` / `\end{...}` 数学环境、行内和围栏代码、YAML、链接、网址和 Obsidian 双链。
- 为了避免破坏标题锚点，保留所有 ATX Markdown 标题行；表格、引用块、某些题干章节等也会保守跳过。
- 生成包含变更摘要和部分 diff 的 Markdown 报告。
- 批量写入前将待修改的原文件打包到 ZIP，并在写入前核验备份内容。
- 附带 `restore_math_vault.py`；恢复时校验当前文件哈希，避免覆盖恢复前已有的新编辑。

**限制：**保护是基于已识别语法的尽力处理，不能保证识别所有 Obsidian 插件语法、嵌套 Markdown 或非标准数学表达。部分文件可能被跳过，命令仍可能返回成功状态；务必检查报告的“跳过文件及原因”。原题/题干章节可能保持原标点。转换器不会替你检查数学推导正确性。

### 环境要求

- Python **3.9 或更新版本**（标准库，无第三方依赖）。
- 已有 Markdown 文件。无需安装 Obsidian。
- 当前主要在 macOS 上实测；其他操作系统的兼容性以独立测试结果为准。

### 安装

克隆仓库（公开后替换为真实地址）：

```bash
# git clone https://github.com/Stone-X1/math-punctuation-normalizer.git
# cd math-punctuation-normalizer
```

在发布前，你也可以直接使用本地项目目录中的 Python 文件。仓库不需要 `pip install`。

### 使用：预览 → 审查 → 应用

在仓库目录执行，以下示例路径均为占位符：

```bash
# 1. 只读预览（默认行为）
python3 normalize_math_vault.py "/path/to/your/markdown-vault" --dry-run

# 2. 详细显示更多文件的 diff
python3 normalize_math_vault.py "/path/to/your/markdown-vault" --max-diffs 30

# 3. 完整备份知识库到其他位置；确认预览报告后再执行写入
python3 normalize_math_vault.py "/path/to/your/markdown-vault" \
  --apply --backup-dir "/path/outside/the/vault/backups"
```

脚本默认在目标文件或文件夹的**同级目录**生成 `-punctuation-preview.md` 或 `-punctuation-applied.md` 报告；如需自定义位置可使用 `--report`。报告中详细 diff 默认只展示前 15 个待修改文件，数量可通过 `--max-diffs` 修改。报告仅显示部分内容，不能代替抽查完整文件。

> 在 iCloud、Dropbox 等同步目录中批量写入前，请先保留独立的本地副本，避免多设备同时编辑。ZIP 备份只保存本次准备修改的原文件，不等于完整知识库备份。

### 恢复

恢复命令要求**文件夹路径**和对应的 ZIP 备份路径。默认只预览：

```bash
python3 restore_math_vault.py "/path/to/your/markdown-vault" "/path/to/backup.zip"

# 检查输出且确认后，再实际恢复
python3 restore_math_vault.py "/path/to/your/markdown-vault" "/path/to/backup.zip" --apply
```

若文件在转换之后又发生修改，恢复工具会拒绝覆盖它。恢复时也会为待恢复的当前文件创建额外 ZIP 备份。恢复不是严格的全有或全无事务；遇到写入中断时应根据报告与备份检查结果。

### 手动保护区域

将不希望转换的 Markdown 内容包在以下标记中，标记单独占一行：

```markdown
<!-- punctuation: off -->
这段内容不进行标点转换。
<!-- punctuation: on -->
```

### 运行测试

```bash
python3 -m unittest -v test_normalize_math_vault.py
```

单元和集成测试使用临时目录，不需要真实数学知识库。发布前应在所声明支持的操作系统与 Python 版本上验证，而不只依赖一次本地测试。

### 开源许可

MIT License。见 [`LICENSE`](LICENSE)。

---

## English

### Overview

Math Punctuation Normalizer is a small Python command-line utility for applying a **B+ punctuation style** to Chinese mathematical Markdown notes. It converts selected Chinese sentence punctuation to ASCII punctuation and adds a following space when appropriate, while conservatively preserving recognized LaTeX and Markdown constructs.

It operates on local `.md` files and folders. **It is not an Obsidian plugin**, does not require an Obsidian installation, and uses only Python's standard library.

### What it does

- **Preview by default:** no note is rewritten unless `--apply` is passed.
- Convert common Chinese commas, periods, colons, semicolons, question marks and exclamation marks in eligible prose.
- Preserve recognized math delimiters, code, frontmatter, links, URLs and wiki links.
- Keep existing ATX headings unchanged to reduce broken heading anchors.
- Conservatively skip tables, blockquotes, selected exercise-source sections, and ambiguous documents.
- Write Markdown change reports, create ZIP backups before changes, and provide checksum-aware restoration.

It deliberately keeps ideographic commas (`、`), Chinese quotation marks, brackets and book-title marks. This tool is **not** a general-purpose Chinese-to-ASCII punctuation converter.

### Requirements

Python 3.9+; no third-party dependencies. Primarily exercised on macOS so far; do not assume full platform compatibility without testing.

### Usage

From the repository directory:

```bash
# Preview only (default)
python3 normalize_math_vault.py "/path/to/markdown-folder" --dry-run

# Preview more per-file diffs
python3 normalize_math_vault.py "/path/to/markdown-folder" --max-diffs 30

# Apply after reviewing the report and taking an independent backup
python3 normalize_math_vault.py "/path/to/markdown-folder" \
  --apply --backup-dir "/path/outside/the/folder/backups"
```

Use `--report /path/to/report.md` to choose a report destination outside the target folder. You may also pass a single `.md` file to the normalizer.

### Restore

```bash
# Preview restoration
python3 restore_math_vault.py "/path/to/markdown-folder" "/path/to/backup.zip"

# Actually restore, after reviewing the output
python3 restore_math_vault.py "/path/to/markdown-folder" "/path/to/backup.zip" --apply
```

The restore command expects a **directory**, and checks recorded SHA-256 hashes to avoid overwriting files changed after normalization. A restore operation is not transactional if an I/O error occurs midway.

### Safety and limitations

This is a conservative, deterministic text processor—not a full Markdown/Obsidian/MathJax parser. Unrecognized syntax may not be protected, some files may be skipped, and the program may still exit with status zero when skips occur. Always inspect the report, run on a copy first, and keep a full independent backup of important notes. A successful test suite is not a guarantee of correctness for arbitrary documents.

If you need a verbatim passage, add `<!-- punctuation: off -->` and `<!-- punctuation: on -->` on separate lines around it.

### Tests

```bash
python3 -m unittest -v test_normalize_math_vault.py
```

### License

MIT. See [`LICENSE`](LICENSE).
