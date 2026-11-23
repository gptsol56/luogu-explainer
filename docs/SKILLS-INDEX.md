# 本机 Agent Skill 索引

> 本文件由 `verify_skills.py --write-index` 自动生成, 请勿手改。
> 改完技能目录后重跑一次, 索引与实际可见性就永远对得上。

## 现状速览

| 指标 | 值 |
|---|---|
| 入口层唯一技能 | 196 |
| MCode 可见 | 196 |
| 被技能开关禁用 | 0 |

## 目录结构约定

| 目录 | 角色 | 规则 |
|---|---|---|
| `~/.agents/skills/` | **入口层(真值源)** | 每个技能一个目录, 目录名 == frontmatter 的 `name` |
| `~/.minimax/skills/` | 兼容层 | 只放 junction, 全部指回 .agents; 不放实体 |
| `~/.claude/skills/` | Claude Code 域 | 由 kkSwitch / CherryStudio 管理, 只去重、不改其链接指向 |
| `~/.minimax/skills-archive/` | 归档区 | 冗余副本移到这里, 不删除, 可回退 |
| `~/.agents/skills/@<ns>/` | SkillHub 命名空间层 | **二级子目录照样被扫描**; 一级 `@<ns>` 目录本身不算技能 |

## 技能清单

### 编码与工程

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `ai-coder` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\ai-coder` | 一站式全栈开发专家（Full-stack development expert）。支持 Vue3/React/Angular/SpringBoot/Node.js/Python 等主流技术栈，覆盖需求分析、架构设计... |
| `code-expert` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\code-expert` | A professional-level programming AI that follows a document-driven development workflow. When the user asks... |
| `code-mate-claude-code` | - | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\code-mate-claude-code` | Run Claude Code non-interactively for coding tasks. Use when the user asks to delegate work to Claude Code. |
| `code-mate-minimax-code` | - | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\code-mate-minimax-code` | Run MiniMax Code non-interactively for coding tasks. Use when the user asks to delegate work to MiniMax Code. |
| `foundation-builder` | 1.9.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\foundation-builder` | 在 Foundation 底座（React19+TS+Vite SPA / Express 5 / Zod v4 / better-sqlite3）上开发全栈功能时使用：新增页面与服务端模块、接入登录/会话/own... |
| `gitee` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\gitee` | 提供Gitee仓库创建与代码提交功能；当用户需要创建Gitee仓库、提交代码到Gitee或管理Gitee项目时使用 |
| `vercel-cli-with-tokens` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\vercel-cli-with-tokens` | Deploy and manage projects on Vercel using token-based authentication. Use when working with Vercel CLI usi... |
| `vercel-composition-patterns` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\vercel-composition-patterns` | React composition patterns that scale. Use when refactoring components with boolean prop proliferation, bui... |
| `vercel-optimize` | 1.2.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\vercel-optimize` | Use for Vercel cost and performance optimization on deployed projects, especially Next.js, SvelteKit, Nuxt,... |
| `vercel-react-best-practices` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\vercel-react-best-practices` | React and Next.js performance optimization guidelines from Vercel Engineering. This skill should be used wh... |
| `vercel-react-native-skills` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\vercel-react-native-skills` | React Native and Expo best practices for building performant mobile apps. Use when building React Native co... |
| `vercel-react-view-transitions` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\vercel-react-view-transitions` | Guide for implementing smooth, native-feeling animations using React's View Transition API (`<ViewTransitio... |

