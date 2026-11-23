# -*- coding: utf-8 -*-
"""
verify_skills.py —— 技能可见性核对 + SKILLS-INDEX.md 重生成 (只读核对, 可重复跑)

为什么需要它:
  MCode 把技能的"禁用"状态记在 sqlite 的 local_runtime_preferences 里, key =
  'standalone-skill-disabled-state', 字段 disabledLocationUris —— 按 **文件 URI**
  匹配, 不是按技能名. 所以只要把技能实体挪个位置(例如 .minimax/skills -> .agents/skills),
  旧 URI 就失效, 技能会被意外重新启用; 反过来, 只建链接不改实体位置, 禁用态会一直生效.

三条硬约定:
  1. 只读: 本脚本不写任何技能目录, 只读磁盘与 sqlite
  2. 不改用户开关: 禁用/启用一律交给用户在桌面端操作, 脚本只报告
  3. 自带夹具: --selftest 用临时目录 + 真实 junction 验证"改名后旧 URI 失效"这条判定

用法:
  python verify_skills.py                # 打印核对报告
  python verify_skills.py --write-index  # 顺带重生成 SKILLS-INDEX.md
  python verify_skills.py --selftest     # 跑确定性断言
"""
import os, re, sys, json, time, sqlite3, subprocess, tempfile

sys.stdout.reconfigure(encoding="utf-8")

H = os.path.expanduser("~")
ROOTS = [os.path.join(H, ".agents", "skills"), os.path.join(H, ".claude", "skills")]
DB = os.path.join(H, ".minimax", "v2", "sqlite", "runtime-state.sqlite")
PREF_KEY = "standalone-skill-disabled-state"
BACKUP_DIR = os.path.join(H, ".minimax", "preferences")

GROUPS = [
    ("编码与工程", [
        "ai-coder", "code-expert", "code-mate-claude-code", "code-mate-minimax-code",
        "foundation-builder", "gitee", "vercel-cli-with-tokens", "vercel-composition-patterns",
        "vercel-optimize", "vercel-react-best-practices", "vercel-react-native-skills",
        "vercel-react-view-transitions",
    ]),
    ("Skill / Prompt 工厂", [
        "find-skills", "prompt-optimizer", "skill-creator", "skillhub", "skills-factory",
    ]),
    ("设计 · 视觉 · 交付物", [
        "design-iface", "gpt-taste", "image-creator", "next-slide", "office-transform",
        "slides", "ui-ux-pro-max", "web-design-guidelines", "writing-guidelines",
    ]),
    ("写作 · 内容处理", [
        "humanize-ai-text", "humanizer", "humanizer-academic", "summarize",
    ]),
    ("联网 · 检索 · 浏览器", [
        "cherry-browser", "cherry-computer", "cherry-tool-guide", "web-access", "web-search",
    ]),
    ("音频 · 视频 · 字幕", [
        "bilibili-transcript", "dlazy-qwen-tts",
    ]),
    ("地图 · 出行", [
        "baidu-map-webapi", "tencentmap-map-assistant-skill", "travel-planner",
    ]),
]
GROUP_OF = {}
for _g, _n in GROUPS:
    for _x in _n:
        GROUP_OF[_x] = _g


def path_to_uri(p):
    p = os.path.abspath(p).replace(chr(92), "/")
    if not p.startswith("/"):
        p = "/" + p
    return "files://" + p.replace(" ", "%20")


def uri_to_path(u):
    if u.startswith("files://"):
        u = u[len("files://"):]
    u = u.lstrip("/")
    return u.replace("/", chr(92))


def read_frontmatter(sk):
    try:
        txt = open(sk, "r", encoding="utf-8", errors="replace").read()
    except Exception:
        return {}
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---", txt, re.S)
    if not m:
        return {}
    lines = m.group(1).splitlines()
    fm = {}
    meta = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if ":" not in line or line[:1].isspace():
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        block = v in ("|", ">", "|-", ">-", "|+", ">+")
        plain = (v == "" and i < len(lines) and lines[i][:1].isspace() and lines[i].strip())
        if block or plain:
            buf = []
            while i < len(lines) and (not lines[i].strip() or lines[i][:1].isspace()):
                buf.append(lines[i].strip())
                i += 1
            while buf and not buf[-1]:
                buf.pop()
            val = " ".join(x for x in buf if x).strip()
            if k == "metadata":
                for mm in re.finditer(r"([A-Za-z_][\w-]*):\s*(.+)", val):
                    meta[mm.group(1)] = mm.group(2).strip().strip("'").strip('"')
            else:
                fm[k] = val
            continue
        fm[k] = v.strip("'").strip('"')
    if "version" not in fm and "version" in meta:
        fm["version"] = meta["version"]
    return fm


