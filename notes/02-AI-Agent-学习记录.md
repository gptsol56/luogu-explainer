# 二、AI Agent 基础认知与实践

这一章不抄教程。我把它当成一份实验记录来写：结论尽量标清楚哪些是我在本机真的跑出来的数字，哪些只是我的推断。用的底座是 MiniMax，跑的是 MiniMax Code（内部代号 MCode）这个 Agent 运行时。所有命令和输出都可以复现。

## 2.1 Agent 和一次普通的 LLM 对话，差在哪

先说结论：差的不在模型，在外面那圈东西。

普通的 LLM 对话是「一问一答」：你把问题丢进去，模型生成一段文本，结束。它看不到你的文件系统，跑不了命令，也不知道上一轮你说过什么。它的输出质量完全取决于提示词里给了多少信息 —— 你得把背景全喂进去。

Agent 是把这个「生成一段文本」换成了一个循环：观察 → 决策 → 行动 → 观察结果 → 继续或结束。模型不再只是输出文字，它输出的是「我要调用这个工具，参数是这些」，宿主（harness）真的去执行，把真实结果再喂回给模型。

我这台机器上做过一个很干净的对照。同一个任务：「执行 python -c print(1234567*7)，把输出原样告诉我」。

纯对话的模型只能自己心算并把结果写进文字里 —— 它报什么就是什么，你无从验证。接了 bash 工具的 Agent 会真的去起一个进程、读回 stdout。实测两次（官方通道 MiniMax-M3.1-Flash、custom_provider 通道 MiniMax-M3）返回的都是 8641969，跟 1234567 × 7 完全一致。

> 这里修正我自己一个先前的错误判断：我之前记录过「Flash 模型工具调用输出畸形、不可用」。这次用当前版本重新实测，两个通道都正常。说明「模型不能用」这种结论必须自己复验，不能拿旧记录当结论 —— 这一点本身就是用 Agent 干活时最容易犯的错。

## 2.2 一个 Agent 系统由哪些部分组成

我现在的理解是六块。下面每一块我都写上本机的具体实现和我实测到的数字。

### ① 模型：只负责推理，不负责做事

模型在 Agent 里退化成「决策器」。它读上下文，输出下一步动作。MiniMax 在本机接了三种通道：官方 provider（minimax/MiniMax-M3.1-Flash，走 agent.minimax.cn）、custom_provider（minimax-cn/MiniMax-M3，走 Anthropic 协议兼容端点）、以及 ECC 自带的 Python provider（走 https://api.minimaxi.com/anthropic）。

### ② 工具调用：模型与外界唯一的接口

工具是模型能触碰现实的唯一通道。本机接了 5 个 MCP server：chrome-devtools（30 个工具）、playwright（25 个）、dynamic-workflows（11 个）、kaggle（29 个）、caveman（5 个），再加上一堆内置工具（read / write / edit / bash / grep / glob）。

MCP（Model Context Protocol）解决的是「工具怎么被统一描述给模型看」的问题：一个 JSON 里声明 server 名、传输方式和参数 schema，模型看到的就是一张标准工具表，不用为每个工具单独写适配。我实测过 chrome-devtools 的握手：发 initialize 拿到 serverInfo 是 chrome_devtools v1.10.1，再发 tools/list 一次返回 30 个工具名，整个过程是真的走 stdio 子进程 + JSON-RPC，不是 mock。

### ③ 上下文管理：窗口是有限资源

上下文窗口有上限，而且每次请求都要为它付钱。本机官方通道 MiniMax-M3 / M3.1-Flash 标称 context 512000、output 128000，另有 1000000 的可选项（会提示 higher_usage）；custom_provider 通道那三个模型标的是 context 200000、output 64000 —— 同一款模型，通道不同给的配额不一样，这个差异值得记住。

上下文管理的另一个面向是「选材」：塞进去的东西越多，模型越容易抓不住重点。本机装完 ECC 后技能目录从 59 个涨到 196 个，新会话实测可见技能 246 个（含插件技能）。这些技能的 description 全部常驻在每次 prompt 里 —— 我粗算过 ECC 那 328 个技能的描述文字约 9.9 万字符，折合约 2.8 万 tokens。每一次对话都在为此付费。

### ④ 任务规划：把一件事拆成可验证的步骤

