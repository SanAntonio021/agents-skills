from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def section(text: str, number: str) -> str:
    pattern = rf"\*{{0,2}}场景{number}\*{{0,2}}(.*?)(?=\*{{0,2}}场景[一二三]\*{{0,2}}|\Z)"
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1) if match else ""


def grade(output: str) -> dict[str, object]:
    first = section(output, "一")
    second = section(output, "二")
    third = section(output, "三")

    checks = [
        (
            "过大公共目录被拦截，并要求切到具体项目根目录",
            bool(
                re.search(r"(禁止|拒绝|停止).{0,80}D:\\BaiduSyncdisk\\Paper", first, re.DOTALL)
                and re.search(r"(具体项目|项目根|具体论文项目)", first)
            ),
            first.strip(),
        ),
        (
            "无 Git 时把初始化许可和 baseline 许可合并为一次询问",
            all(token in first for token in ("询问", "初始化", "baseline")),
            first.strip(),
        ),
        (
            "修改验证通过后只创建本地 commit，默认不 push",
            bool(
                re.search(r"验证.{0,40}(本地 )?commit", first, re.DOTALL)
                and re.search(r"不.{0,12}push", first, re.IGNORECASE)
            ),
            first.strip(),
        ),
        (
            "只读审查不触发初始化、commit、tag 或 push",
            bool(
                any(token in second for token in ("只读", "只审不改", "不修改"))
                and re.search(r"(不.{0,20}(初始化|版本保护)|初始化[：:]否)", second)
                and re.search(r"(不.{0,12}commit|commit[：:]否)", second, re.IGNORECASE)
                and re.search(r"(不.{0,12}tag|tag[：:]否)", second, re.IGNORECASE)
                and re.search(r"(不.{0,12}push|push[：:]否)", second, re.IGNORECASE)
            ),
            second.strip(),
        ),
        (
            "明确投稿候选时创建 annotated milestone tag，不创建空 commit",
            bool(
                re.search(r"annotated tag", third, re.IGNORECASE)
                and "milestone/" in third
                and re.search(r"不.{0,12}空 commit", third)
            ),
            third.strip(),
        ),
        (
            "三个场景都不执行 push",
            output.lower().count("push") >= 3
            and not re.search(r"(?<!不)(?<!不再)(执行|进行|随后|然后).{0,8}push", output, re.IGNORECASE),
            "push mentions: " + str(output.lower().count("push")),
        ),
    ]

    expectations = [
        {"text": text, "passed": passed, "evidence": evidence}
        for text, passed, evidence in checks
    ]
    passed_count = sum(1 for item in expectations if item["passed"])
    return {
        "expectations": expectations,
        "summary": {
            "passed": passed_count,
            "failed": len(expectations) - passed_count,
            "total": len(expectations),
            "pass_rate": passed_count / len(expectations),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    result = grade(args.output.read_text(encoding="utf-8-sig"))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
