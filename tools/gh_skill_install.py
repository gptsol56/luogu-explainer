# -*- coding: utf-8 -*-
"""
gh_skill_install.py —— 从 GitHub 装 Agent Skill (绕过被墙的 git clone)

为什么不用 git clone / npx skills:
  本机实测 github.com:443 被重置 (WinError 10054 / curl 28),
  git clone 与 npx skills add 都失败; 但 api.github.com 的 tarball
  通道可用 (重定向到 codeload.github.com 能通), 所以走这条路。

三个必须处理的现实问题:
  1. 同一个技能可能在一个仓库里存多份 (impeccable 在 22 个 agent 目录各存一份),
     所以按 **frontmatter name** 去重, 再按优先级挑一份:
     .agents/skills/<name> > .claude/skills/<name> > 顶层 <name> > 其它
  2. 本机已装的技能不能被静默覆盖 (默认跳过, --force 才覆盖)
  3. 装之前先报出该技能带不带脚本, 让你能自己判断要不要装

用法:
  python gh_skill_install.py --repo anthropics/skills --list-only
  python gh_skill_install.py --repo obra/superpowers --only systematic-debugging,verification-before-completion
  python gh_skill_install.py --repo pbakaus/impeccable --dry-run
  python gh_skill_install.py --repo obra/superpowers        # 装到 ~/.agents/skills
"""
import argparse, gzip, io, json, os, re, shutil, sys, tarfile, tempfile, time, urllib.request

UA = "mavis-skill-installer"
sys.stdout.reconfigure(encoding="utf-8")
HOME = os.path.expanduser("~")
DEFAULT_DEST = os.path.join(HOME, ".agents", "skills")
SCRIPT_EXT = (".py", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".js", ".mjs", ".cjs", ".ts", ".rb", ".go", ".exe")


def fetch_tarball(repo, ref="main", retries=3):
    url = "https://api.github.com/repos/%s/tarball/%s" % (repo, ref)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
            data = urllib.request.urlopen(req, timeout=180).read()
            return data
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError("tarball 拉取失败: %s: %s" % (type(last).__name__, str(last)[:120]))


