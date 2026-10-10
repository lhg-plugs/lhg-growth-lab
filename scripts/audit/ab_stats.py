#!/usr/bin/env python3
"""lhg-growth-lab 确定性统计脚本：A/B 实验显著性判定，Python3 零第三方依赖。

子命令：
    ztest        双比例 z 检验（转化率类指标）
    ttest        Welch t 检验（均值类指标，需汇总统计量）
    samplesize   双比例实验样本量估算（每组所需样本）
    bonferroni   多重比较 Bonferroni 校正

用法示例：
    python3 ab_stats.py ztest --x1 100 --n1 1000 --x2 130 --n2 1000
    python3 ab_stats.py samplesize --p1 0.10 --mde 0.20 --relative
    python3 ab_stats.py bonferroni --p "0.01,0.04,0.20"

数学实现均为公开统计公式（正态 CDF 用 math.erf；t 分布 CDF 用正则不完全
贝塔函数的连分式展开），代码为本项目独立实现。
"""

import argparse
import json
import math
import sys

VERSION = "1.0.0"
TOOL = "lhg-growth-lab/ab-stats"


# ---------------------------------------------------------------- 基础数学

def norm_cdf(x):
    """标准正态 CDF（math.erf 精确实现）。"""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    """标准正态分位数（二分法反解 norm_cdf，精度 1e-12）。"""
    if not 0.0 < p < 1.0:
        raise ValueError("p 必须在 (0,1) 内")
    lo, hi = -10.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _betacf(a, b, x):
    """不完全贝塔函数的连分式展开（标准数值算法）。"""
    MAXIT, EPS, FPMIN = 200, 3.0e-12, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        dele = c * d
        h *= dele
        if abs(dele - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    """正则不完全贝塔函数 I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if a <= 0.0 or b <= 0.0:
        raise ValueError("a,b 必须为正")
    if x < (a + 1.0) / (a + b + 2.0):
        bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                      + a * math.log(x) + b * math.log(1.0 - x))
        return bt * _betacf(a, b, x) / a
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t, df):
    """学生 t 分布 CDF。"""
    if df <= 0:
        raise ValueError("df 必须为正")
    x = df / (df + t * t)
    ib = betai(df / 2.0, 0.5, x)
    if t >= 0:
        return 1.0 - 0.5 * ib
    return 0.5 * ib


# ---------------------------------------------------------------- 统计量

def ztest_2prop(x1, n1, x2, n2, sided="two"):
    """双比例 z 检验（pooled SE）。返回 dict。"""
    if n1 <= 0 or n2 <= 0:
        raise ValueError("n1/n2 必须为正")
    if not (0 <= x1 <= n1 and 0 <= x2 <= n2):
        raise ValueError("x 必须在 [0,n] 内")
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        raise ValueError("方差为 0，无法检验")
    z = (p2 - p1) / se
    if sided == "two":
        p = 2.0 * (1.0 - norm_cdf(abs(z)))
    else:
        p = 1.0 - norm_cdf(z)
    # 差值的 95% 置信区间（unpooled SE）
    se_diff = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    zc = norm_ppf(0.975)
    diff = p2 - p1
    return {
        "p1": p1, "p2": p2, "diff": diff,
        "diff_pct": (diff / p1 * 100.0) if p1 > 0 else None,
        "z": z, "p_value": p, "sided": sided,
        "ci95": [diff - zc * se_diff, diff + zc * se_diff],
    }


def welch_ttest(m1, s1, n1, m2, s2, n2, sided="two"):
    """Welch t 检验（汇总统计量）。返回 dict。"""
    if n1 <= 1 or n2 <= 1:
        raise ValueError("n1/n2 必须 >1")
    if s1 < 0 or s2 < 0:
        raise ValueError("sd 不能为负")
    v1, v2 = s1 * s1 / n1, s2 * s2 / n2
    se = math.sqrt(v1 + v2)
    if se == 0:
        raise ValueError("方差为 0，无法检验")
    t = (m2 - m1) / se
    df = (v1 + v2) ** 2 / ((v1 ** 2) / (n1 - 1) + (v2 ** 2) / (n2 - 1))
    if sided == "two":
        p = 2.0 * (1.0 - t_cdf(abs(t), df))
    else:
        p = 1.0 - t_cdf(t, df)
    return {"mean1": m1, "mean2": m2, "diff": m2 - m1,
            "t": t, "df": df, "p_value": p, "sided": sided}


def sample_size_2prop(p1, mde, relative=True, alpha=0.05, power=0.8):
    """双比例实验每组所需样本量。

    p1: 基线转化率；mde: 最小可检测效应（relative=True 时为相对提升比例，
    如 0.2 表示 +20%；否则为绝对差值）；alpha: 显著性水平；power: 统计功效。
    公式：n = [z_{1-α/2}√(2·p̄(1-p̄)) + z_{1-β}√(p1(1-p1)+p2(1-p2))]² / δ²
    """
    if not 0 < p1 < 1:
        raise ValueError("p1 必须在 (0,1) 内")
    delta = p1 * mde if relative else mde
    if delta <= 0:
        raise ValueError("mde 必须为正")
    p2 = p1 + delta
    if not 0 < p2 < 1:
        raise ValueError("p1+mde 超出 (0,1)")
    p_bar = (p1 + p2) / 2.0
    z_alpha = norm_ppf(1 - alpha / 2.0)
    z_beta = norm_ppf(power)
    n = (z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
         + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (delta ** 2)
    return {"n_per_group": math.ceil(n), "n_total": math.ceil(n) * 2,
            "p1": p1, "p2": p2, "delta_abs": delta,
            "alpha": alpha, "power": power}


def bonferroni(p_values, alpha=0.05):
    """Bonferroni 校正。返回每项的校正后 p 值与是否显著。"""
    m = len(p_values)
    if m == 0:
        raise ValueError("p_values 为空")
    out = []
    for p in p_values:
        adj = min(1.0, p * m)
        out.append({"raw_p": p, "adj_p": adj, "significant": adj < alpha})
    return {"m": m, "alpha": alpha, "results": out}


# ---------------------------------------------------------------- CLI

def emit(obj, fmt):
    if fmt == "json":
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        def show(d, prefix=""):
            for k, v in d.items():
                if isinstance(v, dict):
                    show(v, prefix + k + ".")
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    print("%s%s: [%d 项]" % (prefix, k, len(v)))
                else:
                    print("%s%s=%s" % (prefix, k, v))
        show(obj)


def verdict(p, alpha):
    if p < alpha:
        return "显著（p < %.3g）：差异不太可能是运气，可以按实验结论行动；但仍要看实际提升幅度是否有业务价值。" % alpha
    return "不显著（p >= %.3g）：当前数据不足以排除运气，不要下结论；检查样本量是否达标（samplesize 子命令）。" % alpha


def main(argv=None):
    ap = argparse.ArgumentParser(description="lhg-growth-lab A/B 显著性判定")
    ap.add_argument("--format", choices=["json", "text"], default="text")
    sub = ap.add_subparsers(dest="cmd", required=True)

    z = sub.add_parser("ztest", help="双比例 z 检验")
    z.add_argument("--x1", type=int, required=True, help="对照组转化数")
    z.add_argument("--n1", type=int, required=True, help="对照组样本量")
    z.add_argument("--x2", type=int, required=True, help="实验组转化数")
    z.add_argument("--n2", type=int, required=True, help="实验组样本量")
    z.add_argument("--alpha", type=float, default=0.05)
    z.add_argument("--sided", choices=["two", "one"], default="two")

    t = sub.add_parser("ttest", help="Welch t 检验")
    t.add_argument("--mean1", type=float, required=True)
    t.add_argument("--sd1", type=float, required=True)
    t.add_argument("--n1", type=int, required=True)
    t.add_argument("--mean2", type=float, required=True)
    t.add_argument("--sd2", type=float, required=True)
    t.add_argument("--n2", type=int, required=True)
    t.add_argument("--alpha", type=float, default=0.05)
    t.add_argument("--sided", choices=["two", "one"], default="two")

    s = sub.add_parser("samplesize", help="样本量估算")
    s.add_argument("--p1", type=float, required=True, help="基线转化率，如 0.10")
    s.add_argument("--mde", type=float, required=True, help="最小可检测效应")
    s.add_argument("--relative", action="store_true", help="mde 为相对提升（默认绝对差值）")
    s.add_argument("--absolute", dest="relative", action="store_false")
    s.add_argument("--alpha", type=float, default=0.05)
    s.add_argument("--power", type=float, default=0.8)
    s.set_defaults(relative=True)

    b = sub.add_parser("bonferroni", help="多重比较校正")
    b.add_argument("--p", required=True, help="逗号分隔的 p 值，如 \"0.01,0.04,0.2\"")
    b.add_argument("--alpha", type=float, default=0.05)

    # --format 放在子命令后也可用（dest 区分，避免覆盖全局值）
    for sp in (z, t, s, b):
        sp.add_argument("--format", dest="sub_format",
                        choices=["json", "text"], default=None)

    args = ap.parse_args(argv)
    fmt = args.sub_format or args.format  # 子命令级优先，否则用全局（默认 text）
    try:
        if args.cmd == "ztest":
            r = ztest_2prop(args.x1, args.n1, args.x2, args.n2, args.sided)
            r["verdict"] = verdict(r["p_value"], args.alpha)
            r["alpha"] = args.alpha
        elif args.cmd == "ttest":
            r = welch_ttest(args.mean1, args.sd1, args.n1,
                            args.mean2, args.sd2, args.n2, args.sided)
            r["verdict"] = verdict(r["p_value"], args.alpha)
            r["alpha"] = args.alpha
        elif args.cmd == "samplesize":
            r = sample_size_2prop(args.p1, args.mde, args.relative,
                                  args.alpha, args.power)
            r["note"] = "每组至少 %d 样本；按日流量折算实验天数，跑满前不要看显著性。" % r["n_per_group"]
        elif args.cmd == "bonferroni":
            ps = [float(x) for x in args.p.split(",") if x.strip() != ""]
            r = bonferroni(ps, args.alpha)
            r["note"] = "同时看 m 个指标/做 m 组比较时用；校正后仍显著的才算数。"
        r["tool"] = TOOL
        r["version"] = VERSION
        emit(r, fmt)
        return 0
    except ValueError as e:
        print("参数错误：%s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
