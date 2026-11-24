# 参与这份代码

这个仓库是个人学习项目, 但版本控制按团队标准来管 —— 因为它要当作业交, 提交记录本身就是评分的一部分。

## 分支模型

| 分支 | 用途 | 能不能直接推 |
| --- | --- | --- |
| `main` | 始终可交付, CI 必须绿 | **不允许**, 一律走 PR |
| `feat/xxx` | 新功能 (如 `feat/explainer-web`) | 可以 |
| `fix/xxx` | 修 bug | 可以 |
| `docs/xxx` | 只改文档 | 可以 |

规则:

- `main` 上禁止直接 push; 所有改动从功能分支开 PR 合入。
- 分支命名用英文小写加短横线: `feat/luogu-punch-cli`、`fix/timezone-fallback`。
- 功能分支活不过一周, 合完就删。

## 提交规范

用 Conventional Commits: `<type>(<scope>): <subject>`

| type | 什么时候用 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | 修 bug |
| `docs` | 只改文档 |
| `refactor` | 重构, 行为不变 |
| `test` | 补测试 |
| `chore` | 构建/依赖/杂项 |
| `ci` | CI 配置 |

例子:

`
feat(punch): 打卡失败时按 code+message 双重判定
fix(tz): Windows 缺 tzdata 时回退到固定 UTC+8
docs(notes): 把第三章提交日记补进学习笔记
`

subject 用中文或英文都行, 但要写清**做了什么**, 不要写"更新代码"这种。

## 提 PR 前必做

`
python luogu_punch.py --selftest          # 离线自检, 不能有失败
python -m unittest discover -s tests -v   # 单元测试
git status                                # 看清楚要提交什么
git diff --stat                           # 看清楚改了多少
`

CI 必须全绿才合。合并方式用 **Squash and merge**, 保持历史线性;
合并后把分支删掉。

## 版本控制的几条硬规矩

1. **凭据永远不进版本库。** 洛谷 Cookie 走环境变量 `LUOGU_CLIENT_ID` / `LUOGU_UID`, 
   模型密钥走环境变量或 GitHub Secrets; 仓库里只保留空的 `.env.example`。
2. **不提交虚拟环境、缓存、第三方源码树。** `.gitignore` 已覆盖 `__pycache__/`、`.venv/`、
   `node_modules/`、`.env`; 如果 `git status` 里冒出这些, 说明 `.gitignore` 被绕过了。
3. **不提交大文件。** 单文件超过 5 MB 一律走 Git LFS 或改为外链, 仓库体积要能 clone。
4. **一次提交只做一件事。** 混在一起的提交将来没法单独回滚。
5. **提交信息写"为什么", 不只写"做了什么"。** 踩坑类改动要写清根因。
6. **不 force push 到 main`。** 万一推错了用 `git revert` 追加一个新提交, 而不是改历史。
7. **打 tag 前确认 CI 绿。** 版本号用 `vX.Y.Z`, 与 README 里的用法保持一致。

## 本地与远端一致性自查

Git 是内容寻址的, 所以**哈希一致就是最强的证据**。推送后自查:

`
git rev-parse HEAD
gh api repos/gptsol56/luogu-explainer/commits/main --jq .sha
git ls-tree -r HEAD
gh api repos/gptsol56/luogu-explainer/git/trees/main --jq '.tree[].sha'
`

两条 SHA 相同说明提交到位; 远端 tree 的每个 blob SHA 与本地 `git ls-tree` 逐个一致,
才说明**服务端存的就是我本地这份内容** —— 只看 push 没报错是不够的。

## 版本号

| 版本 | 内容 |
| --- | --- |
| `v1.0.0` | 首个完整版本: 打卡工具 + 讲解模块 + 网页应用, 站点上线 |
| `v1.1.0` | 学习笔记并入本仓库: 五章正文 + DOCX 原稿 + 原始素材, 站点 / 打卡 / 笔记合并为一个仓库 |
