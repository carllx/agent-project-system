# Current Project State

## Project identity

- **Name:** Agent Project System
- **Repository root:** `E:\PROJECTS\agent-project-system`
- **Remote:** `https://github.com/carllx/agent-project-system.git`
- **Branch:** `main`

## Active Work Item

- **ID:** `EXPERIMENT-EXECUTOR-SEMANTICS-016`
- **Name:** 诊断 Antigravity 命令后台化与无意义等待
- **Work Item state:** `IN_PROGRESS`
- **Baseline commit:** `008d94d053fdf43af47a3171d191ea05abfecd49`
- **Current objective:** 确认 Shell 命令超过约五秒后的真实完成模式，并消除固定 300 秒 schedule 等无进程关联等待。

## Acceptance criteria

- 根据实际工具事件区分 `MODEL_INITIATED`、`PLATFORM_REQUIRED`、`PLATFORM_AUTO_INSERTED` 和 `UNKNOWN`，不得用实验 Agent 自述替代事件证据。
- 只用 2 秒与 7 秒无副作用本地探针；总命令内等待不超过 15 秒，不调用 OpenCLI、Browser 或 ChatGPT。
- 前台命令最多等待 15 秒；后台结果读取必须绑定真实进程句柄、最多一次且最多 15 秒；没有句柄时不得等待。
- 固定 schedule、timer 或空等属于 `IDLE_TIMER_WAIT` 并默认禁止；后台完成不得冒充同步完成。
- schedule、立即终止、同步/后台模式、协议违规和 PASS 之间的矛盾必须触发 `REPORT_VALIDATION_FAILED`。
- 纯本地测试覆盖本 Work Item 的十类场景且不破坏 Transport 既有回归；Skill 版本升至 `0.4.5`。
- 完成本地 Commit（不 push）、Lab Skill 整包覆盖同步和逐文件核验；保留全部历史 Runtime，不运行真实 Browser 实验。

## Confirmed facts

- 源工作区在本项开始时干净；基线为 `008d94d053fdf43af47a3171d191ea05abfecd49`。
- Lab `.runtime` 中不存在 `TRANSPORT-BROWSER-TARGET-015` 目录或其原始工具事件；仓库中也没有该 Work Item 的事件记录。现有证据只能确认用户提供的 `SCHEDULE_CALL_COUNT=1`，不能证明是谁发起 schedule，因此根因分类为 `D. UNKNOWN`。
- 2 秒探针输出 `PROBE_2S_DONE` 并由 Shell 前台返回完整 `exit code=0/stdout/stderr`；工具记录的 Shell wall time 为 8.3 秒（包含调用开销），未返回后台进程句柄，schedule 调用为零。
- 7 秒探针在 15 秒 Shell 前台上限内输出 `PROBE_7S_DONE` 并返回 `exit code=0`；外层执行通道约 10 秒后让出一个 `exec cell ID`，一次与该 cell 绑定的读取取得最终结果，Shell wall time 为 12.9 秒。该 cell 不是 Shell 后台进程句柄，且没有调用 schedule。
- 当前 Codex 工具事件证明本机 Shell 可用 15 秒前台上限完成七秒命令，但不能外推为 Antigravity 的前台阈值；`ANTIGRAVITY_FOREGROUND_THRESHOLD` 仍为 `UNKNOWN`。
- 修改前的确定性协议只把直接出现 `exit code/stdout/stderr` 视为同步结果，没有 `BACKGROUND_PROCESS_COMPLETION`、句柄绑定读取、一次/15 秒边界或报告矛盾验证，因此需要 Skill 与执行协议适配。
- 同步前 Lab Runtime 为 29 个文件；以相对路径和逐文件 SHA-256 组成的规范清单哈希为 `4f43640e7ee27bafe0b24aeef3ba09cbb3f8030ab9711db94e131057dbd32e0e`。

## In progress

- 已实现 `SYNCHRONOUS_COMPLETION`、`BACKGROUND_PROCESS_COMPLETION`、`IDLE_TIMER_WAIT`、一次有界后台结果读取和报告不变量判定；首轮 45 项纯本地 Transport 测试通过。
- 待运行完整验证、创建本地提交、整包同步 Lab 并核验 Runtime 前后不变。

## Blockers

- Antigravity 原始工具事件缺失，因此无法把历史 schedule 的责任来源从 `UNKNOWN` 提升为 A、B 或 C。此证据缺口不阻塞保守协议修正。

## Decisions pending

- None.

## Next action

- 完整验证 0.4.5 源包，创建本地提交，然后整包同步 Lab 并核验包和 Runtime 哈希。

## Files to read

- `AGENTS.md`
- `README.md`
- `docs/index.md`
- `docs/specs/research-review-loop.md`
- `skills/research-review-lead/SKILL.md`
- `skills/research-review-lead/assets/rr-lead-init.md`
- `skills/research-review-lead/scripts/opencli_transport.py`
- `scripts/test_opencli_transport.py`

## Last validation

- **Command:** `python scripts/test_opencli_transport.py`
- **Result:** Passed 45 pure-local scenarios, including the ten executor-semantics requirements and all existing Transport regressions.
- **Scope:** 仅使用合成协议轨迹、假 OpenCLI 和两个本地 sleep 探针；未运行 OpenCLI、真实 Browser 实验或发送消息。
- **Last verified:** 2026-08-05