### Skill / Prompt 工厂

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `find-skills` | 1.7.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\@indiv-guipi\find-skills` | 不知道装什么技能？想让 AI 自己找到最合适的技能？技能发现·Find Skills 是场景驱动+关键词双模式的技能发现工具（skill discovery / skill finder / install ski... |
| `prompt-optimizer` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\prompt-optimizer` | 大师级AI提示词优化专家。当用户需要优化提示词、改进prompt、进行提示词工程、设计高效提示词时使用此技能。将模糊的请求转化为精准构建的提示词，最大化释放AI在所有平台的潜力。Keywords: prompt o... |
| `skill-creator` | 1.0.0 | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\skill-creator` | Create, edit, evaluate, and optimize skills, including benchmarking and description tuning for better trigg... |
| `skillhub` | 1.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\skillhub` | SkillHub 技能商店（国内优先源，已确认为本机的优先技能安装源）。当需要搜索、发现、安装、升级技能时（用户说"找个技能""装个技能""有没有做 XX 的技能""技能推荐"），优先用本技能：skillhub s... |
| `skills-factory` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\skills-factory` | 技能工厂 - 专注于为Expert Agent设计和创建高质量、标准化的技能（Skills）。支持编码规范类、工作流程类、领域知识类、模板类、检查清单类、工具使用类、问题解决类等各类技能的设计、编写和优化，内置UI... |

### 设计 · 视觉 · 交付物

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `design-iface` | 1.0.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\design-iface` | 设计能力统一入口：检索 UI 风格/配色/字体/体验准则、生成配图插画、读图做视觉核对。 只要任务涉及界面设计或视觉产出，就用这个技能，不要凭记忆编造风格名、配色值或动效参数， 也不要手写 SVG/canvas 顶... |
| `gpt-taste` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\gpt-taste` | Classic skill for GPT and Codex, opt-in: it runs only when called by name. Layout variance, a strict AIDA p... |
| `image-creator` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\image-creator` | Use it for EVERY request to create, generate, design or edit an image, banner, poster, ad creative, social ... |
| `next-slide` | 1.1.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\next-slide` | Next Slide (a.k.a. Next PPT / 下一代 PPT) — create stunning HTML presentations from scratch or convert PowerPo... |
| `office-transform` | 1.0.0 | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\office-transform` | Extract or edit a selection from xlsx, docx, pdf, or pptx into a new file; the source is never modified. |
| `slides` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\slides` | Create strategic HTML presentations with Chart.js, design tokens, responsive layouts, copywriting formulas,... |
| `ui-ux-pro-max` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\ui-ux-pro-max` | UI/UX design intelligence for web, mobile, and desktop. This skill should be used when designing, building,... |
| `web-design-guidelines` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\web-design-guidelines` | Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibil... |
| `writing-guidelines` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\writing-guidelines` | Review docs/prose for Writing Guidelines compliance. Use when asked to "review my docs", "check writing sty... |

### 写作 · 内容处理

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `humanize-ai-text` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\humanize-ai-text` | 学术写作风格工具箱（中英双语，academic writing style toolkit）：论文降AI率、去AI味的风格自查与自然化改写工具（style naturalization & style-patter... |
| `humanizer` | 2.1.1 | 可见 | `C:\Users\CHATGPT\.agents\skills\@clawhub_biostartechnology\humanizer` | Remove signs of AI-generated writing from text. Use when editing or reviewing text to make it sound more na... |
| `humanizer-academic` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\@user_15292d5a\yjkj-humanizer-academic` | Rewrite ACADEMIC / scholarly / professional prose (English, Chinese, or mixed EN-in-ZH) to remove AI-writin... |
| `summarize` | 1.0.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\@clawhub_paudyyin\summarize` | smart summarization capability in the office and document processing domain. Use when the user wants to 支持对... |

### 联网 · 检索 · 浏览器

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `cherry-browser` | 2.0.0 | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\cherry-browser` | Control the user''s visible Agent browser: navigate, click, type, screenshot, debug. Needs the Browser sett... |
| `cherry-computer` | 1.0.1 | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\cherry-computer` | Drive native apps via Computer Use: open, inspect, type, click, screenshot. Needs OS permissions; respect u... |
| `cherry-tool-guide` | 1.8.0 | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\cherry-tool-guide` | Cherry tool routing: bun, uv, rg, knowledge, memory, schedules, skills, MCP, web. Read before shell workaro... |
| `web-access` | - | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\skills-sh-1785812558262` | 所有联网操作必须通过此 skill 处理，包括：搜索、网页抓取、登录后操作、网络交互等。 触发场景：用户要求搜索信息、查看网页内容、访问需要登录的网站、操作网页界面、抓取社交媒体内容（小红书、微博、推特等）、读取动... |
| `web-search` | - | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\web-search` | Web search and content extraction with Tavily and Exa via inference.sh CLI. Apps: Tavily Search, Tavily Ext... |

