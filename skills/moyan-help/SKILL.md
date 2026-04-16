---
name: moyan-help
description: >
  莫言速查卡：列出所有模式、技能、命令。一次性显示，不改变模式。
  Trigger: /moyan-help, "莫言帮助", "怎么用莫言", "moyan help", "how do I use moyan".
---

# 莫言速查

触发即显此卡。一次性 —— 不切模式，不写状态文件，不持久化。输出以莫言风格。

## 模式

| 模式 | 触发 | 效果 |
|------|------|------|
| **轻** | `/moyan 轻` | 去客套填词，保留完整句。专业但紧凑。 |
| **精** | `/moyan` | 默认。去冠词、客套、铺垫，允许片段。 |
| **极** | `/moyan 极` | 极度压缩。片段为主，表格代散文。 |
| **文言** | `/moyan 文言` | 转文言文。极省字，古雅风。 |

字形可加：`/moyan 繁`（繁體）、`/moyan 简`（简体）。不指定则随用户输入。
可组合：`/moyan 繁 极`、`/moyan 文言`（文言不分繁简，依传统作繁）。

模式持续至换级或会话结束。

## 技能

| 技能 | 触发 | 功能 |
|------|------|------|
| **moyan-commit** | `/moyan-commit` | 简洁 commit 消息。Conventional Commits。标题 ≤50 字符。 |
| **moyan-review** | `/moyan-review` | 一行式 PR 评论：`L42: bug：user 可空。加判空守卫。` |
| **moyan-help** | `/moyan-help` | 本卡。 |

## 关闭

说「停止莫言」或「恢复正常」/「normal mode」。再开：`/moyan`。

## 更多

主页：https://github.com/jaceyang97/moyan
