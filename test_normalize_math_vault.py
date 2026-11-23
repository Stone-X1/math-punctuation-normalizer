#!/usr/bin/env python3
"""Offline regression tests: python3 -m unittest -v test_normalize_math_vault.py"""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from normalize_math_vault import UnsafeMarkdown, transform, main
from restore_math_vault import main as restore


class ParagraphTests(unittest.TestCase):
    def check(self, before, after):
        self.assertEqual(transform(before).text, after)
        self.assertEqual(transform(after).text, after, 'Not idempotent')

    def test_basic(self):
        self.check('设函数连续，且导数大于零。因此，函数递增。',
                   '设函数连续, 且导数大于零. 因此, 函数递增.')

    def test_colon_semicolon(self):
        self.check('思路：分类讨论；结论：成立。', '思路: 分类讨论; 结论: 成立.')

    def test_question_exclamation(self):
        self.check('为什么？注意！', '为什么? 注意!')

    def test_existing_ascii_punctuation_spacing(self):
        self.check('条件,结论.因此,  接着讨论.', '条件, 结论. 因此, 接着讨论.')

    def test_existing_ascii_space(self):
        self.check('因此, 已知. 所以', '因此, 已知. 所以')

    def test_no_trailing_space(self):
        self.check('正确。\n错误，\n', '正确.\n错误,\n')

    def test_crlf_preserved(self):
        self.check('已知，条件。\r\n因此，成立。\r\n', '已知, 条件.\r\n因此, 成立.\r\n')

    def test_fullwidth_dot(self):
        self.check('函数递增．因此成立．', '函数递增. 因此成立.')

    def test_keep_dunhao_brackets_titles(self):
        self.check('《教材》中的函数、导数（初步）很重要。',
                   '《教材》中的函数、导数（初步）很重要.')

    def test_close_quote(self):
        self.check('他说：“成立。”', '他说: “成立.”')

    def test_markdown_emphasis_closing(self):
        self.check('**结论。** 以及 *推论。*', '**结论.** 以及 *推论.*')
        self.check('~~不成立。~~', '~~不成立.~~')

    def test_han_surrounds_ascii_dot(self):
        self.check('命题成立.下面证明。', '命题成立. 下面证明.')

    def test_decimal_and_numeric_list(self):
        self.check('1. 第一步：设 $x=3.14$。', '1. 第一步: 设 $x=3.14$.')

    def test_repeated_punctuation(self):
        self.check('为什么？！请注意！！', '为什么?! 请注意!!')

    def test_hard_rule_inline_cjk(self):
        self.check('理由：$f(x,y)$，故成立。', '理由: $f(x,y)$, 故成立.')


