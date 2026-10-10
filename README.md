<!-- About 简介（推送后填写到仓库 About 栏）：
小白也能做严谨 A/B 实验：从假设到显著性判定 ｜ 一键安装：/plugin marketplace add lhg-plugs/lhg-growth-lab
-->
<!-- topics（推送后打）：claude-code, claude-plugin, agent-skills, ab-testing, statistics -->

# lhg-growth-lab：小白也能做严谨的 A/B 实验

> **一句话介绍**：给 AI 助手装上"增长实验专家"——假设→实验设计（分组/随机化/样本量估算）→一键显著性判定（Python 零依赖脚本：双比例 z 检验/t 检验/Bonferroni）→p-hacking 反模式拦截→复盘报告。
>
> **一键安装**：在 Claude Code 里运行
> ```
> /plugin marketplace add lhg-plugs/lhg-growth-lab
> /plugin install lhg-growth-lab@lhg-plugs
> ```

## 它是什么

`lhg-growth-lab` 是一个 Claude Code 插件（plugin 为主、skill 为辅），面向**想做严谨实验但不懂统计的小白**：

- **4 个命令**（小白入口）：`growth-lab` A/B 实验全流程，`sample-size` 样本量估算，`ab-significance` 一键显著性判定，`audit` 实验设计体检
- **4 个平台中立 skill**（方法论，可移植到豆包/Workbuddy 等 agent 平台）：实验假设与 OEC、实验设计、统计判定、p-hacking 反模式
- **2 个专家 agent**：实验设计师、统计评审
- **2 个硬门 hooks**：commit 前实验设计审计拦截、"显著"断言无样本量提醒（均可一键豁免）
- **确定性脚本**：`ab_stats.py`（显著性计算，数学实现经手工验算与数值积分双重校验）+ `gl_audit.py`（10 条实验设计审计规则），纯 Python、零第三方依赖

与兄弟插件 `lhg-user-growth` 的分工：轻量增长实验清单（AARRR 诊断→实验卡→复盘）走那边；需要严格分组、样本量、显著性判定的走这边。两个插件互链，不重复造轮子。

## 4 个命令用法

| 命令 | 作用 | 示例 |
|---|---|---|
| `/lhg-growth-lab:growth-lab` | A/B 实验全流程：假设→设计→判定→防 p-hacking→复盘 | `/lhg-growth-lab:growth-lab "红色按钮转化更高"` |
| `/lhg-growth-lab:sample-size` | 样本量估算：基线转化率 + 最小可检测效应 → 每组样本与天数 | `/lhg-growth-lab:sample-size --p1 0.10 --mde 0.2` |
| `/lhg-growth-lab:ab-significance` | 显著性判定：输入两组数据，一键跑检验并解读 | `/lhg-growth-lab:ab-significance --x1 100 --n1 1000 --x2 130 --n2 1000` |
| `/lhg-growth-lab:audit` | 实验设计体检：假设/对照组/样本量缺项 + p-hacking 反模式 | `/lhg-growth-lab:audit docs/` |

## 统计脚本说明

`scripts/audit/ab_stats.py` 四个子命令（全部零第三方依赖）：

| 子命令 | 作用 | 示例 |
|---|---|---|
| `ztest` | 双比例 z 检验（转化率类指标） | `ab_stats.py ztest --x1 100 --n1 1000 --x2 130 --n2 1000` |
| `ttest` | Welch t 检验（均值类，需汇总统计量） | `ab_stats.py ttest --mean1 50 --sd1 10 --n1 500 --mean2 53 --sd2 11 --n2 500` |
| `samplesize` | 双比例实验每组样本量估算 | `ab_stats.py samplesize --p1 0.10 --mde 0.2` |
| `bonferroni` | 多重比较校正 | `ab_stats.py bonferroni --p "0.01,0.04,0.20"` |

数学正确性经三重校验：手工验算值（z=2.1027/p=0.0355）、t 分布 CDF 与 Simpson 数值积分对照（误差 <1e-6）、样本量缩放律（MDE 减半→样本量约 4 倍）。详见 `smoke_test.py`。

## 自查说明

自查 = 确定性脚本（机器）+ 人工评审清单（人）：