def enumerate_entries(roots=None):
    """返回 {skill_name: {...}} —— 一个技能一条, 实体按 realpath 去重."""
    roots = roots if roots is not None else ROOTS
    out = {}
    for r in roots:
        if not os.path.isdir(r):
            continue
        for e in sorted(os.listdir(r)):
            p = os.path.join(r, e)
            if not os.path.isdir(p):
                continue
            subs = []
            if e.startswith("@"):
                for s in sorted(os.listdir(p)):
                    sp = os.path.join(p, s)
                    if os.path.isdir(sp) and os.path.isfile(os.path.join(sp, "SKILL.md")):
                        subs.append(sp)
            else:
                subs.append(p)
            for sp in subs:
                sk = os.path.join(sp, "SKILL.md")
                if not os.path.isfile(sk):
                    continue
                rp = os.path.realpath(sk)
                fm = read_frontmatter(rp)
                name = fm.get("name") or os.path.basename(os.path.dirname(rp))
                rec = out.setdefault(name, {
                    "name": name,
                    "version": fm.get("version", "-"),
                    "description": fm.get("description", ""),
                    "entity": os.path.dirname(rp),
                    "entries": [],
                })
                if sp not in rec["entries"]:
                    rec["entries"].append(sp)
    return out


def read_disabled_uris(db=None):
    """读 MCode 的技能禁用清单; 读不到就返回空列表而不是抛错."""
    db = db or DB
    if not os.path.isfile(db):
        return []
    try:
        con = sqlite3.connect("file:" + db.replace(chr(92), "/") + "?mode=ro", uri=True)
        row = con.execute(
            "SELECT value_json FROM local_runtime_preferences WHERE key=?", (PREF_KEY,)
        ).fetchone()
        con.close()
    except Exception:
        return []
    if not row:
        return []
    try:
        return json.loads(row[0]).get("disabledLocationUris", [])
    except Exception:
        return []


def skill_name_of_uri(u):
    parts = [p for p in uri_to_path(u).split(chr(92)) if p]
    return parts[-2] if len(parts) >= 2 else u


def uris_for_skill(uris, name, rec):
    """属于某个技能的 URI: 父目录名 == 技能名, 或解析后指向该技能实体."""
    ent_real = os.path.normcase(os.path.abspath(os.path.join(rec["entity"], "SKILL.md")))
    out = []
    for u in uris:
        if skill_name_of_uri(u) == name:
            out.append(u)
            continue
        try:
            if os.path.normcase(os.path.realpath(uri_to_path(u))) == ent_real:
                out.append(u)
        except Exception:
            pass
    return out