### 音频 · 视频 · 字幕

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `bilibili-transcript` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\@user_0b65fce7\bilibili-txt` | 提取B站（bilibili.com）视频的完整文字稿。当用户需要提取、获取、下载B站视频的文字稿、字幕、转录内容、语音转文字时使用此skill。支持从视频URL提取音频并使用Whisper进行中文语音识别，生成带时... |
| `dlazy-qwen-tts` | 1.3.5 | 可见 | `C:\Users\CHATGPT\AppData\Roaming\CherryStudio\Data\Agents\.claude\skills\dlazy-qwen-tts` | Alibaba Bailian qwen3-tts text-to-speech. Choose from curated system voices (including dialects) or design ... |

### 地图 · 出行

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `baidu-map-webapi` | 1.0.5 | 可见 | `C:\Users\CHATGPT\.claude\skills\@clawhub_baidu-maps\baidu-map-webapi` | 百度地图 webapi 开发指南。在编写、审查或调试使用百度地图webAPI的代码时应运用此技能，也适用于直接调用百度地图API获取结果的场景。涵盖：地图位置搜索、POI检索、路线规划、建议出发时间、路线耗时预测、... |
| `tencentmap-map-assistant-skill` | 1.5.2 | 可见 | `C:\Users\CHATGPT\.claude\skills\@tencent-adm\tencentmap-map-assistant` | 腾讯地图·地图助手 Skill，一句自然语言调用腾讯地图全套能力，开箱即用。提供 AI 旅游攻略、地点搜索（含评分/人均/营业时间）、关键词提示、路线规划（驾车/步行/公交/骑行）、地址解析与逆解析、行政区划、IP... |
| `travel-planner` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\@user_67790f4b\travelplanner` | 专业旅行规划师，提供个性化旅行行程设计、预算规划和出行攻略。当用户需要以下操作时使用：(1) 规划某个目的地的详细行程，(2) 制作每日行程表（景点/餐厅/住宿安排），(3) 估算旅行预算，(4) 推荐景点、美食、... |

### 其他