长任务如果不拆，模型很容易在中途跑偏。做法是显式维护一份待办清单，每完成一项就更新状态。本机 runtime 的 todowrite 就是干这个的。

### ⑤ 权限与沙箱：决定 Agent 能碰到什么

Agent 的破坏力和它的能力成正比。本机有 permissionMode 控制（auto / smart / off），还有逐工具的审批（ask_user）、不可逆操作二次确认、以及删除保护（nativeDelete）。写文件时的另一个硬约束是「拒绝穿透符号链接写」—— 因为技能目录里大量是 junction（Windows 目录联接），穿透写会把真实目标改掉。

### ⑥ 记忆：让经验跨会话存活

Agent 的记忆分两层：一层是会话内的（这段对话的上下文），一层是跨会话的（本机写在 ~/.minimax 下的 MEMORY.md 和 user memory）。后者的作用是「下次不用重新教一遍」。我在这个会话里积累的那条「Windows 中文 locale 下管道 JSON 必须 ensure_ascii=True」的规则，就是靠这层机制留下来的。

## 2.3 什么是 Harness

Harness 是把模型、工具、执行流程组织起来的那个外壳。换个说法：模型是发动机，Harness 是车架、方向盘和传动。没有 Harness，模型就只是一个一次性的 API 调用；有 Harness，它才是一个能自己跑起来的 Agent。

Harness 负责的事至少包括：怎么把工具表塞进提示词、模型返回调用意图后由谁去执行、结果怎么回灌、执行失败要不要重试、上下文满了怎么压缩、哪些工具这次允许用、每一步要不要人确认、预算和步数怎么卡。

本机这个 harness 就是 MiniMax Code。它把上面这些开关都暴露成了命令行参数，我实测下来最有用的几个（括号里是对应我这轮真实用它们解决的问题）：

| Harness 能力 | 参数 | 我这轮用它解决的问题 |
| --- | --- | --- |
| --model | 指定 provider/模型 | 对比官方通道与 minimax-cn 通道的工具调用行为差异 |
| --permission off | 关掉逐次审批 | 跑批量脚本和自动化验证时不被交互卡住 |
| --max-steps | 限制最大步数 | 试探一个任务到底需要几轮才收敛 |
| --file | 把提示词作为附件传入 | Windows 下命令行内联引号会被 PowerShell 吃掉，改用文件才稳 |
| --ptc | 程序化工具调用 | 让模型在一次响应里并行发起多个工具调用 |
| --output-format json | 结构化输出 | 直接读 usage 字段做 token 计量 |
| --effort | 思考档位 | 控制推理深度与耗时 |

Harness 也定义了「什么叫完成」。本机 runtime 有一条硬规则：Agent 不能自己宣称验证通过，只能报告自己跑过哪些检查。这条规则的存在，直接决定了这套系统的可信度边界。

## 2.4 怎样描述任务、提供上下文

这是我觉得最需要练习、也最难教给别人的一块。我在这台机器上总结出五条，每条都有对应的翻车现场。

### 规则一：说完成判据，不说过程

「帮我改一下 MCP 配置」几乎必然翻车，因为「改好」没有定义。「这个 JSON 现在第 21 行缺一个逗号，导致整个文件解析失败；补上逗号后用 json.load 验证能读出 4 个 server 名」—— 这句话我能直接执行、执行完还能自检。

### 规则二：给出可验证的检查方式

不要写「确认一下有没有问题」，要写「跑 xxx 命令，把输出原样告诉我」。前者的结果我无法判断真假，后者的结果可以核对。上面那个 1234567×7 的例子就是靠这条才能验证的。

### 规则三：路径要绝对、要引号

本机工作区路径是 D:\新建文件夹\淳阳项目组\第一阶段 GIT and agent —— 有空格、有中文。相对路径会被 Agent 猜错，带空格的路径不加引号会被 PowerShell 拆成两段。

### 规则四：长提示词走文件，不要内联

我实测过三种写法：命令行双引号内联 → PowerShell 把引号吃掉，报错信息是「未知选项」这种完全误导性的东西；--input 传文件路径 → 报「--input currently 只接受 -」；--input - 配管道 → PowerShell 传给原生程序的是对象不是文本，提示词直接丢了。正确写法是 --file 附加文件。

### 规则五：要求先取证再表态

