from __future__ import annotations

import json
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = SKILLS_ROOT / "writing-router" / "references" / "document-version-protection.md"
SKILL_PATHS = {
    "writing-router": SKILLS_ROOT / "writing-router" / "SKILL.md",
    "project-writing": SKILLS_ROOT / "project-writing" / "SKILL.md",
    "ieee-manuscript-edit": SKILLS_ROOT / "ieee-manuscript-edit" / "SKILL.md",
    "latex-paper": SKILLS_ROOT / "latex-paper" / "SKILL.md",
}
EVAL_PATHS = {
    name: path.parent / "evals" / "evals.json" for name, path in SKILL_PATHS.items()
}


def require(text: str, fragment: str, location: Path) -> None:
    if fragment not in text:
        raise AssertionError(f"{location} missing required fragment: {fragment}")


def main() -> None:
    reference_text = REFERENCE.read_text(encoding="utf-8")
    reference_fragments = [
        "git init -b main",
        "D:\\BaiduSyncdisk\\Paper",
        "被误初始化的公共父目录",
        "修改前 baseline",
        "git diff --cached --check -- <本轮文件清单>",
        "禁止 `git add .`",
        "文稿：<文件或章节>｜<修改目的>",
        "milestone/YYYYMMDD-HHmmss-<类型>",
        "验证失败时不创建正常 commit",
        "不执行 `git remote add`、`git push`",
        "不得使用 `git reset --hard`、`git checkout --`",
    ]
    for fragment in reference_fragments:
        require(reference_text, fragment, REFERENCE)

    combined_eval_text = ""
    for skill_name, skill_path in SKILL_PATHS.items():
        skill_text = skill_path.read_text(encoding="utf-8")
        require(skill_text, "document-version-protection.md", skill_path)
        require(skill_text, "里程碑", skill_path)

        eval_path = EVAL_PATHS[skill_name]
        payload = json.loads(eval_path.read_text(encoding="utf-8"))
        if payload.get("skill_name") != skill_name:
            raise AssertionError(f"{eval_path} skill_name mismatch")
        if not payload.get("evals"):
            raise AssertionError(f"{eval_path} has no evals")
        combined_eval_text += json.dumps(payload, ensure_ascii=False)

    eval_fragments = [
        "git init -b main",
        "baseline",
        "只读任务不触发",
        "无关",
        "每轮只创建一个本地 commit",
        "annotated",
        "不 push",
        "git reset --hard",
        "旧版本",
    ]
    for fragment in eval_fragments:
        require(combined_eval_text, fragment, Path("combined writing evals"))

    print("document version protection static tests passed")


if __name__ == "__main__":
    main()