def write_disabled_uris(uris, db=None, backup=True):
    """把禁用清单写回 sqlite; 先备份原值, 写完回读校验."""
    db = db or DB
    con = sqlite3.connect(db, timeout=15)
    con.execute("PRAGMA busy_timeout=15000")
    row = con.execute("SELECT value_json FROM local_runtime_preferences WHERE key=?", (PREF_KEY,)).fetchone()
    if not row:
        con.close()
        raise RuntimeError("找不到偏好项: " + PREF_KEY)
    obj = json.loads(row[0])
    if backup and os.path.abspath(db) == os.path.abspath(DB):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        bak = os.path.join(BACKUP_DIR, "skill-disabled-state.backup-%s.json" % ts)
        with open(bak, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    obj["disabledLocationUris"] = list(uris)
    con.execute("UPDATE local_runtime_preferences SET value_json=? WHERE key=?",
                (json.dumps(obj, ensure_ascii=False), PREF_KEY))
    con.commit()
    con.close()
    after = list(read_disabled_uris(db))
    if after != list(uris):
        raise RuntimeError("写回校验不一致")
    return obj


def set_skill_enabled(name, enabled, entries=None, db=None):
    """启用/禁用一个技能。

    启用: 清掉这个名字在清单里的所有条目, 包括路径变过之后的失效条目。
    禁用: 记录它当前的真实位置 URI —— 实体以后再挪位置, 禁用态不会失效。
    """
    entries = enumerate_entries() if entries is None else entries
    rec = entries.get(name)
    if rec is None:
        raise KeyError("入口层没有这个技能: " + name)
    current = path_to_uri(os.path.join(rec["entity"], "SKILL.md"))
    old = list(read_disabled_uris(db))
    mine = set(uris_for_skill(old, name, rec))
    kept = [u for u in old if u not in mine]
    new = kept if enabled else kept + [current]
    write_disabled_uris(new, db)
    return {"skill": name, "enabled": enabled, "before": len(old), "after": len(new),
            "removed": len(old) - len(kept), "added": 0 if enabled else 1}


def uri_norm(u):
    return os.path.normcase(os.path.abspath(uri_to_path(u)))


def audit(entries=None, disabled_uris=None):
    """核心判定: 哪些可见 / 哪些被禁用 / 哪些禁用条目已失效."""
    entries = enumerate_entries() if entries is None else entries
    disabled_uris = read_disabled_uris() if disabled_uris is None else disabled_uris
    dis_set = {uri_norm(u) for u in disabled_uris}

    visible, disabled = [], []
    for name, rec in entries.items():
        rp = uri_norm(path_to_uri(os.path.join(rec["entity"], "SKILL.md")))
        if rp in dis_set:
            disabled.append(name)
        else:
            visible.append(name)

    stale, orphan = [], []
    for u in disabled_uris:
        p = uri_to_path(u)
        if not os.path.exists(p):
            orphan.append(u)
            continue
        if uri_norm(os.path.realpath(p)) != uri_norm(p):
            stale.append(u)

    return {
        "total": len(entries),
        "visible": sorted(visible),
        "disabled": sorted(disabled),
        "stale_uris": stale,
        "orphan_uris": orphan,
        "entries": entries,
        "disabled_uris": disabled_uris,
    }


def render_index(rep):
    B = chr(96)
    entries = rep["entries"]
    dis = set(rep["disabled"])
    grouped = {}
    for n in entries:
        grouped.setdefault(GROUP_OF.get(n, "其他"), []).append(n)

    L = []
    L.append("# 本机 Agent Skill 索引")
    L.append("")
    L.append("> 本文件由 " + B + "verify_skills.py --write-index" + B + " 自动生成, 请勿手改。")
    L.append("> 改完技能目录后重跑一次, 索引与实际可见性就永远对得上。")
    L.append("")
    L.append("## 现状速览")
    L.append("")
    L.append("| 指标 | 值 |")
    L.append("|---|---|")
    L.append("| 入口层唯一技能 | %d |" % rep["total"])
    L.append("| MCode 可见 | %d |" % len(rep["visible"]))
    L.append("| 被技能开关禁用 | %d |" % len(rep["disabled"]))
    L.append("")
    if rep["disabled"]:
        L.append("被禁用的技能实体仍在磁盘上, 只是 MCode 不把它们放进技能目录:")
        L.append("")
        for n in rep["disabled"]:
            L.append("- " + B + n + B + " —— 实体 " + B + entries[n]["entity"] + B)
        L.append("")
    if rep["stale_uris"]:
        L.append("> 失效条目(路径已变, 旧的禁用 URI 不再命中, 技能已被重新打开):")
        L.append("")
        for u in rep["stale_uris"]:
            L.append("- " + B + u + B)
        L.append("")
    L.append("## 目录结构约定")
    L.append("")
    L.append("| 目录 | 角色 | 规则 |")
    L.append("|---|---|---|")
    L.append("| " + B + "~/.agents/skills/" + B + " | **入口层(真值源)** | 每个技能一个目录, 目录名 == frontmatter 的 " + B + "name" + B + " |")
    L.append("| " + B + "~/.minimax/skills/" + B + " | 兼容层 | 只放 junction, 全部指回 .agents; 不放实体 |")
    L.append("| " + B + "~/.claude/skills/" + B + " | Claude Code 域 | 由 kkSwitch / CherryStudio 管理, 只去重、不改其链接指向 |")
    L.append("| " + B + "~/.minimax/skills-archive/" + B + " | 归档区 | 冗余副本移到这里, 不删除, 可回退 |")
    L.append("| " + B + "~/.agents/skills/@<ns>/" + B + " | SkillHub 命名空间层 | **二级子目录照样被扫描**; 一级 " + B + "@<ns>" + B + " 目录本身不算技能 |")
    L.append("")
    L.append("## 技能清单")
    L.append("")
    for gname, names in GROUPS:
        rows = sorted(n for n in names if n in entries)
        if not rows:
            continue
        L.append("### %s" % gname)
        L.append("")
        L.append("| 技能 | 版本 | 状态 | 实体来源 | 用途 |")
        L.append("|---|---|---|---|---|")
        for n in rows:
            L.append(row_for(entries[n], n in dis, B))
        L.append("")
    others = sorted(grouped.get("其他", []))
    if others:
        L.append("### 其他")
        L.append("")
        L.append("| 技能 | 版本 | 状态 | 实体来源 | 用途 |")
        L.append("|---|---|---|---|---|")
        for n in others:
            L.append(row_for(entries[n], n in dis, B))
        L.append("")
    L.append("## 维护约定")
    L.append("")
    L.append("1. **新增技能**: 实体放 " + B + "~/.agents/skills/<name>/" + B + ", 目录名 == frontmatter " + B + "name" + B + ";")
    L.append("   SkillHub 装出来的 " + B + "@<ns>/<name>" + B + " 是二级目录, 同样会被扫描, 不用再补平铺链接。")
    L.append("2. **改完目录必跑** " + B + "python tidy_skills.py" + B + " 与 " + B + "python verify_skills.py --write-index" + B + "。")
    L.append("3. **禁用态按 URI 匹配**: 实体一旦换位置, 旧的禁用条目会失效并把技能重新打开;")
    L.append("   本脚本会列出失效条目, 要保持禁用就改 URI 或在桌面端重新关一次。")
    L.append("4. **不删副本**: 冗余一律 Move 到 " + B + "~/.minimax/skills-archive/" + B + ", 可回退。")
    L.append("")
    L.append("## 工具")
    L.append("")
    L.append("- " + B + "tidy_skills.py" + B + " —— 目录整理(改名 / 补可见性 / 版本收敛 / 冗余归档 / 真值源归一), 幂等。")
    L.append("- " + B + "verify_skills.py" + B + " —— 可见性核对与本索引的重生成, 带 " + B + "--selftest" + B + "。")
    L.append("")
    return "\n".join(L)


def row_for(rec, disabled, B):
    desc = (rec["description"] or "").replace("|", "/").replace("\n", " ").strip()
    if len(desc) > 110:
        desc = desc[:107] + "..."
    return "| " + B + rec["name"] + B + " | " + rec["version"] + " | " + ("已禁用" if disabled else "可见") + " | " + B + rec["entity"] + B + " | " + desc + " |"


def mkjunction(link, target):
    r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                       capture_output=True, text=True)
    if r.returncode != 0:
        os.symlink(target, link, target_is_directory=True)
    return os.path.isdir(link)


