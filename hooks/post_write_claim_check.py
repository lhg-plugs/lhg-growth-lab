#!/usr/bin/env python3
"""lhg-growth-lab 硬门②（警告级，不拦截）：写实验文档时若断言"显著"但未提样本量，提醒先验样本。

触发：PostToolUse / Write|Edit。只做提醒，永远 exit 0、不拦截写入。
只检查疑似实验文档的 markdown（路径或内容含"实验"/"显著"），其他文件快速放行。

逃生方式：LHG_GL_HOOKS_OFF=1（环境变量）可关闭本提醒；
或 /plugin disable lhg-growth-lab 停用整个插件。
零第三方依赖。
"""

import json
import os
import sys


def looks_like_experiment_doc(path, text):
    p = path.replace("\\", "/").lower()
    if any(k in p for k in ("实验", "experiment", "ab", "growth-lab")):
        return True
    head = text[:2000]
    return "实验" in head and "显著" in head


def main() -> int:
    if os.environ.get("LHG_GL_HOOKS_OFF") == "1":
        return 0

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    if not file_path:
        return 0
    if not file_path.endswith(".md"):
        return 0

    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return 0

    if not looks_like_experiment_doc(file_path, text):
        return 0  # 非实验文档：快速放行

    notes = []
    if "显著" in text and "样本量" not in text:
        notes.append("文档断言「显著」但未提样本量：先确认样本量达标（ab_stats.py samplesize），否则结论不可信。")
    if "显著" in text and "p" not in text and "P值" not in text and "p值" not in text:
        notes.append("文档谈显著但未给出 p 值：用 /lhg-growth-lab:ab-significance 跑脚本判定，不要凭感觉。")
    if not notes:
        return 0

    msg = "显著性提醒（lhg-growth-lab）：%s\n%s\n关闭本提醒：export LHG_GL_HOOKS_OFF=1。" % (
        file_path, "\n".join(notes))
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
