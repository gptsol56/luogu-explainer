# luogu-explainer

给洛谷题目写的讲解助手。填个题号，它把题面翻成一篇能读下去的教学稿 —— 这题在考什么、怎么推到解法、代码怎么写、复杂度多少、容易错在哪，外加两道自测题。

顺手还做了个每天签到的小工具，以及这一阶段的学习笔记。

站点在这儿：<https://gptsol56.github.io/luogu-explainer/>

![网页应用界面](docs/images/web-ui.png)

（截图是 GitHub Pages 上的静态站形态, 右上角标着当前是哪种模式。）

## 三件事，各管一段

- **讲解站点** —— `web/` 和 `server/`。上面那个链接就是它。
- **打卡工具** —— `luogu_punch.py`。洛谷的连续签到，靠它保住。
- **学习笔记** —— `notes/` 五章 Markdown。第一阶段的作业，也留在这儿。

三块之间几乎不耦合。站点不依赖笔记，笔记不讲站点代码。唯一的交叉点是站点要读 `explainer/prompt_template.json`，这份文件后面单独说。

## 跑起来

```
pip install -r requirements.txt
python explainer/luogu_explainer.py --selftest
python server/app.py
```

浏览器开 <http://127.0.0.1:8848/>。默认监听 127.0.0.1，不对外网暴露。

想先看效果不配密钥，就点页面上的「看演示样例」。

## 自检

每个脚本都带 `--selftest`，不用凭据、不联网：

| 命令 | 断言数 | 查什么 |
| --- | --- | --- |
| `python luogu_punch.py --selftest` | 23 | 打卡逻辑。洛谷那个 code=201 有两种含义，不能一律当"已打卡" |
| `python -m unittest discover -s tests` | 23 | 打卡工具的单元测试 |
| `python explainer/luogu_explainer.py --selftest` | 39 | 提示词模板、模型预设表、两种接口形状的请求与解析 |
| `python tools/build_site.py --selftest` | 8 | 静态产物组装：文件齐不齐、模板能不能解析、有没有密钥字面量 |
| `python tools/check_notes_sync.py --selftest` | 5 | 笔记同步比对器：正文、图片、文件名任何一个字节不一样都要抓出来 |

这些命令存在是有原因的。工具坏掉的时候，你得能分清是环境问题还是代码问题 —— 靠肉眼看输出不行。

## 凭据

全部只从环境变量读，仓库里只有一份空的 `.env.example`：

```
LUOGU_CLIENT_ID=      # 洛谷 Cookie 里的 __client_id，抓题和打卡都要
LUOGU_UID=            # 洛谷 Cookie 里的 _uid
MINIMAX_API_KEY=      # 模型密钥
MINIMAX_BASE_URL=https://api.minimaxi.com/anthropic
MINIMAX_MODEL=MiniMax-M3.1-Flash
```

Windows 上 `setx` 只对新开的进程生效。当前进程读不到时，服务端会从注册表 `HKCU\Environment` 回退一次。

洛谷 Cookie 怎么拿：浏览器登录 luogu.com.cn，F12 → Application → Cookie → https://luogu.com.cn，`__client_id` 和 `_uid` 各一个。

## 换个模型讲

页面提交区有个「用哪个模型」下拉，现在能选：

- MiniMax（默认，Anthropic 风格）
- DeepSeek 深度求索（OpenAI 风格）
- Kimi 月之暗面（OpenAI 风格）
- 通义千问 百炼（OpenAI 风格）
- 智谱 GLM（OpenAI 风格）
- 自定义端点 —— 本机 Ollama、vLLM，或者你手里的中转地址

选完，接口地址、模型名、协议一起带出来，不想用预设就自己改。

接口就两种形状，都试过：

- Anthropic 风格：`POST {base}/v1/messages`，头 `x-api-key` + `anthropic-version`
- OpenAI 风格：`POST {base}/chat/completions`，头 `Authorization: Bearer`

每家一套环境变量。DeepSeek 要 `DEEPSEEK_API_KEY`，Kimi 要 `MOONSHOT_API_KEY`，以此类推；自建端点统一用 `LLM_API_KEY`。配了几家，页面上会一家一家标出来"服务端已配好"还是"还没配"。

想加第七家？往 `explainer/providers.json` 里加一条就行，Python 那边不用动。那份 JSON 是后端和浏览器共用的唯一真源 —— 和提示词模板一个路子，两端各写一份的话，改了一边忘了另一边，就会出现"页面上能选、服务端不认"这种错。

### 浏览器能不能直连

GitHub Pages 没有后端，带密钥模式只能让浏览器直接调模型接口。能不能调成，取决于对方给不给 CORS 头。

我拿假密钥把候选端点挨个打了一遍，只看状态码和响应头：

