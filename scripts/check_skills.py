#!/usr/bin/env python3
"""技能仓库体检：只报告，不修改任何文件。

用法：
    python scripts/check_skills.py            # 检查当前仓库
    python scripts/check_skills.py <repo根>   # 检查指定目录

退出码：0 = 无错误，1 = 有错误（提示不影响退出码）。只依赖标准库。
"""

import os
import re
import sys

SKILL = "SKILL.md"
TEXT_EXT = {".md", ".json", ".yaml", ".yml", ".toml"}
PRIVATE_PATH = re.compile(r"(?:^|[\s`\"'(])[A-Za-z]:\\|/Users/|/home/")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
MAX_DESC = 1024
SOFT_DESC = 500
MAX_LINES = 500
BIG_FILE = 512 * 1024


def frontmatter(text):
    """只解析顶层 key: value；description 支持 > / | 折叠块。"""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    data, key = {}, None
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            data[key] = [] if val in (">", "|", ">-", "|-") else [val]
        elif key and line[:1] in (" ", "\t"):
            data[key].append(line.strip())
        else:
            key = None
    out = {}
    for k, parts in data.items():
        val = " ".join(p for p in parts if p).strip()
        if len(val) > 1 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1].replace('\\"', '"')
        out[k] = val
    return out


def check_frontmatter(root, d):
    errors, warnings = [], []
    path = os.path.join(root, d, SKILL)
    text = open(path, encoding="utf-8", errors="replace").read()
    fm = frontmatter(text)
    if fm is None:
        return [f"{d}/{SKILL}: 缺少 YAML frontmatter"], []
    if fm.get("name") != d:
        errors.append(f"{d}/{SKILL}: name={fm.get('name')!r} 与目录名不一致")
    desc = fm.get("description", "")
    if not desc:
        errors.append(f"{d}/{SKILL}: 缺少 description")
    elif len(desc) > MAX_DESC:
        errors.append(f"{d}/{SKILL}: description {len(desc)} 字符，超过 {MAX_DESC} 上限会被截断")
    elif len(desc) > SOFT_DESC:
        warnings.append(f"{d}/{SKILL}: description {len(desc)} 字符，超过建议值 {SOFT_DESC}")
    if len(text.splitlines()) > MAX_LINES:
        warnings.append(f"{d}/{SKILL}: {len(text.splitlines())} 行，建议把细节下沉到 references/")
    has_license = bool(fm.get("license")) or any(
        os.path.exists(os.path.join(root, d, n)) for n in ("LICENSE", "LICENSE.txt", "LICENSE.md", "NOTICE"))
    if not has_license:
        upstream = os.path.join(root, d, "references", "upstream-sources.md")
        if os.path.exists(upstream) and "仓库：" in open(upstream, encoding="utf-8", errors="replace").read():
            warnings.append(f"{d}/: upstream-sources 登记了实际上游，但目录内没有 LICENSE/NOTICE")
        elif os.path.isdir(os.path.join(root, d, "scripts", "office")):
            warnings.append(f"{d}/: 含有 scripts/office 共享工具集（疑似 Anthropic office 技能衍生），但没有 LICENSE/NOTICE")
    return errors, warnings


def check_files(root):
    errors, warnings = [], []
    for base, subdirs, names in os.walk(root):
        subdirs[:] = [s for s in subdirs if s != ".git"]
        for n in names:
            path = os.path.join(base, n)
            rel = os.path.relpath(path, root)
            size = os.path.getsize(path)
            if size > BIG_FILE:
                warnings.append(f"{rel}: {size // 1024} KB，可考虑 LFS 或 releases")
            if os.path.splitext(n)[1] not in TEXT_EXT or size > 2 * 1024 * 1024:
                continue
            body = open(path, encoding="utf-8", errors="replace").read()
            if n.endswith(".md"):
                for target in MD_LINK.findall(body):
                    target = target.split("#")[0].strip()
                    if target and not target.startswith(("http://", "https://", "mailto:", "#")):
                        if not os.path.exists(os.path.normpath(os.path.join(base, target))):
                            errors.append(f"{rel}: 链接指向不存在的路径 {target}")
            for i, line in enumerate(body.splitlines(), 1):
                if PRIVATE_PATH.search(line) and not re.search(r"[A-Za-z]:\\path\\", line):
                    warnings.append(f"{rel}:{i}: 写死了本机私有路径 {line.strip()[:80]}")
    return errors, warnings


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), ".."))
    dirs = sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)) and not d.startswith("."))
    skills = [d for d in dirs if os.path.isfile(os.path.join(root, d, SKILL))]
    errors, warnings = [], []
    for d in dirs:
        if d not in skills:
            warnings.append(f"{d}/: 顶层目录但没有 {SKILL}，cc-switch 侧会当成无效技能")
        if os.path.isdir(os.path.join(root, d, ".github")):
            errors.append(f"{d}/.github/: 不会被执行，GitHub 只运行仓库根的 .github/workflows/")
    for d in skills:
        e, w = check_frontmatter(root, d)
        errors += e
        warnings += w
    e, w = check_files(root)
    errors += e
    warnings += w
    for label, items in (("错误", errors), ("提示", warnings)):
        print(f"{label}：{len(items)}")
        for it in items:
            print(f"  - {it}")
        print()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
