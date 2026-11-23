# -*- coding: utf-8 -*-
"""
github_skill_scan.py —— 抓取 GitHub 高星 Agent Skill 仓库榜 (可重复跑, 带本地缓存)

产出:
  github-skill-stars.md    榜单 + Top24 仓库的技能清单
  github-skill-stars.csv   全量数据(含每个仓库的所有技能名)
  github-skill-scan-cache.json  缓存(仓库元信息 + skill 清单), 重复跑只补新增的

用法:
  python github_skill_scan.py              # 增量: 只补新增仓库的 tree
  python github_skill_scan.py --refresh    # 强制重跑全部检索
  python github_skill_scan.py --refresh-trees  # 只重抓 tree, 不重跑检索

数据源: GitHub REST API (api.github.com)。优先用环境里的 GH_TOKEN(5000/h),
没有 token 就退回未认证(60/h, 检索 10/min, 所以检索之间要 sleep)。
"""
import csv, json, os, sys, time, urllib.parse, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "github-skill-scan-cache.json")
OUT_MD = os.path.join(HERE, "github-skill-stars.md")
OUT_CSV = os.path.join(HERE, "github-skill-stars.csv")
API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or ""
B = chr(96)

SEARCHES = [
    ("topic:agent-skills", {"sort": "stars", "order": "desc", "per_page": "30"}),
    ("topic:claude-skills", {"sort": "stars", "order": "desc", "per_page": "30"}),
    ("agent skills in:name,description stars:>800", {"sort": "stars", "order": "desc", "per_page": "30"}),
    ("claude code skills in:name,description stars:>300", {"sort": "stars", "order": "desc", "per_page": "30"}),
    ("skill in:name stars:>30000", {"sort": "stars", "order": "desc", "per_page": "50"}),
    ("agent skill in:description stars:>80000", {"sort": "stars", "order": "desc", "per_page": "40"}),
]
KNOWN = [
    "mattpocock/skills", "obra/superpowers", "affaan-m/ECC", "anthropics/skills",
    "addyosmani/agent-skills", "ComposioHQ/awesome-claude-skills",
    "sickn33/agentic-awesome-skills", "VoltAgent/awesome-agent-skills",
    "emilkowalski/skills", "larksuite/cli", "multica-ai/andrej-karpathy-skills",
    "nextlevelbuilder/ui-ux-pro-max-skill", "Graphify-Labs/graphify", "Nutlope/hallmark",
]


def api(path, params=None, tries=3):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    hdr = {"User-Agent": "mcode-skill-scanner", "Accept": "application/vnd.github+json"}
    if TOKEN:
        hdr["Authorization"] = "Bearer " + TOKEN
    err = None
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            err = repr(e)
            time.sleep(2.0 * (t + 1))
    return {"__error__": err}


def save(pool):
    with open(CACHE, "w", encoding="utf-8", newline="") as f:
        json.dump(list(pool.values()), f, ensure_ascii=False)


def scan_searches(pool):
    for q, extra in SEARCHES:
        p = {"q": q}
        p.update(extra)
        d = api("/search/repositories", p)
        time.sleep(12 if TOKEN else 20)
        if "__error__" in d:
            print("SEARCH_ERR", q, d["__error__"][:80])
            continue
        for it in d.get("items", []):
            fn = it["full_name"]
            if fn not in pool:
                pool[fn] = {"repo": fn, "stars": it["stargazers_count"], "forks": it["forks_count"],
                            "desc": (it.get("description") or "")[:120],
                            "topics": it.get("topics", [])[:6],
                            "updated": it.get("pushed_at", "")[:10], "src": "search"}


def scan_known(pool):
    for i in range(0, len(KNOWN), 5):
        chunk = KNOWN[i:i + 5]
        d = api("/search/repositories", {"q": " ".join("repo:" + r for r in chunk), "per_page": "20"})
        time.sleep(12 if TOKEN else 20)
        if "__error__" in d:
            print("BATCH_ERR", d["__error__"][:80])
            continue
        for it in d.get("items", []):
            fn = it["full_name"]
            if fn not in pool:
                pool[fn] = {"repo": fn, "stars": it["stargazers_count"], "forks": it["forks_count"],
                            "desc": (it.get("description") or "")[:120],
                            "topics": it.get("topics", [])[:6],
                            "updated": it.get("pushed_at", "")[:10], "src": "known"}