| 厂商 | 浏览器直连 |
| --- | --- |
| MiniMax、DeepSeek、通义千问、硅基流动 | 能 |
| Kimi、智谱、火山 Ark | 不能 |

所以选了 Kimi，页面会直接说"这家会被拦，想用就跑本机代理模式"，而不是让人填完密钥再撞一堵墙。

这是 2026-11-24 实测的，不是抄文档。厂商以后改策略，以实际为准。

## 页面怎么知道自己该干嘛

站点部署在 Pages 上没有后端，但同一个前端也想在本机跑 —— 那时能自动取题面，打卡按钮也能用。于是页面启动时先问 `/api/health`：

- 答上了 → **本机代理模式**。密钥在服务端进程环境里，浏览器碰不到任何凭据。
- 答不上 → **自带密钥模式**。密钥只写进你这台电脑的 localStorage，不经过任何服务器。
- 没密钥也能看 → **演示样例**。提交一份预先调好的讲解，页面里标明"预先生成，不是实时调用"。

想验证密钥真的没上传？看站点源码，里面只有你填进去的那一个密钥，别无其它。

## 为什么打卡没做成网页按钮

两个实测出来的原因：

1. 洛谷的题目接口要登录态。匿名 `GET /problem/P1001?_contentOnly=1` 回来的是 SPA 的 HTML 空壳，`POST /fe/api/problem/detail/P1001` 直接 403 `UserNotLoggedInException`。
2. 洛谷的响应没有 CORS 头。浏览器直连一定被跨域策略拦掉。

浏览器里放洛谷 Cookie 这条路也别想了 —— 就算放进去，CORS 那一关照样过不去。所以打卡只能在有服务端的地方做，页面上那个标签页干脆直接把命令行敲法给你：

```
python luogu_punch.py                # 打一次
python luogu_punch.py --json         # JSON 输出，脚本好接管
python luogu_punch.py --schedule     # 常驻，每天 10:00（北京时间）
scripts\install_task.ps1             # 注册成 Windows 计划任务
```

退出码：`0` 成功（含"今日已打卡"）/ `1` 打卡失败 / `2` 凭据或参数错误 / `130` 被 Ctrl+C 中断。

## 提示词只有一份

提示词模板放在 `explainer/prompt_template.json`。Python 后端读它，浏览器前端也读它。

这个是被坑过之后改的。原来两端各写一份，改了一边忘了另一边，本机看到的讲解和线上看到的就不一样，而且极难查 —— 那种问题不报错，只是悄悄不对。现在 CI 里有两条断言专门盯：`build_prompt` 不许留下没替换的占位符；模板里的 `required_sections` 必须和代码里的 `REQUIRED_SECTIONS` 是同一份定义。

固定六个小节：题目在考什么、思路推导、关键代码、复杂度、常见坑、自测题。讲解风格目前两个：面向初学者、冲刺提分。

## 接口

```
GET  /api/health             健康检查。只说"有没有密钥"，绝不返回密钥本身
GET  /api/providers          模型厂商预设表
GET  /api/problem/{pid}      抓洛谷题目
POST /api/explain            讲解。body: {pid?, text?, style?, provider?}
POST /api/punch              服务端执行一次打卡
GET  /prompt_template.json   提示词模板
```

## 笔记

三层。

**正文** `notes/` 五章，直接在 GitHub 上读，不用跑任何东西：

- [01 Git 学习记录](notes/01-Git-学习记录.md) —— 概念、合并方式、分支策略
- [02 AI Agent 学习记录](notes/02-AI-Agent-学习记录.md) —— Agent 和 LLM 的区别、六块组成、实测基线、踩的坑
- [03 提交日记 · 洛谷打卡助手](notes/03-提交日记-洛谷打卡助手.md) —— 一次真实的提交：取证 → 写 → 提交 → 验证
- [04 把仓库做成一个完整的整体](notes/04-把仓库做成一个完整的整体.md) —— 三个模块各归其位、两种部署形态
- [05 拆仓库 · 公开的站点与私有的笔记](notes/05-拆仓库-公开的站点与私有的笔记.md) —— 为什么拆、BYOK 与提示词单一真源、合并与验证

正文是**转换产物**，不是手抄的 —— 由 `docs/draft/` 里的 DOCX 转出来，没有 YAML frontmatter，也没有"本文件来自 DOCX…"这类说明行。

**原稿** `docs/draft/`：《淳阳项目组学习笔记_第一阶段_GIT_AND_AGENT.docx》，35 页。

**原始素材** `docs/source-materials/`：第一到第四天的原始笔记、前置学习任务、终端记录、版面预览。

留原始素材的理由很实在：阶段任务书要交"过程"，原始稿和成稿放在一起，以后回头看才知道哪些判断是后来改的。

### 重新生成正文

