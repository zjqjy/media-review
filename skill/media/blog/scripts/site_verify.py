#!/usr/bin/env python3
"""site_verify.py — 站点验收闭环（S7-C）：规范校验 → build → e2e test → （可选）git add+commit。

PersonalWebsite 的验收即站点自己的门禁（维护手册卡）：`npm run build && npm test`
（Playwright e2e 60+ 条，红=契约破了）。本脚本串起 site_check → build → test，
通过后可选 `--commit "msg"` 把本次涉及的文件（_posts/<slug>.md + images/<slug>/ + links.yml）
定点 add + commit（绝不 add -A——站点仓库常有并行改动）。

红线：只 commit 本文章相关路径；不做 hexo deploy（备案关站期，上线动作用户手动）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_check import check_post  # noqa: E402


def run(cmd: list[str] | str, cwd: Path, timeout: int, shell: bool = False) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=str(cwd), shell=shell, capture_output=True,
                       text=True, timeout=timeout, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out


def tail(text: str, n: int = 25) -> str:
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def npm_cmd(args: str) -> str:
    return f"npm {args}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="站点验收：check→build→test→可选 commit")
    ap.add_argument("--post", required=True)
    ap.add_argument("--site-root", required=True)
    ap.add_argument("--skip-build", action="store_true", help="只跑 test（内容未动模板时）")
    ap.add_argument("--skip-test", action="store_true")
    ap.add_argument("--commit", help="通过后定点 commit（消息文本）；不传则不 commit")
    ap.add_argument("--timeout", type=int, default=900, help="build/test 单步超时秒")
    a = ap.parse_args(argv)
    site = Path(a.site_root)
    post = Path(a.post)

    print("== 1/3 规范校验 ==")
    if check_post(post, site) != 0:
        return 1

    steps = [] if a.skip_build else [("npm run build", npm_cmd("run build"))]
    if not a.skip_test:
        steps.append(("npm test", npm_cmd("test")))
    total = len(steps)
    for i, (label, cmd) in enumerate(steps, start=2):
        print(f"== {i}/{total+1} {label} ==")
        rc, out = run(cmd, site, timeout=a.timeout, shell=True)
        if rc != 0:
            print(f"FAIL {label} 退出码 {rc}，输出尾部：\n{tail(out)}")
            return 1
        print(f"{label} 绿（尾部）：\n{tail(out, 8)}")

    if a.commit:
        files = [f"source/_posts/{post.name}", f"source/images/{post.stem}"]
        links_yml = site / "source" / "_data" / "links.yml"
        if links_yml.is_file():
            files.append("source/_data/links.yml")
        files = [f for f in files if (site / f).exists()]
        print("== 4 定点 commit ==")
        add_cmd = "git add " + " ".join(f'"{f}"' for f in files)
        rc, out = run(add_cmd + f' && git commit -m "{a.commit}"', site,
                      timeout=120, shell=True)
        if rc != 0:
            print(f"FAIL commit：\n{tail(out)}")
            return 1
        print(tail(out, 6))
    else:
        print("== commit 跳过（未传 --commit）==")
    print("站点验收闭环完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