| 技能 | 版本 | 状态 | 实体来源 | 用途 |
|---|---|---|---|---|
| `accessibility` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\accessibility` | Design, implement, and audit accessible UI to WCAG 2.2 Level AA across Web, iOS, and Android — semantic ARI... |
| `agent-introspection-debugging` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\agent-introspection-debugging` | Structured self-debugging workflow for AI agent failures using capture, diagnosis, contained recovery, and ... |
| `agent-self-evaluation` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\agent-self-evaluation` | Use after completing any non-trivial task. The agent self-rates its output on 5 axes — accuracy, completene... |
| `agent-sort` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\agent-sort` | Build an evidence-backed ECC install plan for a specific repo by sorting skills, commands, rules, hooks, an... |
| `ai-regression-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\ai-regression-testing` | Regression testing strategies for AI-assisted development. Sandbox-mode API testing without database depend... |
| `android-clean-architecture` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\android-clean-architecture` | Clean Architecture patterns for Android and Kotlin Multiplatform projects — module structure, dependency ru... |
| `angular-developer` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\angular-developer` | Generates Angular code and provides architectural guidance. Trigger when creating projects, components, or ... |
| `api-design` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\api-design` | REST API design patterns including resource naming, status codes, pagination, filtering, error responses, v... |
| `archify` | 3.3" author: tt-a1i | 可见 | `C:\Users\CHATGPT\.agents\skills\archify` | Create validated architecture, workflow, sequence, data-flow, lifecycle/state, ERD, class, tree, timeline, ... |
| `architecture-decision-records` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\architecture-decision-records` | Capture architectural decisions as numbered ADR markdown files in docs/adr/ with context, alternatives cons... |
| `backend-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\backend-patterns` | Backend architecture patterns, API design, database optimization, and server-side best practices for Node.j... |
| `bengali-nlp` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\bengali-nlp` | Bengali (Bangla) text processing patterns including Unicode normalization, script detection, tokenization, ... |
| `brainstorming` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\brainstorming` | You MUST use this before any creative work - creating features, building components, adding functionality, ... |
| `brownfield-retrospective` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\brownfield-retrospective` | Run the ECC engineering process retroactively against an existing project slice. Audit current state, recon... |
| `browser-qa` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\browser-qa` | Run automated post-deploy UI verification with a browser automation MCP (claude-in-chrome, Playwright, or P... |
| `bun-runtime` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\bun-runtime` | Bun as runtime, package manager, bundler, and test runner. When to choose Bun vs Node, migration notes, and... |
| `ck` | 2.0.0 origin: community | 可见 | `C:\Users\CHATGPT\.claude\skills\ck` | Persistent per-project memory for Claude Code (Context Keeper) driven by deterministic Node.js /ck commands... |
| `click-path-audit` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\click-path-audit` | Trace every user-facing button/touchpoint through its full state change sequence to find bugs where functio... |
| `clickhouse-io` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\clickhouse-io` | ClickHouse database patterns, query optimization, analytics, and data engineering best practices for high-p... |
| `code-review-and-quality` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\code-review-and-quality` | Conducts multi-axis code review. Use before merging any change. Use when reviewing code written by yourself... |
| `code-tour` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\code-tour` | Create CodeTour `.tour` files — persona-targeted, step-by-step walkthroughs with real file and line anchors... |
| `codebase-onboarding` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\codebase-onboarding` | Analyze an unfamiliar codebase and generate a structured onboarding guide with architecture map, key entry ... |
| `codehealth-mcp` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\codehealth-mcp` | Real-time structural Code Health via CodeScene MCP — review before edits, verify score deltas after changes... |
| `coding-standards` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\coding-standards` | Baseline cross-project coding conventions for naming, readability, immutability, and code-quality review. U... |
| `compose-multiplatform-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\compose-multiplatform-patterns` | Compose Multiplatform and Jetpack Compose patterns for KMP projects — state management, navigation, theming... |
| `config-gc` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\config-gc` | Garbage collection for your Claude Code configuration. Periodically scans ~/.claude (skills, memory, hooks,... |
| `configure-ecc` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\configure-ecc` | Run the conversational ECC setup wizard inside the current harness: inventory the install, collect scope (u... |
| `context-budget` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\context-budget` | Routes live context checks to the native Codex or Claude Code meter without scanning files, and performs a ... |
| `context-engineering` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\context-engineering` | Optimizes agent context setup. Use when starting a new session, when agent output quality degrades, when sw... |
| `continuous-learning` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\continuous-learning` | [DEPRECATED - use continuous-learning-v2] Legacy v1 stop-hook skill extractor. v2 is a strict superset with... |
| `continuous-learning-v2` | 2.1.0 origin: ECC | 可见 | `C:\Users\CHATGPT\.claude\skills\continuous-learning-v2` | Instinct-based learning system that observes sessions via hooks, creates atomic instincts with confidence s... |
| `contract-first` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\contract-first` | Coordinate frontend/backend or service-to-service work through one authoritative machine-checkable contract... |
| `conventional-commit-review` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\conventional-commit-review` | Reviews staged changes and drafts a Conventional Commits-compliant commit message with the right type, scop... |
| `council` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\council` | Convene a four-voice council for ambiguous decisions, tradeoffs, and go/no-go calls. Use when multiple vali... |
| `council-multi-model` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\council-multi-model` | Add one optional external Codex critique after the existing council has produced a decision draft. Use when... |
| `cpp-coding-standards` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\cpp-coding-standards` | C++ coding standards based on the C++ Core Guidelines (isocpp.github.io). Use when writing, reviewing, or r... |
| `cpp-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\cpp-testing` | Use only when writing/updating/fixing C++ tests, configuring GoogleTest/CTest, diagnosing failing or flaky ... |
| `csharp-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\csharp-testing` | C# and .NET testing patterns with xUnit, FluentAssertions, mocking, integration tests, and test organizatio... |
| `dart-flutter-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\dart-flutter-patterns` | Production-ready Dart and Flutter patterns covering null safety, immutable state with Freezed, async compos... |
| `database-migrations` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\database-migrations` | Safe, reversible database migration patterns: forward-only production changes, expand-contract zero-downtim... |
| `deepseek-harness-setup` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\deepseek-harness-setup` | Install and operate Everything Claude Code (ECC) on the DeepSeek Harness (DSH): native skill roots (~/.dsh/... |
| `delivery-gate` | 1.1.1 origin: ECC | 可见 | `C:\Users\CHATGPT\.claude\skills\delivery-gate` | Stop hook that blocks Claude from finishing until quality checks pass. Detects rationalization patterns (su... |
| `design-system` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\design-system` | Generate a design system from an existing codebase or audit one for visual consistency: extract tokens (col... |
| `dev-team` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\dev-team` | Simulate a collaborative dev team session where multiple role-based personas (PM, Architect, Developer, QA)... |
| `diagnosing-bugs` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\diagnosing-bugs` | Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this", o... |
| `django-celery` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\django-celery` | Django + Celery async task patterns — configuration, task design, beat scheduling, retries, canvas workflow... |
| `django-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\django-patterns` | Django architecture patterns, REST API design with DRF, ORM best practices, caching, signals, middleware, a... |
| `django-tdd` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\django-tdd` | Django testing strategies with pytest-django, TDD methodology, factory_boy, mocking, coverage, and testing ... |
| `django-verification` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\django-verification` | Run the full Django verification loop — environment check, mypy/ruff/black linting, migration safety, pytes... |
| `dmux-workflows` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\dmux-workflows` | Multi-agent orchestration using dmux (tmux pane manager for AI agents). Patterns for parallel agent workflo... |
| `domain-modeling` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\domain-modeling` | Build and sharpen a project's domain model. Use when discussing codebase terminology, writing or editing a ... |
| `dotnet-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\dotnet-patterns` | Idiomatic C# and .NET patterns, conventions, dependency injection, async/await, and best practices for buil... |
| `e2e-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\e2e-testing` | Playwright E2E testing patterns, Page Object Model, configuration, CI/CD integration, artifact management, ... |
| `ecc-guide` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\ecc-guide` | Answer questions about ECC by reading the live repo surface — agents, skills, commands, hooks, rules, insta... |
| `ecc-recipes` | 1.0.0 | 可见 | `C:\Users\CHATGPT\.claude\skills\ecc-recipes` | Map a described workflow to the right ECC command group with run-order and stop condition, or browse all co... |
| `error-handling` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\error-handling` | Patterns for robust error handling across TypeScript, Python, and Go. Covers typed errors, error boundaries... |
| `eval-harness` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\eval-harness` | Eval-driven development (EDD) framework for AI coding sessions — define capability and regression evals bef... |
| `fastapi-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\fastapi-patterns` | FastAPI best practices covering project structure, Pydantic v2 schemas, dependency injection, async handler... |
| `flutter-dart-code-review` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\flutter-dart-code-review` | Library-agnostic Flutter/Dart code review checklist covering widget best practices, state management patter... |
| `frontend-a11y` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\frontend-a11y` | Accessibility patterns for React and Next.js — semantic HTML, ARIA attributes, form labeling, keyboard navi... |
| `frontend-design-direction` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\frontend-design-direction` | Set an ECC-specific frontend design direction for production UI work. Use when building or improving websit... |
| `frontend-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\frontend-patterns` | Frontend development patterns for React, Next.js, state management, performance optimization, and UI best p... |
| `frontend-slides` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\frontend-slides` | Create stunning, animation-rich HTML presentations from scratch or by converting PowerPoint files. Use when... |
| `fsharp-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\fsharp-testing` | F# testing patterns with xUnit, FsUnit, Unquote, FsCheck property-based testing, integration tests, and tes... |
| `generating-python-installer` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\generating-python-installer` | Commercial-grade Python installer expert for Windows: Nuitka extreme compilation, dist slimming, DLL footpr... |
| `git-workflow` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\git-workflow` | Git workflow patterns including branching strategies, commit conventions, keeping history clean and readabl... |
| `godot-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\godot-patterns` | Idiomatic Godot 4 GDScript patterns - static typing, scene and node design, signals, resources, autoloads, ... |
| `godot-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\godot-testing` | Testing Godot 4 GDScript projects - a zero-dependency headless check scene, gdUnit4 and GUT suites, scene-r... |
| `golang-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\golang-patterns` | Idiomatic Go patterns, best practices, and conventions for building robust, efficient, and maintainable Go ... |
| `golang-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\golang-testing` | Go testing patterns including table-driven tests, subtests, benchmarks, fuzzing, and test coverage. Follows... |
| `growth-log` | 1.1.0 origin: ECC | 可见 | `C:\Users\CHATGPT\.claude\skills\growth-log` | Write growth log entries that extract reusable patterns from completed work — root cause, transferable rule... |
| `hexagonal-architecture` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\hexagonal-architecture` | Design, implement, and refactor Ports & Adapters systems with clear domain boundaries, dependency inversion... |
| `hookify-rules` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\hookify-rules` | Create and configure hookify rules — markdown files with YAML frontmatter that match bash, file, prompt, or... |
| `i18n-sync` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\i18n-sync` | Translate and synchronize application JSON locale files using source-key usage, project terminology, and fo... |
| `impeccable` | 4.10.0 | 可见 | `C:\Users\CHATGPT\.agents\skills\impeccable` | Use when the user wants to design, redesign, shape, critique, audit, polish, simplify, harden, animate, or ... |
| `implement-spec` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\implement-spec` | Implement the result of /to-spec and /to-tickets in code. |
| `inherit-legacy-style` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\inherit-legacy-style` | Prevent AI style drift on legacy projects by scanning the codebase for implicit conventions, resolving conf... |
| `intent-driven-development` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\intent-driven-development` | Turn ambiguous or high-impact product and engineering changes into scoped, verifiable acceptance criteria b... |
| `iterative-retrieval` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\iterative-retrieval` | Pattern for progressively refining context retrieval to solve the subagent context problem. Use when a suba... |
| `java-coding-standards` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\java-coding-standards` | Java coding standards for Spring Boot and Quarkus services: naming, immutability, Optional usage, streams, ... |
| `jpa-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\jpa-patterns` | JPA/Hibernate patterns for entity design, relationships, query optimization, transactions, auditing, indexi... |
| `kotlin-coroutines-flows` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\kotlin-coroutines-flows` | Kotlin Coroutines and Flow patterns for Android and KMP — structured concurrency, Flow operators, StateFlow... |
| `kotlin-exposed-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\kotlin-exposed-patterns` | JetBrains Exposed ORM patterns including DSL queries, DAO pattern, transactions, HikariCP connection poolin... |
| `kotlin-ktor-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\kotlin-ktor-patterns` | Ktor server patterns including routing DSL, plugins, authentication, Koin DI, kotlinx.serialization, WebSoc... |
| `kotlin-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\kotlin-patterns` | Idiomatic Kotlin patterns, best practices, and conventions for building robust, efficient, and maintainable... |
| `kotlin-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\kotlin-testing` | Kotlin testing patterns with Kotest, MockK, coroutine testing, property-based testing, and Kover coverage. ... |
| `laravel-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\laravel-patterns` | Laravel architecture patterns, routing/controllers, Eloquent ORM, service layers, queues, events, caching, ... |
| `laravel-plugin-discovery` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\laravel-plugin-discovery` | Discover and evaluate Laravel packages via LaraPlugins.io MCP. Use when the user wants to find plugins, che... |
| `laravel-tdd` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\laravel-tdd` | Laravel testing strategies with PHPUnit, Pest, model factories, HTTP tests, Sanctum authentication testing,... |
| `laravel-verification` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\laravel-verification` | Verification loop for Laravel projects: env checks, linting, static analysis, tests with coverage, security... |
| `leanrea` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\leanrea` | Reverse engineers shipped software with bounded local CLI inspection. Covers PE headers, Electron archives,... |
| `living-docs-governance` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\living-docs-governance` | Keep a long-lived project's documentation from rotting by assigning existing project docs clear constitutio... |
| `loop-design-check` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\loop-design-check` | Design a goal-oriented agent loop or review one for failure modes: spinning, Goodhart-gaming the verifier, ... |
| `make-interfaces-feel-better` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\make-interfaces-feel-better` | Apply concrete design-engineering details that make interfaces feel polished. Use when reviewing or improvi... |
| `mcp-server-patterns` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\mcp-server-patterns` | Build MCP servers with Node/TypeScript SDK — tools, resources, prompts, Zod validation, stdio vs Streamable... |
| `motion-advanced` | 1.0.0 | 可见 | `C:\Users\CHATGPT\.claude\skills\motion-advanced` | Advanced motion patterns for React / Next.js — drag & drop, gestures, text animations, SVG path drawing, cu... |
| `motion-foundations` | 1.0.0 | 可见 | `C:\Users\CHATGPT\.claude\skills\motion-foundations` | Motion tokens, spring presets, performance rules, device adaptation, accessibility enforcement, and SSR saf... |
| `motion-patterns` | 1.0.0 | 可见 | `C:\Users\CHATGPT\.claude\skills\motion-patterns` | Production-ready animation patterns for React / Next.js — button, modal, toast, stagger, page transitions, ... |
| `mybatis-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\mybatis-patterns` | MyBatis and MyBatis-Spring patterns for mapper design, XML and annotation SQL, result mapping, dynamic SQL ... |
| `mysql-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\mysql-patterns` | MySQL and MariaDB schema, query, indexing, transaction, replication, and connection-pool patterns for produ... |
| `nestjs-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\nestjs-patterns` | NestJS architecture patterns for modules, controllers, providers, DTO validation, guards, interceptors, con... |
| `nextjs-turbopack` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\nextjs-turbopack` | Next.js 16+ and Turbopack guidance — incremental Rust bundling, file-system caching, faster dev startup and... |
| `nuxt4-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\nuxt4-patterns` | Nuxt 4 app patterns for hydration safety, performance, route rules, lazy loading, and SSR-safe data fetchin... |
| `perl-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\perl-patterns` | Modern Perl 5.36+ idioms, best practices, and conventions for building robust, maintainable Perl applicatio... |
| `perl-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\perl-testing` | Perl testing patterns using Test2::V0, Test::More, prove runner, mocking, coverage with Devel::Cover, and T... |
| `plan-canvas` | 1.0.0" origin: ECC | 可见 | `C:\Users\CHATGPT\.claude\skills\plan-canvas` | Open plans and HTML artifacts in a local browser canvas where the human annotates elements, chats, and appr... |
| `plankton-code-quality` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\plankton-code-quality` | Write-time code quality enforcement using Plankton — auto-formatting, linting, and Claude-powered fixes on ... |
| `postgres-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\postgres-patterns` | PostgreSQL database patterns for query optimization, schema design, indexing, and security. Based on Supaba... |
| `prisma-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\prisma-patterns` | Prisma ORM patterns for TypeScript backends — schema design, query optimization, transactions, pagination, ... |
| `product-lens` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\product-lens` | Validate the why before building through four product diagnostics — a YC-style product diagnostic that prod... |
| `production-audit` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\production-audit` | Local-evidence production readiness audit for shipped apps, pre-launch reviews, post-merge checks, and "wha... |
| `prompt-caching-strategy` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\prompt-caching-strategy` | Optimize LLM prompt caching hit rate to reduce API costs and improve latency. Analyzes prompt structure, id... |
| `python-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\python-patterns` | Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and mainta... |
| `python-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\python-testing` | Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage r... |
| `quarkus-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\quarkus-patterns` | Quarkus 3.x LTS architecture patterns with Camel for messaging, RESTful API design, CDI services, data acce... |
| `quarkus-tdd` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\quarkus-tdd` | Test-driven development for Quarkus 3.x LTS using JUnit 5, Mockito, REST Assured, Camel testing, and JaCoCo... |
| `quarkus-verification` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\quarkus-verification` | Verification loop for Quarkus projects: build, static analysis (Checkstyle, PMD, SpotBugs), tests with JaCo... |
| `rails-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\rails-patterns` | Ruby on Rails framework patterns for Rails 7.1+ and 8.x apps. Covers the directory contract, skinny control... |
| `react-native-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\react-native-patterns` | React Native and Expo app patterns — Expo Router navigation, state separation (server/client/route/form), T... |
| `react-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\react-patterns` | React 18/19 patterns including hooks discipline, server/client component boundaries, Suspense + error bound... |
| `react-performance` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\react-performance` | React and Next.js performance optimization patterns adapted from Vercel Engineering's React Best Practices ... |
| `react-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\react-testing` | React component testing with React Testing Library, Vitest/Jest, MSW for network mocking, accessibility ass... |
| `redis-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\redis-patterns` | Redis data structure patterns, caching strategies, distributed locks, rate limiting, pub/sub, and connectio... |
| `repo-scan` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\repo-scan` | Bootstrap pointer that installs the external repo-scan skill from a pinned, reviewable commit. Use when rep... |
| `rules-distill` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\rules-distill` | Scan skills to extract cross-cutting principles and distill them into rules — append, revise, or create new... |
| `rust-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\rust-patterns` | Idiomatic Rust patterns, ownership, error handling, traits, concurrency, and best practices for building sa... |
| `rust-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\rust-testing` | Rust testing patterns including unit tests, integration tests, async testing, property-based testing, mocki... |
| `santa-method` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\santa-method` | Multi-agent adversarial verification: two independent reviewers with the same rubric must both pass before ... |
| `self-improvement` | 3.0.24 | 可见 | `C:\Users\CHATGPT\.agents\skills\@clawhub_pskoett\self-improving-agent` | Captures learnings, errors, and corrections to enable continuous improvement. Use when: (1) A command or op... |
| `skill-comply` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\skill-comply` | Visualize whether skills, rules, and agent definitions are actually followed — auto-generates scenarios at ... |
| `skill-host-compat` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\skill-host-compat` | Lint ECC skills for Codex/Cursor-safe frontmatter and Claude-only substitutions before a skill PR. |
| `skill-scout` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\skill-scout` | Search existing local, marketplace, GitHub, and web skill sources before creating a new skill. Use when the... |
| `skill-stocktake` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\skill-stocktake` | Use when auditing Claude skills and commands for quality. Supports Quick Scan (changed skills only) and Ful... |
| `spec-driven-development` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\spec-driven-development` | Creates specs before coding. Use when starting a new project, feature, or significant change and no specifi... |
| `springboot-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\springboot-patterns` | Spring Boot architecture patterns, REST API design, layered services, data access, caching, async processin... |
| `springboot-tdd` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\springboot-tdd` | Test-driven development for Spring Boot using JUnit 5, Mockito, MockMvc, Testcontainers, and JaCoCo. Use wh... |
| `springboot-verification` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\springboot-verification` | Run the full Spring Boot verification loop — Maven or Gradle build, SpotBugs, PMD, and Checkstyle static an... |
| `story-lifecycle` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\story-lifecycle` | Manage a file-based epic → story → sprint development loop without requiring an external project management... |
| `strategic-compact` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\strategic-compact` | Suggests manual context compaction at logical intervals to preserve context through task phases rather than... |
| `systematic-debugging` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\systematic-debugging` | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes |
| `tdd-workflow` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\tdd-workflow` | Test-driven development workflow: write a failing test first, watch it fail, implement the smallest change ... |
| `test-driven-development` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\test-driven-development` | Use when implementing any feature or bugfix, before writing implementation code |
| `tinystruct-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\tinystruct-patterns` | Expert guidance for developing with the tinystruct Java framework. Use when working on the tinystruct codeb... |
| `token-budget-advisor` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\token-budget-advisor` | Offer a choice of response depth (25%/50%/75%/100%) with token estimates before answering, then answer at t... |
| `typescript-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\typescript-patterns` | TypeScript patterns for strict, type-safe, maintainable code in modern TypeScript and JavaScript applicatio... |
| `ui-canvas` | 1.0.0 | 可见 | `C:\Users\CHATGPT\.claude\skills\ui-canvas` | Preview a UI component mockup in a local browser canvas where the human directly edits it (move, resize, ed... |
| `ui-to-vue` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\ui-to-vue` | Use when the user has UI screenshots or design exports that need batch conversion into Vue 3 components, es... |
| `unified-memory` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\unified-memory` | Share durable, inspectable context and handoffs between Claude, Codex, Hermes, Cursor, OpenCode, and other ... |
| `verification-before-completion` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\verification-before-completion` | Use when about to claim work is complete, fixed, or passing, before committing or creating PRs - requires r... |
| `verification-loop` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\verification-loop` | Run a six-phase verification of a Claude Code session's work — build, type check, lint, tests with coverage... |
| `vite-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\vite-patterns` | Vite build tool patterns including config, plugins, HMR, env variables, proxy setup, SSR, library mode, dep... |
| `vue-patterns` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\vue-patterns` | Vue.js 3 Composition API patterns, component architecture, reactivity best practices, Pinia state managemen... |
| `windows-desktop-e2e` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\windows-desktop-e2e` | E2E testing for Windows native desktop apps (WPF, WinForms, Win32/MFC, Qt) using pywinauto and Windows UI A... |
| `writing-for-agents` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\writing-for-agents` | Writing documents for agents. Use when creating or editing skills, or modifying AGENTS.md or CLAUDE.md. |
| `writing-plans` | - | 可见 | `C:\Users\CHATGPT\.agents\skills\writing-plans` | Use when you have a spec or requirements for a multi-step task, before touching code |
| `yoruba-localization-testing` | - | 可见 | `C:\Users\CHATGPT\.claude\skills\yoruba-localization-testing` | Test Yoruba (yo) and English bilingual interfaces for tone marks, underdots, Unicode normalization, transla... |

## 维护约定

1. **新增技能**: 实体放 `~/.agents/skills/<name>/`, 目录名 == frontmatter `name`;
   SkillHub 装出来的 `@<ns>/<name>` 是二级目录, 同样会被扫描, 不用再补平铺链接。
2. **改完目录必跑** `python tidy_skills.py` 与 `python verify_skills.py --write-index`。
3. **禁用态按 URI 匹配**: 实体一旦换位置, 旧的禁用条目会失效并把技能重新打开;
   本脚本会列出失效条目, 要保持禁用就改 URI 或在桌面端重新关一次。
4. **不删副本**: 冗余一律 Move 到 `~/.minimax/skills-archive/`, 可回退。

## 工具

- `tidy_skills.py` —— 目录整理(改名 / 补可见性 / 版本收敛 / 冗余归档 / 真值源归一), 幂等。
- `verify_skills.py` —— 可见性核对与本索引的重生成, 带 `--selftest`。
