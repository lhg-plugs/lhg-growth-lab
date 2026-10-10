#!/usr/bin/env python3
"""lhg-growth-lab 插件冒烟测试：全部绿才算过。

检查项：
 1. 三个 JSON 合法（plugin.json / marketplace.json / hooks.json）
 2. 4 个 SKILL.md 都有 name/description frontmatter，且 150~320 行
 3. 4 个 commands 都有 description frontmatter
 4. 2 个 agents 都有 name/description/tools/model frontmatter
 5. skills 平台中立：不含 Claude Code 专有工具名
 6. gl_audit fixtures：坏 fixture 埋点全命中且 exit!=0；好 fixture 零 blocker 且 exit==0
 7. ab_stats 数学正确性：手工验算值（z=2.1027/p=0.0355）、样本量缩放律、
    Bonferroni、t 检验与 z 检验大样本一致性
 8. hooks 脚本：commit 拦截 / 非 commit 放行 / 逃生开关 / 显著性断言提醒

用法：python3 smoke_test.py [--repo <插件根目录>]
退出码：0=全绿，1=有失败。
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append((PASS if cond else FAIL, name, detail))
    return cond


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def frontmatter(path):
    """解析 markdown 顶部 --- YAML 块（只取一层 key: value）。"""
    text = read(path)
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for ln in text[3:end].split("\n"):
        m = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)


# 预期的埋点命中（坏 fixture 必须全部命中）
BAD_MUST = {"GL-DSG-001", "GL-DSG-003", "GL-PHK-001", "GL-PHK-002"}
# 平台中立红线：skill 正文不许出现这些 Claude Code 专有表述
NEUTRAL_DENY = ["Task tool", "Bash tool", "Edit tool", "Write tool", "Read tool",
                "AskUserQuestion", "subagent_type", "PreToolUse", "PostToolUse",
                "${CLAUDE_", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    AUDIT = os.path.join(repo, "scripts", "audit")
    STATS = os.path.join(AUDIT, "ab_stats.py")

    # 1. JSON 合法
    for rel in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                "hooks/hooks.json"]:
        p = os.path.join(repo, rel)
        try:
            d = json.loads(read(p))
            check("JSON 合法: " + rel, True)
            if rel.endswith("plugin.json"):
                check("plugin.json name==lhg-growth-lab", d.get("name") == "lhg-growth-lab", str(d.get("name")))
                check("plugin.json 有 version/description/author",
                      all(d.get(k) for k in ("version", "description", "author")))
            if rel.endswith("marketplace.json"):
                ps = d.get("plugins", [])
                check("marketplace.json source==./ 且 name 一致",
                      len(ps) == 1 and ps[0].get("source") == "./" and
                      ps[0].get("name") == "lhg-growth-lab", str(ps))
            if rel.endswith("hooks.json"):
                check("hooks.json 顶层有 hooks 包装", "hooks" in d)
                evts = d["hooks"]
                check("hooks.json 有 PreToolUse+PostToolUse",
                      "PreToolUse" in evts and "PostToolUse" in evts, str(list(evts)))
        except Exception as e:
            check("JSON 合法: " + rel, False, str(e))

    # 2. SKILL.md
    for skill in ["lhg-gl-hypothesis", "lhg-gl-design", "lhg-gl-stats", "lhg-gl-antiphack"]:
        p = os.path.join(repo, "skills", skill, "SKILL.md")
        fm = frontmatter(p)
        check("skill frontmatter: " + skill,
              bool(fm.get("name")) and bool(fm.get("description")),
              "name=%s" % fm.get("name"))
        nlines = len(read(p).split("\n"))
        check("skill 行数 150~320: %s (%d 行)" % (skill, nlines), 150 <= nlines <= 320, str(nlines))
        body = read(p)
        bad_words = [w for w in NEUTRAL_DENY if w in body]
        check("skill 平台中立: " + skill, not bad_words, "命中: %s" % bad_words)
        check("skill 有出品区: " + skill, "出品：刘洪光" in body and "https://github.com/lhg-skills" in body)
        check("skill 有自检与反馈: " + skill, "自检与反馈" in body)

    # 3. commands
    for cmd in ["growth-lab", "sample-size", "ab-significance", "audit"]:
        p = os.path.join(repo, "commands", cmd + ".md")
        fm = frontmatter(p)
        check("command description: " + cmd, bool(fm.get("description")), str(fm.get("description"))[:60])

    # 4. agents
    for ag in ["experiment-designer", "stats-reviewer"]:
        p = os.path.join(repo, "agents", ag + ".md")
        fm = frontmatter(p)
        check("agent frontmatter: " + ag,
              all(fm.get(k) for k in ("name", "description", "tools", "model")),
              str({k: fm.get(k) for k in ("name", "model")}))

    # 5. gl_audit fixtures
    def audit_hits(target):
        r = run([sys.executable, os.path.join(AUDIT, "gl_audit.py"),
                 "--target", os.path.join(repo, target), "--format", "json"])
        try:
            d = json.loads(r.stdout)
        except Exception:
            return None, r.returncode, []
        return d["summary"], r.returncode, [f["rule_id"] for f in d["findings"]]

    s, code, ids = audit_hits("fixtures/design-bad")
    check("设计坏 fixture exit!=0", code != 0, "exit=%d" % code)
    check("设计坏 fixture blocker>0", s and s["blocker"] > 0, str(s))
    missing = BAD_MUST - set(ids)
    check("设计坏 fixture 埋点全命中 (%d/%d)" % (len(BAD_MUST - missing), len(BAD_MUST)),
          not missing, "缺失: %s" % sorted(missing))

    s, code, ids = audit_hits("fixtures/design-good")
    check("设计好 fixture 零 blocker", s and s["blocker"] == 0, str(s))
    check("设计好 fixture exit==0", code == 0, "exit=%d" % code)

    n_rules = json.loads(run([sys.executable, os.path.join(AUDIT, "gl_audit.py"),
                              "--target", os.path.join(repo, "fixtures/design-good"),
                              "--format", "json"]).stdout)["summary"]["rules_run"]
    check("设计规则数>=8 (%d)" % n_rules, n_rules >= 8, str(n_rules))

    # 6. ab_stats 数学正确性
    def stats(*a):
        r = run([sys.executable, STATS, "--format", "json"] + list(a))
        return json.loads(r.stdout), r.returncode

    # 6a. 双比例 z 检验：手工验算值（对照 100/1000 vs 实验 130/1000）
    # pooled p=0.115, SE=0.0142667, z=2.1027, 双侧 p=0.0355
    d, code = stats("ztest", "--x1", "100", "--n1", "1000", "--x2", "130", "--n2", "1000")
    check("ztest exit==0", code == 0)
    check("ztest z≈2.1027", abs(d["z"] - 2.1027) < 0.01, "z=%s" % d.get("z"))
    check("ztest p≈0.0355", abs(d["p_value"] - 0.0355) < 0.005, "p=%s" % d.get("p_value"))
    check("ztest 置信区间包含差值", d["ci95"][0] < d["diff"] < d["ci95"][1], str(d.get("ci95")))

    # 6b. 样本量缩放律：MDE 减半 → 样本量约 4 倍
    d1, _ = stats("samplesize", "--p1", "0.10", "--mde", "0.2")
    d2, _ = stats("samplesize", "--p1", "0.10", "--mde", "0.1")
    ratio = d2["n_per_group"] / d1["n_per_group"]
    check("样本量缩放律 ~4x (%.2f)" % ratio, 3.4 < ratio < 4.4, "n1=%d n2=%d" % (d1["n_per_group"], d2["n_per_group"]))

    # 6c. Bonferroni 校正
    d, _ = stats("bonferroni", "--p", "0.01,0.04,0.20")
    adj = [r["adj_p"] for r in d["results"]]
    sig = [r["significant"] for r in d["results"]]
    check("bonferroni 校正值", all(abs(a - e) < 1e-9 for a, e in zip(adj, [0.03, 0.12, 0.6])), str(adj))
    check("bonferroni 显著性", sig == [True, False, False], str(sig))

    # 6d. t 检验大样本下与 z 检验一致
    dz, _ = stats("ztest", "--x1", "10000", "--n1", "100000", "--x2", "10300", "--n2", "100000")
    dt, _ = stats("ttest", "--mean1", "0.1", "--sd1", str(math.sqrt(0.09)),
                  "--n1", "100000", "--mean2", "0.103",
                  "--sd2", str(math.sqrt(0.103 * 0.897)), "--n2", "100000")
    check("t 检验大样本≈z 检验", abs(dt["p_value"] - dz["p_value"]) < 0.02,
          "t_p=%.4f z_p=%.4f" % (dt["p_value"], dz["p_value"]))

    # 6e. 参数错误处理
    r = run([sys.executable, STATS, "ztest", "--x1", "5", "--n1", "0",
             "--x2", "1", "--n2", "10"])
    check("ztest 非法参数 exit!=0", r.returncode != 0, "exit=%d" % r.returncode)

    # 7. hooks 脚本
    def hook(script, payload, env=None):
        e = dict(os.environ); e.update(env or {})
        return run([sys.executable, os.path.join(repo, "hooks", script)],
                   input=payload, env=e)

    r = hook("pre_commit_gl_audit.py", '{"tool_input":{"command":"git status"}}')
    check("hook: 非 commit 放行", r.returncode == 0 and not r.stdout.strip())
    r = hook("pre_commit_gl_audit.py",
             '{"tool_input":{"command":"git commit -m \\"x\\""}}',
             {"CLAUDE_PROJECT_DIR": os.path.join(repo, "fixtures/design-bad")})
    try:
        d = json.loads(r.stdout)
        denied = d["hookSpecificOutput"]["permissionDecision"] == "deny"
    except Exception:
        denied = False
    check("hook: commit 有 blocker 拦截", denied, r.stdout[:120])
    r = hook("pre_commit_gl_audit.py",
             '{"tool_input":{"command":"git commit -m \\"x\\""}}',
             {"CLAUDE_PROJECT_DIR": os.path.join(repo, "fixtures/design-bad"),
              "LHG_GL_HOOKS_OFF": "1"})
    check("hook: 逃生开关生效", r.returncode == 0 and not r.stdout.strip())

    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "实验报告.md")
        open(fp, "w", encoding="utf-8").write("# 实验报告\n\n结果显著，转化率提升了。\n")
        r = hook("post_write_claim_check.py", json.dumps({"tool_input": {"file_path": fp}}))
        check("hook: 显著无样本量警告", "additionalContext" in r.stdout, r.stdout[:80])
        fp2 = os.path.join(td, "notes.md")
        open(fp2, "w", encoding="utf-8").write("# 随手记\n\n今天天气不错。\n")
        r = hook("post_write_claim_check.py", json.dumps({"tool_input": {"file_path": fp2}}))
        check("hook: 非实验文档不警告", not r.stdout.strip())

    # 报告
    print("=" * 60)
    print("lhg-growth-lab 冒烟测试报告")
    print("=" * 60)
    fails = 0
    for st, name, detail in results:
        mark = "✓" if st == PASS else "✗"
        print("%s %s %s" % (mark, st, name))
        if detail and st == FAIL:
            print("    → %s" % detail)
        if st == FAIL:
            fails += 1
    print("=" * 60)
    print("共 %d 项，通过 %d，失败 %d" % (len(results), len(results) - fails, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