class ProtectedSyntaxTests(unittest.TestCase):
    def check(self, before, after):
        self.assertEqual(transform(before).text, after)
        self.assertEqual(transform(after).text, after)

    def test_inline_dollar_math(self):
        self.check('设 $f(x,y)=x^2+y^2$，且 $x=1.2$。',
                   '设 $f(x,y)=x^2+y^2$, 且 $x=1.2$.')

    def test_double_dollar_block(self):
        s = '由此，得到\n$$\n\\begin{aligned}\na，b &=1.2;\\\\\nc,d &= 3.4.\n\\end{aligned}\n$$\n因此，成立。\n'
        expected = s.replace('由此，得到', '由此, 得到').replace('因此，成立。', '因此, 成立.')
        self.check(s, expected)

    def test_inline_double_dollar_protect_whole_line(self):
        s = '设定，$$a，b=1.2$$，得到结论。\n因此，成立。'
        self.check(s, '设定，$$a，b=1.2$$，得到结论。\n因此, 成立.')

    def test_backslash_math_inline(self):
        self.check(r'考虑 \(x,y\) ，因此成立。', r'考虑 \(x,y\) , 因此成立.')

    def test_backslash_math_block(self):
        s = '因此，\n\\[\nx，y=3.14\n\\]\n故，成立。\n'
        self.check(s, '因此,\n\\[\nx，y=3.14\n\\]\n故, 成立.\n')

    def test_code_inline(self):
        self.check('文字，`a，b=3.14`。', '文字, `a，b=3.14`.')

    def test_code_fence(self):
        s = '开始，\n```python\nprint("你好，世界。")\n```\n结束。\n'
        self.check(s, '开始,\n```python\nprint("你好，世界。")\n```\n结束.\n')

    def test_yaml_frontmatter(self):
        s = '---\ntitle: 连续，导数。\ntags: [解析，讨论]\n---\n正文，继续。\n'
        self.check(s, '---\ntitle: 连续，导数。\ntags: [解析，讨论]\n---\n正文, 继续.\n')

    def test_wikilink_and_link(self):
        s = '参考[[导数，理论|例子。]]，以及[资料，原文](https://example.com/a,b?q=1.2)。'
        self.check(s, '参考[[导数，理论|例子。]], 以及[资料，原文](https://example.com/a,b?q=1.2).')

    def test_bare_url(self):
        s = '查看 https://example.com/a,b?p=3.14，然后继续。'
        self.check(s, '查看 https://example.com/a,b?p=3.14, 然后继续.')

    def test_url_inside_code(self):
        s = '`https://example.com/你好，测试`，可以。'
        self.check(s, '`https://example.com/你好，测试`, 可以.')

    def test_inline_html(self):
        s = '文字，<span title="含中文，逗号">例子，结束。</span>'
        self.check(s, '文字, <span title="含中文，逗号">例子, 结束.</span>')

    def test_html_raw_block(self):
        s = '<pre>\n正文，禁止修改。\n</pre>\n下文，修改。'
        self.check(s, '<pre>\n正文，禁止修改。\n</pre>\n下文, 修改.')

    def test_indented_code(self):
        s = '说明，\n    code a，b。\n正文，结束。'
        self.check(s, '说明,\n    code a，b。\n正文, 结束.')

    def test_math_with_escaped_dollar(self):
        s = r'价钱为 \$20，记作 $x=2.3$。'
        self.check(s, r'价钱为 \$20, 记作 $x=2.3$.')

    def test_table_untouched(self):
        s = '| 指标，x | 备注。 |\n|---|---|\n| 1.2 | 中文，说明。 |\n正文，继续。'
        self.check(s, '| 指标，x | 备注。 |\n|---|---|\n| 1.2 | 中文，说明。 |\n正文, 继续.')

    def test_quote_untouched(self):
        s = '> 原题，保持不变。\n普通解释，修改。'
        self.check(s, '> 原题，保持不变。\n普通解释, 修改.')

    def test_preserve_obisidian_heading_anchors(self):
        s = ('## 第一问：切点处同时读出函数值和斜率\n'
             '详见[[数学/切线#第一问：切点处同时读出函数值和斜率|对应证明]]，结论成立。\n'
             '### 单调性：函数递增，保持标题\n'
             "证明如下：由 $f'(x)>0$ 可得结论。")
        expected = ('## 第一问：切点处同时读出函数值和斜率\n'
                    '详见[[数学/切线#第一问：切点处同时读出函数值和斜率|对应证明]], 结论成立.\n'
                    '### 单调性：函数递增，保持标题\n'
                    "证明如下: 由 $f'(x)>0$ 可得结论.")
        self.check(s, expected)

    def test_special_headings(self):
        s = '# 内容\n## 原题\n设函数，求导数。\n### 细则\n原文，保持。\n## 分析\n因此，成立。'
        self.check(s, '# 内容\n## 原题\n设函数，求导数。\n### 细则\n原文，保持。\n## 分析\n因此, 成立.')

    def test_manual_off_on(self):
        s = '前，改。\n<!-- punctuation: off -->\n这段，禁止。\n<!-- punctuation: on -->\n后，改。'
        self.check(s, '前, 改.\n<!-- punctuation: off -->\n这段，禁止。\n<!-- punctuation: on -->\n后, 改.')

    def test_obsidian_comment(self):
        s = '前，修改。\n%%\n隐藏，保持。\n%%\n后，修改。'
        self.check(s, '前, 修改.\n%%\n隐藏，保持。\n%%\n后, 修改.')

    def test_latex_begin_end_outside_math(self):
        s = '前，修改。\n\\begin{aligned}\nx，y\n\\end{aligned}\n后，修改。'
        self.check(s, '前, 修改.\n\\begin{aligned}\nx，y\n\\end{aligned}\n后, 修改.')

    def test_preserve_utf8_bom(self):
        self.check('\ufeff前，后。\n', '\ufeff前, 后.\n')

    def test_unclosed_dollar_rejected(self):
        with self.assertRaises(UnsafeMarkdown):
            transform('前，$x=2，后。')

    def test_unclosed_fence_rejected(self):
        with self.assertRaises(UnsafeMarkdown):
            transform('```python\na，b')

    def test_unclosed_manual_guard_rejected(self):
        with self.assertRaises(UnsafeMarkdown):
            transform('<!-- punctuation: off -->\n原文，未关闭。')


