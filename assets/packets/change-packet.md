# Change Packet Template

> 本文件是可复用模板，不是某一次实际运行记录。填写后的临时 Packet 默认不得提交到仓库。

用于向 RR Lead 返回一次本地执行的精简、可核验结果。

## Work Item

- **Conversation ID:** [当前对话标识]
- **Current loop:** [轮次]
- **Objective executed:** [本轮执行目标]

## Change summary

[用白话概括实际改变。]

### Git diff stat

```text
[git diff --stat 的真实输出]
```

### Key diff

```diff
[只放理解变更所必需的关键 Diff；其余用路径和摘要说明]
```

## Validation

- **Command:** `[真实命令]`
- **Exit code:** [真实退出码]
- **Necessary output:**

```text
[支持结论的必要输出或错误，不粘贴无关长日志]
```

## Local fact correction

[若外部判断与本地证据冲突，指出冲突并引用上方证据；否则写 None。]

## Blockers and debt

- **Blockers:** [影响验收标准的问题或 None]
- **Debt:** [非阻塞发现或 None]
