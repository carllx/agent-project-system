# Active Work Item 状态表

_用途：本项目中唯一的全局“事实源”记录板。它用于跨越多个对话，追踪当前唯一活跃的任务状态。_

---

- **Work Item Name**: [在此处填写任务简短名称]
- **Conversation ID (当前负责的对话)**: [记录当前活跃对话的 ID]
- **Current Status**: `IN_PROGRESS` (可选值: `ACHIEVED`, `BLOCKED`, `NEEDS_DECISION`, `STALLED`, `UNSAFE`, `IN_PROGRESS`)

## 目标 (Goal)

- [填写本 Work Item 试图完成的明确目标]
- [填写验收标准 (Definition of Done)]

## 统计信息

- **当前所在循环轮数 (Current Loop Count)**: 0 / 6
- **启动时间**: [时间戳]

## 执行简史 (Timeline)

* `[时间戳]` - 创建 Work Item。
* `[时间戳]` - 发送 Context Packet 给 RR Lead。

_(注意：此文件由 IDE Agent 在发生状态流转时负责更新。只能记录事实发生的事情，不能写大段推断或虚构的未来计划。)_
