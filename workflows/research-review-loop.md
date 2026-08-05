# Research & Review 循环 (RR Loop)

本工作流定义了 IDE Agent 与浏览器端 RR Lead 之间的标准交互循环。第一版（MVP）每个工作项默认最多循环六次。

## 循环触发条件

- 用户提出了新的需求。
- 前置任务产生交接请求（Handoff）。
- 前置测试失败，需要 RR Lead 重新进行技术判断。

## 循环步骤

1. **Step 1: 上下文组装 (IDE 侧)**
   - IDE Agent 收集本地项目状态、代码结构及用户原始需求，生成 `templates/context-packet.md` 并发送给 RR Lead。

2. **Step 2: 分析与指令 (RR Lead 侧)**
   - RR Lead 接收包内容，进行必要的外部技术调研与可行性判断。
   - RR Lead 必须按照固定的标题格式进行响应，将下一步指令发送给 IDE。

3. **Step 3: 执行与验证 (IDE 侧)**
   - IDE Agent 根据 `NEXT_WORK_ORDER` 进行本地代码修改、构建与测试。
   - IDE Agent 将执行结果（无论成功或失败），组装为 `templates/change-packet.md` 返回给 RR Lead。

4. **Step 4: 循环判断**
   - 如果测试成功且达到验收标准，流程结束，进入 `ACHIEVED` 状态。
   - 如果出现严重阻塞需用户决策，生成 Decision Request，进入 `NEEDS_DECISION` 状态。
   - 否则继续进入 Step 2，推进下一轮循环。

## RR Lead 固定响应格式

RR Lead 在向 IDE Agent 发出响应时，必须包含以下固定标题块（不得使用复杂 JSON，而是纯文本小标题）：

### STATUS
[当前状态：ACHIEVED / BLOCKED / NEEDS_DECISION / STALLED / UNSAFE / IN_PROGRESS]

### GOAL_CHECK
[简述当前进度与最初设定目标的对齐情况，确认没有发生目标漂移]

### FINDINGS
[外部调研结果或针对 IDE 返回结果的技术分析]

### BLOCKERS
[当前阻碍目标完成的实质性问题。如果没有，请填 None]

### DEBT
[执行过程中发现的非阻塞性问题或优化建议，记录下来但不妨碍继续推进]

### NEXT_WORK_ORDER
[发给 IDE Agent 的下一条明确、可执行的具体指令]

### VALIDATION
[要求 IDE Agent 如何验证上述指令是否执行成功的标准]

### USER_DECISION_REQUIRED
[是否需要用户介入。如果需要，提供“三选项一推荐”的白话描述；否则填 None]
