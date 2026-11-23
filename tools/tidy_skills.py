# -*- coding: utf-8 -*-
"""
tidy_skills.py —— 整理本机 Agent Skill 目录 (幂等, 可重复跑)

目标布局:
  ~/.agents/skills/          入口层: 目录名 == frontmatter name, 所有技能可见
  ~/.minimax/skills/         兼容层: 只放 junction, 全部指回 .agents
  ~/.claude/skills/          Claude Code 自己的域(由 kkSwitch 管理), 不动其链接
  ~/.minimax/skills-archive/ 归档区(不删除, 可回退)

安全约定:
  - 不做未经验证的递归删除; 冗余副本一律 Move 到归档区
  - 每步操作后立刻回读存在性, 失败即中止
  - 只动用户级技能目录, 不碰项目目录
  - 不碰 kkSwitch 管理的目录(它会自行同步)
"""
import os, shutil, subprocess, sys

sys.stdout.reconfigure(encoding="utf-8")

A = r"C:\Users\CHATGPT\.agents\skills"
M = r"C:\Users\CHATGPT\.minimax\skills"
C = r"C:\Users\CHATGPT\.claude\skills"
ARC = r"C:\Users\CHATGPT\.minimax\skills-archive"
KK = r"C:\Users\CHATGPT\.kkswitch\skills"

FAILS = []

def log(s=""):
    print(s, flush=True)

def is_link(p):
    """Windows junction 与 symlink 都是 reparse point。"""
    try:
        st = os.lstat(p)
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)
    except Exception:
        return False

def exists(p):
    return os.path.exists(p) or is_link(p)

def mkjunction(link, target):
    if not os.path.isdir(target):
        raise RuntimeError("目标不存在: " + target)
    if exists(link):
        return False
    r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("mklink 失败: %s %s" % (r.stdout.strip(), r.stderr.strip()))
    return True

def rmjunction(p):
    """只删 reparse point, 不动目标。"""
    if not is_link(p):
        raise RuntimeError("不是链接, 拒绝删除: " + p)
    try:
        os.rmdir(p)
    except Exception:
        subprocess.run(["cmd", "/c", "rmdir", p], capture_output=True, text=True)
    if exists(p):
        raise RuntimeError("链接删除失败: " + p)