def scan_trees(pool):
    for it in [x for x in pool.values() if "skill_count" not in x]:
        d = api("/repos/%s/git/trees/HEAD?recursive=1" % it["repo"])
        if "__error__" in d:
            it["skill_count"] = None
            it["skills"] = []
            print("TREE_ERR", it["repo"], d["__error__"][:70])
        else:
            paths = [t["path"] for t in d.get("tree", []) if t.get("type") == "blob"]
            sk = sorted({p.rsplit("/", 1)[0].rsplit("/", 1)[-1] for p in paths if p.endswith("SKILL.md")})
            sk = sorted({(it["repo"].split("/")[-1] if s == "SKILL.md" else s) for s in sk})
            it["skills"] = sk
            it["skill_count"] = len(sk)
            it["total_files"] = len(paths)
            it["truncated"] = bool(d.get("truncated"))
        time.sleep(0.25)
        save(pool)


def local_skill_names():
    sys.path.insert(0, HERE)
    try:
        import verify_skills as vs
        return set(vs.enumerate_entries().keys())
    except Exception:
        return set()


def write_outputs(rows):
    local = local_skill_names()
    for r in rows:
        r["overlap"] = sorted(set(r.get("skills", [])) & local)

    md = ["# GitHub 高星 Agent Skill 仓库榜", ""]
    md.append("- 抓取时间: %s (GitHub REST API, 认证: %s)" % (
        time.strftime("%Y-%m-%d"), "GH_TOKEN" if TOKEN else "未认证"))
    md.append("- 采集口径: %d 组检索式 + %d 个已知 owner 定向核对, 共 %d 个去重仓库"
              % (len(SEARCHES), len(KNOWN), len(rows)))
    md.append("- SKILL.md 数: 取每个仓库的 git tree, 统计含 SKILL.md 的路径, 按目录名去重; 根目录技能用仓库名代替")
    md.append("- 交叉列「本机已有」: 与本机已安装技能同名即算命中")
    md.append("- 注意: GitHub 不给单个 SKILL.md 计星, 星数是**仓库级**; 装之前请逐个审包内容, 别只看星数")
    md.append("")
    md.append("## 榜单")
    md.append("")
    md.append("| # | 仓库 | 星数 | SKILL.md 数 | 最近推送 | 本机已有 | 一句话 |")
    md.append("|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        md.append("| %d | [%s](https://github.com/%s) | %s | %s | %s | %s | %s |" % (
            i, r["repo"], r["repo"], format(r["stars"], ","), r.get("skill_count", "-"),
            r.get("updated", "")[:10],
            (", ".join(r["overlap"][:4]) if r.get("overlap") else "-"),
            r.get("desc", "").replace("|", "/")[:80]))
    md.append("")
    md.append("## 各仓库技能清单 (Top 24)")
    md.append("")
    for i, r in enumerate(rows[:24], 1):
        if not r.get("skills"):
            continue
        md.append("### %d. %s (%s, %s 个技能)" % (i, r["repo"], format(r["stars"], ","), r.get("skill_count")))
        md.append("")
        names = r["skills"][:60]
        tail = "" if len(r["skills"]) <= 60 else ", ..."
        md.append(B + B.join(names) + tail + B)
        md.append("")
    md.append("## 重跑")
    md.append("")
    md.append(B + "python github_skill_scan.py" + B + "  增量补全; " + B + "--refresh" + B + "  全量重跑。")
    md.append("")
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md))

    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "repo", "stars", "skill_count", "updated", "local_overlap", "skills", "desc"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["repo"], r["stars"], r.get("skill_count"), r.get("updated"),
                        "|".join(r.get("overlap", [])), "|".join(r.get("skills", [])),
                        r.get("desc", "")])


def main():
    pool = {}
    if os.path.isfile(CACHE) and "--refresh" not in sys.argv:
        try:
            for it in json.load(open(CACHE, encoding="utf-8")):
                pool[it["repo"]] = it
        except Exception:
            pool = {}
    if "--refresh" in sys.argv or not pool:
        scan_searches(pool)
        scan_known(pool)
        save(pool)
    scan_trees(pool)
    save(pool)
    rows = sorted(pool.values(), key=lambda x: -x["stars"])
    write_outputs(rows)
    print("repos=%d  with_skill_md=%d  errors=%d" % (
        len(rows), sum(1 for r in rows if (r.get("skill_count") or 0) > 0),
        sum(1 for r in rows if r.get("skill_count") is None)))
    print("md=%s  csv=%s" % (OUT_MD, OUT_CSV))
    return 0


if __name__ == "__main__":
    sys.exit(main())