class IntegrationTests(unittest.TestCase):
    def test_custom_backup_directory_outside_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            vault = parent / 'vault'
            vault.mkdir()
            (vault / 'a.md').write_text('先，后。', encoding='utf-8')
            backups = parent / 'independent-backups'
            self.assertEqual(main([str(vault), '--apply', '--backup-dir', str(backups)]), 0)
            archives = list(backups.glob('vault-punctuation-backup-*.zip'))
            self.assertEqual(len(archives), 1)
            self.assertEqual((vault / 'a.md').read_text(), '先, 后.')

    def test_preview_apply_backup_and_excludes(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            vault = parent / 'Mathematics Vault'
            vault.mkdir()
            content = '设函数 $f(x,y)$，则得到结论。\n'.encode()
            (vault / 'note.md').write_bytes(content)
            (vault / 'other.md').write_text('```math\n未闭合。', encoding='utf-8')
            (vault / '.obsidian').mkdir()
            (vault / '.obsidian' / 'settings.md').write_text('不转换，保持。')
            self.assertEqual(main([str(vault)]), 0)
            self.assertEqual((vault / 'note.md').read_bytes(), content)
            self.assertTrue((parent / 'Mathematics Vault-punctuation-preview.md').exists())
            report = (parent / 'Mathematics Vault-punctuation-preview.md').read_text()
            self.assertIn('待修改文件：**1**', report)
            self.assertIn('跳过的文件：**1**', report)
            self.assertEqual(main([str(vault), '--apply']), 0)
            self.assertEqual((vault / 'note.md').read_text(), '设函数 $f(x,y)$, 则得到结论.\n')
            self.assertEqual((vault / 'other.md').read_text(), '```math\n未闭合。')
            archives = list(parent.glob('*punctuation-backup*.zip'))
            self.assertEqual(len(archives), 1)
            with zipfile.ZipFile(archives[0]) as bundle:
                self.assertEqual(bundle.read('original/note.md'), content)
                manifest = json.loads(bundle.read('manifest.json'))
                self.assertEqual(manifest['files'][0]['path'], 'note.md')
            self.assertEqual(main([str(vault), '--apply']), 0)
            self.assertEqual(len(list(parent.glob('*punctuation-backup*.zip'))), 1)


    def test_restore_and_conflict_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            vault = parent / 'vault'
            vault.mkdir()
            (vault / 'a.md').write_text('先，后。', encoding='utf-8')
            self.assertEqual(main([str(vault), '--apply']), 0)
            archive = next(parent.glob('vault-punctuation-backup-*.zip'))
            self.assertEqual(restore([str(vault), str(archive)]), 0)
            self.assertEqual((vault / 'a.md').read_text(), '先, 后.')
            self.assertEqual(restore([str(vault), str(archive), '--apply']), 0)
            self.assertEqual((vault / 'a.md').read_text(), '先，后。')

        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            vault = parent / 'vault'
            vault.mkdir()
            (vault / 'a.md').write_text('先，后。', encoding='utf-8')
            self.assertEqual(main([str(vault), '--apply']), 0)
            archive = next(parent.glob('vault-punctuation-backup-*.zip'))
            (vault / 'a.md').write_text('人工后续编辑，不能覆盖。', encoding='utf-8')
            self.assertEqual(restore([str(vault), str(archive), '--apply']), 3)
            self.assertEqual((vault / 'a.md').read_text(), '人工后续编辑，不能覆盖。')


if __name__ == '__main__':
    unittest.main()
