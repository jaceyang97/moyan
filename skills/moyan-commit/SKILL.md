---
name: moyan-commit
description: >
  莫言 commit：中文简洁 commit 消息生成器。Conventional Commits 格式，标题 ≤50 字符，正文只在
  "为何" 不明显时出现。Use when user says "写 commit" / "生成 commit" / "commit 消息" / "写提交" /
  "/commit" or invokes /moyan-commit. Auto-triggers when staging changes.
---

commit message 须简而准。Conventional Commits 格式。说 why，不说 what（diff 已说 what）。

## 规则

**标题行：**
- 格式：`<type>(<scope>): <祈使短句>` — `<scope>` 可省
- type：`feat` / `fix` / `refactor` / `perf` / `docs` / `test` / `chore` / `build` / `ci` / `style` / `revert`
- 祈使语气：「加」「修」「删」—— 不用「添加了」「正在修」
- 标题尽量 ≤50 字符，硬限 72
- 末尾不加句号
- 冒号后首字大小写随项目习惯

**正文（可选）：**
- 标题自明则不写
- 只在以下情况写：非显然的 why、破坏性变更、迁移说明、issue 引用
- 72 字符换行
- 列表用 `-` 不用 `*`
- 末尾引用 issue：`Closes #42`、`Refs #17`
- 中英文混排无妨，技术词保英文

**绝对不写：**
- 「本次提交」「此次修改」「我」「我们」「现在」—— 废话
- 「按 XX 要求」—— 用 `Co-authored-by` trailer
- 任何 AI 署名（「Generated with Claude Code」等）
- emoji（除非项目约定）
- scope 已指明时再写文件名

## 示例

新增接口（含 body 说明 why）：
- ❌ `feat: 增加了一个新的获取用户资料的接口`
- ✅
  ```
  feat(api): add GET /users/:id/profile

  移动端冷启动时只需资料子集，避免 LTE 下全量 user payload
  的带宽开销。

  Closes #128
  ```

破坏性变更：
- ✅
  ```
  feat(api)!: rename /v1/orders to /v1/checkout

  BREAKING CHANGE: /v1/orders 须在 2026-06-01 前迁至
  /v1/checkout。该日期后旧路径返回 410。
  ```

## 破例

以下情况必加正文，不可只写标题：破坏性变更、安全修复、数据迁移、revert 前提交。将来排错者需要上下文。

## 边界

仅生成 commit 消息。不执行 `git commit`，不 stage，不 amend。输出 code block 可直接粘贴。
「停止 moyan-commit」/「normal mode」：还原至啰嗦模式。