「先取证再表态，结论区分实测/推断/未测」—— 我把它写进了常驻记忆，因为它能挡掉最贵的一类错误：Agent 用一句听起来很有道理的假话把任务带偏。反例就在这篇文档的写作过程中：我一开始准备把「Flash 工具调用畸形」这条旧结论直接写进笔记，一实测就发现它已经不成立了。

> 反过来说，规则五不是万能的。我有一次让 Agent 批量写清理脚本，它在 PowerShell 里同时用了 $R（根路径）和 $r（循环变量）。PowerShell 变量名大小写不敏感，$r 静默覆盖了 $R，结果「保留项校验」把 7 个必须存在的路径全报成 GONE。Agent 自己跑出来的 dry-run 结果看起来很合理，但结论是错的 —— 说明「Agent 报告了检查通过」和「检查真的通过」之间还有距离。

## 2.5 MiniMax 在本机的实测基线

这一节是我在本机跑出来的数字，换台机器数字会变，但测试方法可以照抄。

### 模型与通道矩阵

| 通道 | 模型 | context / output | 工具调用实测 | 思考模式 |
| --- | --- | --- | --- | --- |
| 官方 minimax | MiniMax-M3.1-Flash | 512000 / 128000 | 通过（输出 8641969） | forced_on，无法关闭 |
| 官方 minimax | MiniMax-M3 | 512000 / 128000 | 通过 | switchable |
| custom_provider minimax-cn | MiniMax-M3 | 200000 / 64000 | 通过（输出 8641969） | switchable |
| custom_provider minimax-cn | MiniMax-M3.1-Flash | 200000 / 64000 | 通过 | switchable |
| custom_provider minimax-cn | MiniMax-M2.7 | 200000 / 64000 | 未单独测 | switchable |

两点值得单独记：其一，同一款模型在两条通道上的 context 配额差了一倍多（512000 vs 200000），选通道不只是选价格，也是选配额。其二，官方通道的 M3.1-Flash 思考模式是 forced_on —— 强制开启且不能关，想省时间只能换模型或换通道。

### 程序化工具调用（PTC）

这是本机 harness 的一项能力：模型在一次响应里直接发起多个工具调用，由 harness 编排执行。我实测让它并行做三件事（打印 A-OK / B-OK / C-OK），结果三件事全部执行、退出码均为 0。对「同时读 5 个文件」这类任务，能把轮次从 5 轮压到 1 轮。

### Token 计量与缓存

跑一次最小任务（回复两个字），读 --output-format json 的 usage 字段：inputTokens 20094、outputTokens 3、cacheReadTokens 185、totalTokens 20282，durationMs 29454，protocol 标成 anthropic-messages，variant 标成 thinking。

这组数字说明两件事。第一，光是系统提示 + 工具表 + 技能清单，输入就已经 2 万 token 了 —— 这是固定成本，跟你问什么无关。第二，cacheReadTokens 185 说明提示前缀被缓存命中了一部分，说明同一个 Agent 连续追问时，重复的系统提示不会全额重新计费。

> 一个反差值得记：问「回复两个字」花了 29.4 秒。耗时大头不在模型生成（只有 3 个输出 token），而在思考模式和工具表准备。所以「换个更快的模型」未必是提速的正确解法，先要看瓶颈到底在哪。

### 端点与协议

官方端点是 agent.minimax.cn，custom_provider 走的是 api.minimaxi.com/anthropic（Anthropic 兼容协议）。ECC 自带的 MiniMax provider 默认写的是海外站 api.minimax.io，我把它覆盖成了国内端点，并且它的 _uses_anthropic_messages() 会按 baseURL 自动切协议。实测：从国内端点真实调用，返回内容正确，usage 为 input 15 / output 89 / cache_read 197。

## 2.6 踩坑记录：这轮真实遇到并解决的问题

按《前置学习任务》的要求，这部分记的是实际问题与解决过程，不是教程摘要。