1. 先跑 `scripts/audit/gl_audit.py`（10 条规则），零 LLM 成本；
2. 发现分两级：**blocker**（缺假设/无对照组/提前停止风险，必须修，commit 前 hook 会拦截）、**warning**（样本量未估算/随机化未说明/多重比较未校正/周期过短/新奇效应未考虑，补上或写豁免理由）；
3. 判定显著性前先过资格检查（样本/周期/分流/口径），再跑 `ab_stats.py`——跳过资格检查直接算 p 值是第一大忌。

blocker 清零才算做完；为清零改规则算作弊，不许。

## 目录结构

```
lhg-growth-lab/
├── .claude-plugin/          # plugin.json（插件清单）+ marketplace.json（本仓即市场）
├── commands/                # 4 个命令：growth-lab / sample-size / ab-significance / audit
├── skills/                  # 4 个平台中立 skill（hypothesis/design/stats/antiphack）
├── agents/                  # 2 个专家 agent（experiment-designer / stats-reviewer）
├── hooks/                   # 2 个硬门（commit 前审计拦截 / 显著性断言提醒）+ 豁免说明
├── scripts/audit/           # ab_stats.py（显著性计算）+ gl_audit.py（10 条设计审计规则）
├── fixtures/                # 冒烟测试用例（坏/好对照）
├── smoke_test.py            # 一键冒烟测试（含统计数学正确性校验）
├── ATTRIBUTION.md           # 灵感来源与许可声明
└── LICENSE                  # MIT
```

## 什么时候用 / 什么时候不用（FAQ）

**什么时候用：**

- 有实验想法，想严谨验证而不是凭感觉 → 用 `/lhg-growth-lab:growth-lab` 走全流程
- 不知道实验要跑多久、多少样本 → 用 `/lhg-growth-lab:sample-size` 先算
- 实验跑完，两组数据摆在面前不知道怎么判 → 用 `/lhg-growth-lab:ab-significance` 一键判定
- 怀疑自己/同事在 p-hacking（提前看数据、换指标）→ 用 `lhg-gl-antiphack` 的六大反模式自查

**什么时候不用：**

- 流量太小（算出来要跑 3 个月）→ 诚实降级为前后对比 + 访谈，不要硬做 A/B
- 只是想要一堆增长点子、快速试错 → 用兄弟插件 `lhg-user-growth`，更轻更快
- 需要贝叶斯方法、序贯检验等进阶统计 → 本插件只覆盖频率学派固定样本量设计，进阶需求请找统计师

## lhg-plugs 插件矩阵

| 插件 | 一句话 | 安装 |
|---|---|---|
| [lhg-growth-lab](https://github.com/lhg-plugs/lhg-growth-lab) | 增长实验专家：假设→实验设计→显著性判定→防 p-hacking | `/plugin install lhg-growth-lab@lhg-plugs` |
| [lhg-user-growth](https://github.com/lhg-plugs/lhg-user-growth) | 小白可执行的增长实验清单：从杠杆诊断到复盘 | `/plugin install lhg-user-growth@lhg-plugs` |
| [lhg-fullstack](https://github.com/lhg-plugs/lhg-fullstack) | 小白一句话 → 高质量全栈应用 | `/plugin install lhg-fullstack@lhg-plugs` |

## 自检与反馈

本插件自带质检：每次使用后可跑 `python3 smoke_test.py` 一键验证（JSON 合法、skill/command/agent 完整性、统计数学正确性、fixtures 命中、hooks 行为）。

发现 bug 或有改进建议，以 `[QC] <一句话问题>` 为标题提交到 https://github.com/lhg-plugs/lhg-growth-lab/issues，正文写清"复现步骤 → 实际表现 → 期望表现"。统计计算疑问请附你的数据与脚本输出。

## 出品：刘洪光

本插件由真人出镜 IP「刘洪光」（安徽合肥）出品，归属 [lhg-skills](https://github.com/lhg-skills)。

- GitHub 主页：https://github.com/lhg-skills —— 全部 skill 开源在此，欢迎 star
- 视频号：搜「刘洪光实名上网」
- 微信：lhgsmsw