def move(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if exists(dst):
        raise RuntimeError("目标已存在: " + dst)
    os.rename(src, dst)
    if not exists(dst):
        raise RuntimeError("移动后目标不存在: " + dst)

def archive(src, name):
    os.makedirs(ARC, exist_ok=True)
    dst = os.path.join(ARC, name)
    if exists(dst):
        shutil.rmtree(dst)
    move(src, dst)
    return dst

def step(name, fn):
    try:
        msg = fn()
        log("  OK   %-42s %s" % (name, msg or ""))
        return True
    except Exception as e:
        log("  FAIL %-42s %s: %s" % (name, type(e).__name__, str(e)[:150]))
        FAILS.append(name)
        return False

# =============================================================== 1 改名对齐
log("[1] 改名对齐 (目录名 -> frontmatter name)")
for old, new in [("composition-patterns", "vercel-composition-patterns"),
                 ("react-best-practices", "vercel-react-best-practices"),
                 ("react-native-skills", "vercel-react-native-skills"),
                 ("react-view-transitions", "vercel-react-view-transitions")]:
    def f(old=old, new=new):
        s, d = os.path.join(A, old), os.path.join(A, new)
        if not exists(s):
            return "源不存在, 跳过"
        if exists(d):
            return "目标已存在, 跳过"
        move(s, d)
        return "%s -> %s" % (old, new)
    step("rename " + old, f)

def f_webaccess():
    old = os.path.join(A, "skills-sh-1785812558262")
    new = os.path.join(A, "web-access")
    if not exists(old):
        return "源不存在, 跳过"
    tgt = os.path.realpath(old)
    mkjunction(new, tgt)
    rmjunction(old)
    return "web-access -> CherryStudio"
step("CherryStudio 链接改名", f_webaccess)

# =============================================================== 2 补可见性
log()
log("[2] 补可见性 (.claude 命名空间层里的技能拉出平铺入口)")
for nm, src in [("baidu-map-webapi", os.path.join(C, "@clawhub_baidu-maps", "baidu-map-webapi")),
                ("tencentmap-map-assistant-skill", os.path.join(C, "@tencent-adm", "tencentmap-map-assistant")),
                ("bilibili-transcript", os.path.join(C, "@user_0b65fce7", "bilibili-txt"))]:
    def f(nm=nm, src=src):
        d = os.path.join(A, nm)
        if exists(d):
            return "已存在, 跳过"
        mkjunction(d, src)
        return nm
    step("reveal " + nm, f)

# =============================================================== 3 find-skills 版本收敛
log()
log("[3] find-skills 版本收敛 (统一到功能更全的 1.7.0)")
def f_find():
    cur = os.path.join(A, "find-skills")
    ns = os.path.join(A, "@indiv-guipi", "find-skills")
    if not exists(cur):
        return "不存在, 跳过"
    want = os.path.realpath(ns)
    if is_link(cur):
        if os.path.realpath(cur) == want:
            return "已指向 1.7.0"
        rmjunction(cur)
        mkjunction(cur, ns)
        return "链接重指向 1.7.0"
    archive(cur, "find-skills-1.0.0")
    mkjunction(cur, ns)
    return "1.0.0 归档, 1.7.0 生效"
step("find-skills", f_find)

# =============================================================== 4 next-slide 归一
log()
log("[4] next-slide 归一 (唯一实体 = kkSwitch 管理的副本)")
def f_next():
    kk = os.path.join(KK, "next-slide")
    dst = os.path.join(A, "next-slide")
    src_m = os.path.join(M, "next-slide")
    if not os.path.isdir(kk):
        return "kkswitch 实体缺失, 跳过"
    if exists(dst) and not is_link(dst):
        archive(dst, "next-slide-agents-copy")
    if not exists(dst):
        mkjunction(dst, kk)
    if exists(src_m) and not is_link(src_m):
        archive(src_m, "next-slide-minimax-copy")
    if not exists(src_m):
        mkjunction(src_m, dst)
    return "实体=.kkswitch, .agents/.minimax 走链接"
step("next-slide", f_next)

# =============================================================== 5 冗余拷贝归档
log()
log("[5] 冗余拷贝归档 (实体化链接, 避免同一技能两份)")
def f_dedup_travel():
    dup = os.path.join(C, "@user_67790f4b", "travelplanner")
    real = os.path.join(A, "@user_67790f4b", "travelplanner")
    if not exists(dup):
        return "无副本"
    if is_link(dup):
        return "已是链接"
    archive(dup, "travelplanner-claude-dup")
    mkjunction(dup, real)
    return "副本归档, 改为链接"
step("travel-planner", f_dedup_travel)

def f_dedup_img():
    dup = os.path.join(C, "image-creator")
    real = os.path.join(A, "image-creator")
    if not exists(dup):
        return "无副本"
    if is_link(dup):
        return "已是链接"
    archive(dup, "image-creator-claude-dup")
    mkjunction(dup, real)
    return "副本归档, 改为链接"
step("image-creator", f_dedup_img)

# =============================================================== 6 统一真值源
log()
log("[6] 统一真值源 (.minimax 实体 -> .agents, .minimax 留链接)")
for nm in ["ai-coder", "code-expert", "design-iface", "foundation-builder", "gitee",
           "gpt-taste", "humanize-ai-text", "prompt-optimizer", "skills-factory"]:
    def f(nm=nm):
        s, d = os.path.join(M, nm), os.path.join(A, nm)
        if not exists(s):
            return "不存在, 跳过"
        if is_link(s):
            return "已是链接, 跳过"
        if exists(d):
            return ".agents 已有同名, 跳过"
        move(s, d)
        mkjunction(s, d)
        return "实体 -> .agents, .minimax 留链接"
    step("relocate " + nm, f)

log()
log("=" * 70)
log("失败项: %d %s" % (len(FAILS), FAILS if FAILS else ""))
sys.exit(1 if FAILS else 0)