要改就改 DOCX，再重新转：

```
python tools/docx_to_md.py \
  --input "docs/draft/淳阳项目组学习笔记_第一阶段_GIT_AND_AGENT.docx" \
  --out-dir notes --split --no-copy-docx
```

转换器自带零丢失核对：段落 343/343、表格行 119/119、内嵌图 3 张，缺失 0。封面标题（DOCX 的 h1 主标题）有意不进章节正文，核对时会显式报出来，不藏着。

### 正文不会和原稿漂

CI 里有个作业专门干这事：重新转一遍，跟仓库里的 `notes/` 逐字节比。

```
python tools/check_notes_sync.py
```

少一个换行，作业就红。Markdown 不会报错，漂了肉眼看不出来，GitHub 上照常渲染 —— 所以只能让机器每次都比一遍。

## 关于姓名和学号

DOCX 原稿封面上有姓名和学号。正文瘦身成五章之后，正文里不再出现具体值。按作者要求**原样保留，没有打码**。

笔记第四章里写着"笔记含姓名与学号，所以只能放私有仓库" —— 那是当时拆仓库时的判断，为记录过程保留着。实际情况以本文件为准：笔记现在就在这个公开仓库里。

哪天想收回去，删掉 `docs/draft/` 就行。五章正文不含具体值，站点、打卡工具、转换与校验脚本都不受影响。

## 没做完的

三条，笔记第四章里也记着：

1. **真实打卡一次都没跑通。** 洛谷登录态一直没取出来，所以到现在没有过一条 `code=200` 的真实输出。工具是好的，缺凭据。
2. **填题号抓题面需要登录态。** 没 Cookie 就只能粘题面；公开站上更是只能粘，因为洛谷没有 CORS 头。
3. **演示样例是预生成的。** 它是真的调过一次模型存下来的，但模型会更新，样例就会过时。所以界面上标了"预先生成，不是实时调用"。

## 部署

**Pages**：`.github/workflows/pages.yml` 在 push 到 `main` 时自动组装发布。

组装脚本是 `tools/build_site.py`，自带校验：必需文件必须齐、模板必须能解析、**产物里不许出现任何密钥字面量**。CI 跑的是同一个脚本，所以"测的"和"发的"是同一份东西。

**Docker**：

```
docker compose up -d
```

先照 `.env.example` 建一个 `.env` 填好密钥。容器里 `LUOGUBOT_HOST=0.0.0.0`，端口 8848。

## 目录

```
luogu-explainer/
├── luogu_punch.py            每日打卡（单文件，自带 --selftest）
├── explainer/
│   ├── luogu_explainer.py    取题 / 提示词 / 调模型
│   ├── prompt_template.json  提示词唯一真源（后端与前端共用）
│   └── providers.json        模型厂商预设表（同样是真源）
├── server/app.py             API 代理层 + 静态站点（只用标准库）
├── web/                      前端单页，无构建步骤，不引 CDN
├── notes/                    学习笔记正文（五章）+ 内嵌图
├── docs/
│   ├── draft/                笔记 DOCX 原稿
│   ├── source-materials/     第一至第四天的原始素材
│   └── images/               界面截图
├── tests/                    打卡工具的单元测试
├── tools/                    站点构建、笔记转换、CI 校验脚本
├── scripts/                  计划任务安装 / 手动触发 / 启服务
├── .github/workflows/        CI 门禁与 Pages 部署
├── CONTRIBUTING.md           分支模型、提交规范、硬规矩
└── requirements.txt
```

## 提交代码

看 [CONTRIBUTING.md](CONTRIBUTING.md)。几条硬规矩：

- 凭据永远不进版本库，仓库里只留空的 `.env.example`；
- 不提交大文件、虚拟环境、缓存、第三方源码树；
- 历史不改写 —— 不 rebase 已推送的共享分支，不 force-push；
- 一次提交只做一件事；
- 推完要回读远端 tree 的 blob SHA，跟本地 `git ls-tree` 逐个对上。

最后一条不是形式主义。Git 是内容寻址的，**哈希一致才算证据** —— 命令没报错不代表推对了，多半时候要靠逐个 SHA 对上。

## 这个仓库怎么长成现在这样

一开始是三个仓库：公开的站点与代码、私有的笔记正文、私有的笔记原稿与素材。最后合成一个。

判断依据不是内容敏感度，是**访问方式**：谁能 clone、谁能访问 URL、要不要服务端。拆的时候按这个分，拆过头了也得按这个合回来。推理过程写在 notes/05。

## 许可

见 [LICENSE](LICENSE)。引用的第三方项目：

- 洛谷打卡接口的行为参考 <https://github.com/kierankihn/auto-checkin>
- 技能清单来自 <https://github.com/affaan-m/ECC>