| 现象 | 根因 | 怎么解决的 |
| --- | --- | --- |
| github.com:443 连不上，git clone 报 curl 28 | 本机到 GitHub 主站的网络被重置 | 改走 api.github.com 的 tarball 通道，实测 anthropics/skills 4.1MB 正常下载 |
| 读 569 个 SKILL.md 直接超时 420 秒 | tarfile 用 r:gz 模式每次 extractfile 都从压缩流起点重解压 | 先 gzip.decompress 再用 mode=r: 随机读，降到 27 秒 |
| pip install anthropic 装到一半失败，import 报 No module named types.shared | Windows 路径超过 260 字符 | 在工作区内建短路径 venv 重装，anthropic 2.12.0 正常 |
| MCP 配置整体读不出来，报 MCP_STORAGE_READ_FAILED | mcp.json 第 21 行 skillsmp 块后少一个逗号 | 补逗号并原子写回，4 个 server 全部可读 |
| MCP 加完当前会话调不到 | 远端/stdio MCP 的用户态授权只在 Desktop 侧装配，CLI 运行时静默跳过 | 重启 MiniMax Code Desktop 后生效 |
| 给 ECC 选 profile 时提示需要显式 hook 决策 | hooks-runtime 会给每次工具调用挂 PreToolUse/PostToolUse/Stop 钩子 | 实测钩子能力组包含自动改写源码、重写命令、transcript 外发、权限门控，选 --no-hooks |
| 写 Node 脚本时 Windows 路径里的反斜杠被吞 | JS 模板字符串里非法转义被静默处理 | 反斜杠双写，写完立刻回读硬编码路径行核对 |
| 读 MCP 子进程输出时超时，但真实原因是编码错误 | Windows 中文 locale 默认 cp936，读线程抛 UnicodeDecodeError 后死掉，异常被掩盖成超时 | JSON 全部 ensure_ascii=True，子进程显式 utf-8 + errors=replace，读线程 try/except 兜住异常 |
| PowerShell 里 $R 和 $r 互相覆盖，校验全报 GONE | PowerShell 变量名大小写不敏感 | 根路径改用大写常量名，循环变量换名，保留项校验照实打印 |
| select() 在 Windows 管道上报 WSAStartup 失败 | select 只支持 socket，不支持普通管道 | 改用后台读线程 + queue |

把这些放在一起看，会发现一条主线：这轮真正花时间的地方，没有一件是「模型不够聪明」，全部是环境差异 —— 编码、路径长度、权限边界、网络出口、变量名大小写。Agent 的能力上限由模型决定，但实际可用性由这些细节决定。

## 2.7 Agent 能不能当「外置大脑」

先给结论：能，但要限定用法 —— 当作「可验证的外置大脑」，不是「不用思考的替身」。

它已经能实打实承担的事：跨会话记住偏好和踩过的坑（MEMORY.md / user memory）；把重复的工作流固化成技能（我这轮装了 18 个 GitHub 上的技能，含 ECC 整套 328 个）；通过 MCP 扩展工具面（浏览器自动化、数据库、比赛环境）；定时或后台执行长任务；以及在真实代码库上做改动并自己跑验证。

它做不到、或者做了会出事的事，我也有实测证据：

一是上下文成本是固定且不小的。2 万 token 的系统提示 + 技能描述常驻，意味着问一句「在吗」也在付这个钱。装 328 个技能之后这个问题更明显 —— 这也是我最终选 developer profile（138 个技能）而不是 full 的原因。

二是它会给出看起来合理但错误的结论。前面那个 $R / $r 的例子：Agent 的 dry-run 输出格式完整、逻辑自洽，结论全错。

三是破坏性操作需要边界。本机这轮的规矩是：删文件前先确认目标路径、逐个删、删完回读存在性，不做未经验证的递归删除。装 ECC 时我还撞上了一次真实拦截：想把源码从临时目录搬到用户目录，直接被本地安全策略挡下 —— 「递归写入/删除目标无法在工作区内验证」。这类护栏不是碍事，它替我挡住了一次误删。

> 《前置学习任务》里那句话我认同并且实践下来：鼓励用 AI 辅助学习，但要理解相关知识并对生成结果做检查验证。具体到我这份笔记 —— 上面每一个数字都是在本机跑出来的，但「为什么这个模型是这个配额」「为什么这条通道快一点」背后的权衡，是我自己在读文档和试错里补的。Agent 负责把事实摆出来，判断得自己来做。

### 下一步

三件事：一，把本机这套 ECC 的 profile、hooks 决策、MCP 配置整理成一份可复现的安装说明，让换机器时不用重新踩坑；二，把这轮踩的 Windows 编码/路径/管道问题做成一个带自检的小脚本，让每次新会话开始前先跑一遍；三，继续用 Agent 做本阶段的学习笔记，但每写完一段就自己核一遍数据来源。
