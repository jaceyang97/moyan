# 莫言 · moyan

> 少言多意。中文省 token 模式 · Claude Code plugin。

受 [caveman](https://github.com/JuliusBrussee/caveman) 启发。Caveman 以"山顶洞人"的英语省 token，**莫言** 以简洁中文省 token —— 回复少而准，字字算数。

- **白话三级**：轻 / 精（默认）/ 极
- **文言模式**：古雅极省
- **简繁通吃**：自动跟随用户输入，或手动切换
- **Claude Code only**（目前）

## 何以「莫言」

莫言，字面即「少说」。语出《礼记·曲礼》"临财毋苟得，临难毋苟免"的克制传统，也是中国首位诺贝尔文学奖得主之名。此处借意：**字字算数，不费口舌**。

## 安装

### 方式一：marketplace（推荐）

```bash
/plugin marketplace add jaceyang97/moyan
/plugin install moyan@moyan
```

### 方式二：本地 clone

```bash
git clone https://github.com/jaceyang97/moyan ~/.claude/plugins/moyan
```

然后在 Claude Code 中 `/plugin` 启用。

## 快速开始

只需一个命令：

```
/moyan            # 启动默认（精简模式，简繁随输入）
/moyan 轻         # 轻度压缩，保留完整句
/moyan 极         # 极度压缩，片段为主
/moyan 文言       # 文言文回复
/moyan 繁         # 强制繁體
/moyan 简         # 强制简体
/moyan 繁 极      # 繁體 + 极度压缩

停止莫言           # 恢复正常模式
```

启动后写 commit、做 code review、答技术问题 —— 一律按莫言风格输出。无需切换。

## 风格对照

输入：「为什么我的 React 组件每次都重新渲染？」

| 模式 | 回复 |
|------|------|
| 正常 | 您的 React 组件反复渲染，很可能是因为您在每次渲染时都创建了一个新的对象引用。内联对象作为 prop 传递时，每次都会被视为新值，从而触发子组件重新渲染。建议使用 `useMemo` 包裹该对象。 |
| 轻 | 您的组件每次渲染都生成新对象引用，故反复渲染。用 `useMemo` 包裹即可。 |
| 精 | 每次渲染新对象引用。行内对象 prop = 新引用 = 重渲染。用 `useMemo` 包住。 |
| 极 | 行内 obj prop → 新 ref → 重渲染。`useMemo`。 |
| 文言 | 每繪新生物，故頻重繪。以 `useMemo` 包之可也。 |

## 安全边界

以下情况 **自动暂停莫言模式**，完整叙述后再恢复：

- 安全警告
- 不可逆操作确认（删除表、强推、覆盖文件）
- 多步顺序指令（片段排序易误）
- 用户明确要求澄清

## 涵盖场景

主技能 `moyan` 启动后自动覆盖：

| 场景 | 行为 |
|------|------|
| 普通问答 | 按当前强度（轻 / 精 / 极 / 文言）压缩输出 |
| 写 commit | 转 Conventional Commits，标题 ≤50 字符，only-when-needed body |
| code review | 一行式：`L42: 🔴 bug：user 可空。加判空守卫。` |
| 安全 / 破坏性操作 | 自动暂停压缩，完整叙述后恢复 |

## 仓库结构

```
moyan/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   └── moyan/SKILL.md
├── README.md
└── LICENSE
```

就这些。一个 SKILL.md 装下全部行为。无脚本、无依赖、无 hooks。

## 致谢 / 缘起

- [Julius Brussee / caveman](https://github.com/JuliusBrussee/caveman) —— 原作。本仓库的初衷：向原作者提的 PR [#76](https://github.com/JuliusBrussee/caveman/pull/76) 迟迟未合并，遂单开一仓以飨中文用户。
- 莫言先生 —— 借名

## License

MIT
