# 灵感来源与致谢（Attribution）

本插件的**方法论灵感**来自以下公开来源，**所有实现代码、检测规则与文案均为原创**，未复制任何第三方的原文案与代码。

| 来源 | 作者 / 出处 | 许可 | 链接 | 借鉴了什么思路 |
|---|---|---|---|---|
| marketingskills | Corey Haines | MIT | https://github.com/coreyhaines31/marketingskills | 把营销方法论做成 agent skill 包的"技能包"模式；本插件的实验流程、审计规则、中文文案均为独立设计 |
| Evan Miller A/B 工具集 | Evan Miller | 未找到（个人网站免费工具） | http://www.evanmiller.org/ab-testing/ | 样本量估算公式的思路与"不要提前看数据"（peeking）警示；统计脚本为独立实现，数学公式为公开统计知识 |
| How Not To Run an A/B Test | Evan Miller | 未找到（个人博客文章） | http://www.evanmiller.org/how-not-to-run-an-ab-test.html | peeking 反模式的问题意识；本插件六大反模式清单为独立撰写 |
| AARRR 海盗指标 | Dave McClure（500 Startups，2007） | 公开方法论概念 | — | 实验分层思路的背景概念；与兄弟插件 `lhg-user-growth` 的分工界面参考了该框架 |

## 声明

1. **借鉴思路，实现与文案均为原创**：以上来源的具体文案、代码实现均未被复制。本插件的 skill 方法论文案、审计规则、统计脚本（z 检验/t 检验/样本量/Bonferroni 均为独立实现的公开统计公式）均为独立撰写。
2. **许可合规**：marketingskills 为 MIT 许可，允许在保留声明的前提下进行思路借鉴与二次创作。本文件即为保留声明的一部分。统计公式为公开数学知识，不涉及许可问题。
3. **数据诚实**：本插件文档中如引用第三方数据（如 star 数），均标注来源与日期；查不到的不写。
4. **商标与归属**：各项目名称与作者署名归其各自所有者所有。

## 本插件自身的许可

本插件原创部分采用 MIT 许可（见 `LICENSE` 文件），版权所有：刘洪光（https://github.com/lhg-skills）。

## 兄弟插件

- [lhg-user-growth](https://github.com/lhg-plugs/lhg-user-growth)：用户增长专家（AARRR 杠杆诊断、可执行实验清单、复盘），与本插件互链互补。