def open_tar(data):
    """解压一次再用 "r:" 随机读。

    直接用 "r:gz" 的话, 每读一个 SKILL.md 都要从 gzip 流的起点重新解压一遍
    (GzipFile.seek 永远先回卷), 几百个技能目录就能跑到分钟级超时。
    先整体解压成普通 tar, seek 才是 O(1)。
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
    try:
        with gzip.open(io.BytesIO(data), "rb") as gz:
            while True:
                chunk = gz.read(1 << 20)
                if not chunk:
                    break
                tmp.write(chunk)
        tmp.close()
        return tarfile.open(name=tmp.name, mode="r:"), tmp.name
    except Exception:
        tmp.close()
        raise


def tar_root(tf):
    for m in tf.getmembers():
        p = m.name.split("/")
        if len(p) >= 2:
            return p[0]
    return ""


SKIP_DIRS = {"tests", "test", "fixtures", "fixture", "node_modules", "vendor",
             "examples", "example", "samples", "sample", "playground", "sandbox",
             "benchmarks", "benchmark", "e2e", "__tests__"}
# 多语言文档副本 (docs/zh-CN/skills/x, docs/ja-JP/skills/x ...) —— 不是要装的东西
I18N_DOC = re.compile(r"(^|/)docs/[a-z]{2}(-[a-zA-Z]{2})?(/|$)", re.I)


def is_skippable(d, parts):
    if any(p.lower() in SKIP_DIRS for p in parts):
        return True
    # I18N_DOC 必须对整条路径判定: 单独一个路径段 "docs" 匹配不上 "docs/xx/"
    if I18N_DOC.search(d):
        return True
    return False


def skill_dirs(tf, root):
    """含 SKILL.md 的目录; 排除测试夹具/示例目录, 以及过小的占位 SKILL.md。"""
    out = []
    for m in tf.getmembers():
        if not m.name.endswith("/SKILL.md"):
            continue
        rel = m.name[len(root) + 1:] if root and m.name.startswith(root + "/") else m.name
        d = rel.rsplit("/", 1)[0]
        parts = d.split("/")
        if is_skippable(d, parts):
            continue
        if m.size < 200:
            continue
        out.append(d)
    return sorted(set(out))


def read_front_name(tf, d, root):
    full = (root + "/" + d if root else d) + "/SKILL.md"
    try:
        f = tf.extractfile(full)
        head = f.read(3000).decode("utf-8", "replace")
        m = re.search(r"^name:\s*(.+?)\s*$", head, re.M)
        return m.group(1).strip().strip('"\'') if m else d.split("/")[-1]
    except Exception:
        return d.split("/")[-1]


def dir_rank(d):
    """挑副本的优先级: .agents > .claude > 顶层 > 其它; 同级取路径短的。"""
    parts = d.split("/")
    for i in range(len(parts) - 2):
        if parts[i + 1] == "skills":
            agent = parts[i]
            base = {".agents": 0, ".claude": 1}.get(agent, 3)
            return (base, len(parts))
    if len(parts) == 1:
        return (2, len(parts))
    if len(parts) == 2 and parts[1] == "skills":
        return (2, len(parts))
    return (4, len(parts))


def list_scripts(tf, d, root):
    prefix = (root + "/" + d if root else d) + "/"
    out = []
    for m in tf.getmembers():
        if not m.name.startswith(prefix):
            continue
        rel = m.name[len(prefix):]
        if "/" in rel:
            continue
        if rel.lower().endswith(SCRIPT_EXT):
            out.append(rel)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--ref", default="main")
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--only", default="", help="逗号分隔的 skill 名白名单")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    print("[1/4] 拉取 tarball: %s@%s" % (a.repo, a.ref))
    data = fetch_tarball(a.repo, a.ref)
    tf, tar_tmp = open_tar(data)
    root = tar_root(tf)
    dirs = skill_dirs(tf, root)
    print("      %d bytes, %d 个技能目录, 根 %s" % (len(data), len(dirs), root))

    # 按 frontmatter name 归组, 组内按优先级挑一份
    groups = {}
    for d in dirs:
        nm = read_front_name(tf, d, root)
        groups.setdefault(nm, []).append(d)
    picked = {nm: sorted(ds, key=lambda d: (dir_rank(d), d))[0] for nm, ds in groups.items()}
    collapsed = sum(len(ds) - 1 for ds in groups.values())
    print("[2/4] 去重后 %d 个唯一技能 (合并掉 %d 份重复副本, 已排除测试夹具与示例目录)" % (len(picked), collapsed))

    only = set(x.strip() for x in a.only.split(",") if x.strip())
    plan = []
    for nm, d in picked.items():
        if only and nm not in only and d.split("/")[-1] not in only:
            continue
        plan.append((nm, d))
    plan.sort()
    print("      命中 %d 个技能" % len(plan))

    if a.list_only:
        for nm, d in plan:
            sc = list_scripts(tf, d, root)
            print("      - %-38s <- %s%s" % (nm, d, ("   [脚本: " + ",".join(sc) + "]") if sc else ""))
        return

    os.makedirs(a.dest, exist_ok=True)
    installed, skipped, dupnote = [], [], []
    print("[3/4] 安装到 %s" % a.dest)
    for nm, d in plan:
        if len(groups[nm]) > 1:
            dupnote.append("%s(%d份副本, 取 %s)" % (nm, len(groups[nm]), d))
        target = os.path.join(a.dest, nm)
        if os.path.exists(target):
            if not a.force:
                skipped.append(nm)
                print("      = %-38s 已存在, 跳过" % nm)
                continue
            shutil.rmtree(target)
        sc = list_scripts(tf, d, root)
        if sc:
            print("      ! %-38s 含脚本: %s" % (nm, ",".join(sc)))
        if a.dry_run:
            print("      ~ %-38s (dry-run, 未写入)" % nm)
            continue
        # 原子写入: 先解到临时目录, 全部成功再改名; 中途失败不留半个技能
        tmp = target + ".installing"
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        os.makedirs(tmp, exist_ok=True)
        n = 0
        prefix = (root + "/" + d if root else d) + "/"
        try:
            for m in tf.getmembers():
                if not m.name.startswith(prefix):
                    continue
                rel = m.name[len(prefix):]
                if not rel or rel.startswith("/"):
                    continue
                m.name = rel
                try:
                    tf.extract(m, tmp, filter="data")
                except TypeError:
                    tf.extract(m, tmp)
                n += 1
            if os.path.exists(target):
                shutil.rmtree(target)
            os.rename(tmp, target)
        except Exception as e:
            if os.path.exists(tmp):
                shutil.rmtree(tmp, ignore_errors=True)
            print("      ! %-38s 安装失败已回滚: %s" % (nm, e))
            continue
        installed.append((nm, n))
        print("      + %-38s (%d 文件)" % (nm, n))

    print("[4/4] 完成: 新装 %d, 跳过已存在 %d" % (len(installed), len(skipped)))
    if skipped:
        print("      跳过: " + ", ".join(skipped) + "   (加 --force 可覆盖)")
    if dupnote:
        print("      副本合并: " + "; ".join(dupnote))
    try:
        os.remove(tar_tmp)
    except Exception:
        pass


if __name__ == "__main__":
    main()