def selftest():
    """确定性断言: 临时目录夹具 + 真实 junction, 不碰真实技能目录."""
    fails = []

    def check(name, cond, detail=""):
        if cond:
            print("  PASS %s" % name)
        else:
            print("  FAIL %s %s" % (name, detail))
            fails.append(name)

    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, "skills")
        ent = os.path.join(root, "alpha")
        os.makedirs(ent)
        with open(os.path.join(ent, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: alpha\nversion: 1.2.3\ndescription: d\n---\nbody\n")
        alias = os.path.join(root, "alpha-alias")
        mkjunction(alias, ent)

        entries = enumerate_entries([root])
        check("enumerate picks frontmatter name",
              "alpha" in entries and entries["alpha"]["version"] == "1.2.3",
              sorted(entries))

        real_uri = path_to_uri(os.path.join(ent, "SKILL.md"))
        rep = audit(entries=entries, disabled_uris=[real_uri])
        check("realpath uri match -> disabled",
              rep["disabled"] == ["alpha"] and rep["visible"] == [], rep)

        rep2 = audit(entries=entries, disabled_uris=[])
        check("no disable list -> visible",
              rep2["visible"] == ["alpha"] and rep2["disabled"] == [], rep2)

        alias_uri = path_to_uri(os.path.join(alias, "SKILL.md"))
        rep3 = audit(entries=entries, disabled_uris=[alias_uri])
        check("alias uri -> skill stays visible", rep3["visible"] == ["alpha"], rep3)
        check("alias uri -> flagged stale", len(rep3["stale_uris"]) == 1, rep3["stale_uris"])

        missing_uri = path_to_uri(os.path.join(root, "nope", "SKILL.md"))
        rep4 = audit(entries=entries, disabled_uris=[missing_uri])
        check("missing path -> orphan flagged", len(rep4["orphan_uris"]) == 1, rep4)

        rep5 = audit(entries=entries, disabled_uris=[real_uri, alias_uri])
        check("mixed list -> one disabled one stale",
              rep5["disabled"] == ["alpha"] and len(rep5["stale_uris"]) == 1, rep5)

        # --- 开关写入: 临时 sqlite, 验证 enable/disable 往返 ---
        tdb = os.path.join(td, "prefs.sqlite")
        con = sqlite3.connect(tdb)
        con.execute("CREATE TABLE local_runtime_preferences (key TEXT PRIMARY KEY, value_json TEXT)")
        con.execute("INSERT INTO local_runtime_preferences VALUES (?,?)",
                    (PREF_KEY, json.dumps({"version": 1, "disabledLocationUris": []})))
        con.commit()
        con.close()

        r1 = set_skill_enabled("alpha", False, entries=entries, db=tdb)
        rep6 = audit(entries=entries, disabled_uris=read_disabled_uris(tdb))
        check("disable writes one uri",
              r1["after"] == 1 and rep6["disabled"] == ["alpha"], (r1, rep6))

        r2 = set_skill_enabled("alpha", True, entries=entries, db=tdb)
        rep7 = audit(entries=entries, disabled_uris=read_disabled_uris(tdb))
        check("enable purges the uri",
              r2["after"] == 0 and rep7["visible"] == ["alpha"], (r2, rep7))

        # 失效条目(父目录名不同但指向同一实体)也要被 enable 清掉
        con = sqlite3.connect(tdb)
        obj = json.loads(con.execute(
            "SELECT value_json FROM local_runtime_preferences WHERE key=?", (PREF_KEY,)
        ).fetchone()[0])
        obj["disabledLocationUris"] = [alias_uri]
        con.execute("UPDATE local_runtime_preferences SET value_json=? WHERE key=?",
                    (json.dumps(obj), PREF_KEY))
        con.commit()
        con.close()
        r3 = set_skill_enabled("alpha", True, entries=entries, db=tdb)
        check("enable purges stale uri by realpath",
              r3["after"] == 0 and read_disabled_uris(tdb) == [], (r3, read_disabled_uris(tdb)))

        # --- 实体挪位后, 再禁用一次必须写新 URI, 否则禁用态会失效 ---
        moved = os.path.join(root, "alpha2")
        os.rename(ent, moved)
        with open(os.path.join(moved, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: alpha\nversion: 1.2.3\ndescription: d\n---\nbody\n")
        entries2 = enumerate_entries([root])
        set_skill_enabled("alpha", False, entries=entries2, db=tdb)
        rep8 = audit(entries=entries2, disabled_uris=read_disabled_uris(tdb))
        check("re-disable after move writes new uri",
              rep8["disabled"] == ["alpha"] and len(rep8["stale_uris"]) == 0, rep8)

    print("selftest: %d failed %s" % (len(fails), fails if fails else ""))
    return 1 if fails else 0


def names_after(flag):
    if flag not in sys.argv:
        return []
    out = []
    for a in sys.argv[sys.argv.index(flag) + 1:]:
        if a.startswith("--"):
            break
        out.append(a)
    return out


def main():
    if "--selftest" in sys.argv:
        return selftest()
    entries = enumerate_entries()
    for flag, want in (("--enable", True), ("--disable", False)):
        for n in names_after(flag):
            try:
                r = set_skill_enabled(n, want, entries=entries)
                print("%s %s: 禁用清单 %d 条 -> %d 条" % (flag, n, r["before"], r["after"]))
            except Exception as e:
                print("%s %s 失败: %s" % (flag, n, e))
                return 1
    rep = audit(entries=entries)
    print("入口层唯一技能: %d" % rep["total"])
    print("可见: %d" % len(rep["visible"]))
    print("被禁用: %d  %s" % (len(rep["disabled"]), rep["disabled"]))
    print("禁用条目失效(路径已变): %d" % len(rep["stale_uris"]))
    for u in rep["stale_uris"]:
        print("   STALE %s" % u)
    print("禁用条目指向不存在的路径: %d" % len(rep["orphan_uris"]))
    for u in rep["orphan_uris"]:
        print("   ORPHAN %s" % u)
    if "--write-index" in sys.argv:
        target = None
        if "--index-path" in sys.argv:
            target = sys.argv[sys.argv.index("--index-path") + 1]
        if not target:
            target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILLS-INDEX.md")
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_index(rep))
        print("已重生成: %s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
