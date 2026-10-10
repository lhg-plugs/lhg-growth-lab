#!/usr/bin/env python3
"""lhg-growth-lab 确定性实验设计审计：10 条规则，零第三方依赖。

扫描目标目录/文件的 markdown 实验方案，检查假设/对照组/样本量/随机化缺项，
以及 p-hacking 反模式（提前停止、多重比较未校正、周期过短）；
有 blocker 时以 exit code 2 退出（供 hooks 与 CI 使用）。

用法：
    python3 gl_audit.py --target <目录或文件> [--format json|text] [--fail-on blocker|warning]

规则文案均为本项目原创（方法论灵感见 ATTRIBUTION.md，未复制任何第三方原文）。
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"
TOOL = "lhg-growth-lab/design-audit"

SKIP_DIRS = {
    "node_modules", ".next", "dist", "build", ".git", "coverage",
    "__pycache__", "vendor", ".turbo", "out", "fixtures",
}


class Finding:
    __slots__ = ("rule_id", "severity", "category", "title", "file", "line", "snippet", "detail")

    def __init__(self, rule_id, severity, category, title, file, line, snippet, detail):
        self.rule_id = rule_id
        self.severity = severity
        self.category = category
        self.title = title
        self.file = file
        self.line = line
        self.snippet = snippet
        self.detail = detail

    def to_dict(self):
        return {
            "rule_id": self.rule_id, "severity": self.severity,
            "category": self.category, "title": self.title,
            "file": self.file, "line": self.line,
            "snippet": self.snippet, "detail": self.detail,
        }


def collect_files(target):
    if os.path.isfile(target):
        return [target] if target.endswith(".md") else []
    out = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".md"):
                out.append(os.path.join(root, f))
    return sorted(out)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def has_kw(text, *kws):
    return any(k in text for k in kws)


def find_line(lines, pattern, flags=0):
    rx = re.compile(pattern, flags)
    for i, ln in enumerate(lines):
        if rx.search(ln):
            return i + 1, ln.strip()[:160]
    return 1, ""


# ---------------------------------------------------------------- 规则定义

RULES = []
_RULE_BY_ID = {}


def rule(rule_id, severity, category, title, detail):
    def deco(fn):
        r = {"id": rule_id, "severity": severity, "category": category,
             "title": title, "detail": detail}
        _RULE_BY_ID[rule_id] = r
        r["check"] = fn
        RULES.append(r)
        return fn
    return deco


def _mk(rule_id, path, line, snippet):
    r = _RULE_BY_ID[rule_id]
    return Finding(r["id"], r["severity"], r["category"], r["title"],
                   path, line, snippet[:160], r["detail"])


# ---------------- 设计完整性 ----------------

@rule("GL-DSG-001", "blocker", "设计完整性", "实验方案缺少假设",
      "无假设的实验无法证伪。按\"如果…那么…因为…\"写出可证伪假设。")
def r_dsg_001(lines, text, path, ctx):
    if not has_kw(text, "假设"):
        ln, sn = find_line(lines, r"实验|方案")
        return [_mk("GL-DSG-001", path, ln, sn or os.path.basename(path))]
    return []


@rule("GL-DSG-002", "blocker", "设计完整性", "实验方案缺少核心指标",
      "无核心指标（OEC），跑完不知道看什么。定 1 个核心指标 + 口径定义。")
def r_dsg_002(lines, text, path, ctx):
    if not has_kw(text, "指标", "OEC"):
        ln, sn = find_line(lines, r"实验|方案")
        return [_mk("GL-DSG-002", path, ln, sn or os.path.basename(path))]
    return []


@rule("GL-DSG-003", "blocker", "设计完整性", "无对照组设计",
      "没写对照组/控制组，等于没有比较基准。明确对照组是什么、流量比例。")
def r_dsg_003(lines, text, path, ctx):
    if not has_kw(text, "对照组", "控制组", "对照"):
        ln, sn = find_line(lines, r"分组|实验组|方案")
        return [_mk("GL-DSG-003", path, ln, sn or os.path.basename(path))]
    return []


@rule("GL-DSG-004", "warning", "设计完整性", "样本量未估算",
      "没估算样本量就开跑，大概率白跑。用 ab_stats.py samplesize 先算每组所需样本。")
def r_dsg_004(lines, text, path, ctx):
    if not has_kw(text, "样本量", "sample"):
        ln, sn = find_line(lines, r"实验|方案|设计")
        return [_mk("GL-DSG-004", path, ln, sn or os.path.basename(path))]
    return []


@rule("GL-DSG-005", "warning", "设计完整性", "随机化方式未说明",
      "没写随机化/分流方式，分组可能不随机。用用户 ID 哈希分桶并保证分流一致性。")
def r_dsg_005(lines, text, path, ctx):
    if not has_kw(text, "随机", "分流", "分桶", "哈希"):
        ln, sn = find_line(lines, r"分组|实验组|设计")
        return [_mk("GL-DSG-005", path, ln, sn or os.path.basename(path))]
    return []


# ---------------- p-hacking 反模式 ----------------

PEEK_PATTERNS = [
    r"提前停止", r"提前结束", r"边看边停",
    r"每天.{0,8}看.{0,8}显著", r"显著.{0,6}就停", r"显著.{0,6}就全量",
]
NEG_WORDS = ("不", "不要", "禁止", "杜绝", "不许", "避免", "严禁")


def _has_peeking(text):
    for pat in PEEK_PATTERNS:
        for m in re.finditer(pat, text):
            before = text[max(0, m.start() - 6):m.start()]
            if any(w in before for w in NEG_WORDS):
                continue  # 否定句（如"不提前停止"）不算
            return m.group(0)
    return None


@rule("GL-PHK-001", "blocker", "p-hacking", "提前停止（peeking）风险",
      "边看数据边决定停止，会把假阳性率抬到远超 5%。先定样本量与周期，跑满再看；忍不住就用序贯检验。")
def r_phk_001(lines, text, path, ctx):
    hit = _has_peeking(text)
    if hit:
        ln, sn = find_line(lines, re.escape(hit[:4]))
        return [_mk("GL-PHK-001", path, ln, sn or hit)]
    return []


@rule("GL-PHK-002", "warning", "p-hacking", "多重比较未校正",
      "同时看 ≥3 个指标做显著性判定却未提校正，假阳性会膨胀。用 Bonferroni 校正（ab_stats.py bonferroni）或只定 1 个核心指标。")
def r_phk_002(lines, text, path, ctx):
    metrics = re.findall(r"[转化点击留存付费注册激活复购下单回访分享停留跳出加购]{2,}率?", text)
    uniq = {m for m in metrics if len(m) >= 2}
    if len(uniq) >= 3 and not has_kw(text, "校正", "Bonferroni", "bonferroni", "多重比较", "FDR"):
        ln, sn = find_line(lines, r"指标")
        return [_mk("GL-PHK-002", path, ln, "同时判定 %d 个指标：%s" % (len(uniq), "、".join(sorted(uniq)[:5])))]
    return []


@rule("GL-PHK-003", "warning", "p-hacking", "显著性结论无样本量支撑",
      "文档谈\"显著\"却没估算样本量。先算样本量（ab_stats.py samplesize），跑满再谈显著。")
def r_phk_003(lines, text, path, ctx):
    if has_kw(text, "显著") and not has_kw(text, "样本量", "sample"):
        ln, sn = find_line(lines, r"显著")
        return [_mk("GL-PHK-003", path, ln, sn)]
    return []


# ---------------- 周期与效应 ----------------

@rule("GL-DUR-001", "warning", "周期", "实验周期可能过短",
      "文档中最长的\"N 天\"小于 7 天。周期太短会被星期效应/新奇效应污染，建议 ≥7 天并覆盖完整周。")
def r_dur_001(lines, text, path, ctx):
    days = [int(m.group(1)) for m in re.finditer(r"(\d+)\s*天", text)]
    if days and max(days) < 7:
        ln, sn = find_line(lines, r"\d+\s*天")
        return [_mk("GL-DUR-001", path, ln, sn)]
    return []


@rule("GL-NOV-001", "warning", "周期", "新奇效应未考虑",
      "未提新奇效应/预热期。用户对新变化的第一反应不代表长期效果，建议设 2~3 天预热期再纳入判定。")
def r_nov_001(lines, text, path, ctx):
    if not has_kw(text, "新奇", "新颖", "预热", "burn"):
        ln, sn = find_line(lines, r"周期|天|设计")
        return [_mk("GL-NOV-001", path, ln, sn or os.path.basename(path))]
    return []


# ---------------------------------------------------------------- 运行器

def run(target):
    files = collect_files(target)
    findings = []
    base = os.path.abspath(target) if os.path.isdir(target) else os.path.dirname(os.path.abspath(target))
    for path in files:
        text = read_text(path)
        lines = text.split("\n")
        rel = os.path.relpath(path, base)
        for r in RULES:
            try:
                for f in r["check"](lines, text, path, {}) or []:
                    f.file = rel
                    findings.append(f)
            except Exception:
                continue  # 单条规则异常不影响整体
    return files, findings


def main(argv=None):
    ap = argparse.ArgumentParser(description="lhg-growth-lab 确定性实验设计审计")
    ap.add_argument("--target", default=".", help="扫描目录或文件")
    ap.add_argument("--format", choices=["json", "text"], default="text")
    ap.add_argument("--fail-on", choices=["blocker", "warning"], default="blocker")
    args = ap.parse_args(argv)

    target = os.path.abspath(args.target)
    if not (os.path.isdir(target) or os.path.isfile(target)):
        print("target 不存在：%s" % args.target, file=sys.stderr)
        return 1

    files, findings = run(target)
    sev_rank = {"blocker": 2, "warning": 1}
    counts = {"blocker": 0, "warning": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    result = {
        "tool": TOOL,
        "version": VERSION,
        "target": args.target,
        "summary": {
            "files_scanned": len(files),
            "rules_run": len(RULES),
            "blocker": counts["blocker"],
            "warning": counts["warning"],
        },
        "findings": [f.to_dict() for f in sorted(
            findings, key=lambda x: (-sev_rank.get(x.severity, 0), x.file, x.line))],
    }

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        s = result["summary"]
        print("实验设计审计：扫描 %d 文件，运行 %d 条规则" % (s["files_scanned"], s["rules_run"]))
        print("blocker=%d warning=%d" % (s["blocker"], s["warning"]))
        for f in result["findings"]:
            print("[%s][%s] %s:%d %s" % (
                f["severity"].upper(), f["rule_id"], f["file"], f["line"], f["title"]))
            print("    %s" % f["detail"])
            if f["snippet"]:
                print("    → %s" % f["snippet"])

    level = sev_rank[args.fail_on]
    bad = any(sev_rank.get(f.severity, 0) >= level for f in findings)
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
