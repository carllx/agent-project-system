---
name: research-review-lead
description: 规定 IDE Agent 与浏览器端 Research Review Lead (RR Lead) 之间的通讯格式与合作规则。
---

# Research Review Lead 协同准则

本准则定义了 IDE Agent 如何通过文本格式向浏览器端的 RR Lead 报告状态，并接受指令。请注意，目前由于 OpenCLI 文件上传不可靠，不得依赖自动化上传大体积文件，应使用轻量级的文本包格式。

## 角色边界再确认

- **RR Lead**：负责宏观规划、外部资源检索、问题排查的技术思路提供。不掌握本地真实文件运行情况。
- **IDE Agent**：负责本地文件编辑、执行。掌握项目真实的“事实真相”。如果 RR Lead 的指令与本地证据相悖，**IDE Agent 必须果断出示证据予以纠正**。

## 与 RR Lead 交互的原则

1. **事实导向**：向 RR Lead 发送代码变更或测试结果时，必须附带真实的 Git Diff 和日志输出，禁止凭空捏造执行结果。
2. **不陷入僵局**：如果由于某种原因导致 RR Lead 给出的方案在本地重复失败（超过 2 次），IDE Agent 必须明确在下一个包中标注 `BLOCKED` 并要求新的技术路径，不允许无限盲目重试。
3. **接受指令格式**：RR Lead 下发的指令必须遵循固定的 Markdown 标题格式。若 RR Lead 发出自由散漫的文字，IDE Agent 应提醒其使用规范格式。

## 期待的 RR Lead 响应格式

在每一轮响应中，IDE Agent 必须期待 RR Lead 输出以下标准格式：

### STATUS
[当前状态：ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE / IN_PROGRESS]

### GOAL_CHECK
[进度对齐情况]

### FINDINGS
[外部调研结果或技术判断]

### BLOCKERS
[当前阻塞因素]

### DEBT
[非阻塞问题记录]

### NEXT_WORK_ORDER
[具体的下一步指令]

### VALIDATION
[验证指令成功的方法]

### USER_DECISION_REQUIRED
[是否需要用户介入，及选项]
