# -*- coding: utf-8 -*-
"""京东 App 每日京豆签到 + 任务一键执行（adb 驱动，无人值守）。

用法：
  python jd_daily_run.py --check       # 只预检设备/屏幕/登录状态
  python jd_daily_run.py --dry-run     # 预检 + 只读扫描，不领取
  python jd_daily_run.py               # 完整跑一遍；当天已成功则跳过
  python jd_daily_run.py --force       # 忽略每日 guard，强制补跑

退出码：0 成功或当天已完成 / 2 预检失败（下个整点会重试） / 3 页面无法加载
成功时把结果写入 state/last_run.json（每日 guard），并打印 RESULT_JSON=...
"""
import argparse
import json
import os
import sys
import time
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jd_bean_lib as L  # noqa: E402


def emit(obj):
    print("RESULT_JSON=" + json.dumps(obj, ensure_ascii=False), flush=True)


def cfg(key, default):
    return L.config().get(key, default)


def note_result(ns, tag):
    """记录结果页上的关键文案（签到成功 / 到账等），不打印账号信息"""
    hits = [d for d in L.descs(ns)
            if any(k in d for k in ("签到成功", "已到账", "连签", "获得", "奖品"))]
    for h in hits[:4]:
        L.log("   [%s] %s" % (tag, h.replace("\n", " ")[:60]))


def phase_sign():
    """1) 签到开盲盒  2) 京豆签到卡（刮卡式签到）"""
    out = {"blind_box": 0, "bean_sign": 0, "ok": False}
    ns = L.recon_equity()
    if not L.equity_loaded(ns):
        return out

    if not L.risky_page(ns):
        btn = L.find(ns, r"^一键领取$|^立即领取盲盒$|^签到领盲盒$|^立即开盒$", safe_only=True)
        if btn:
            L.log("[签到] 盲盒主按钮: %s" % L.label(btn)[:28])
            L.tap(*L.center(btn))
            time.sleep(3.6)
            ns2 = L.nodes()
            note_result(ns2, "盲盒")
            out["blind_box"] = 1
            L.close_popups(ns2, 2)
    else:
        L.log("[签到] 页面含金融文案，本阶段不点击")

    # 重新进入，保证浮层状态干净；再切「京豆」分类做签到卡
    ns = L.recon_equity()
    if not L.equity_loaded(ns):
        return out
    jd = L.find_jd_category(ns)
    if jd:
        if "已选中" not in jd["desc"]:
            L.tap(*L.center(jd))
            time.sleep(2.2)
            ns = L.nodes()
    else:
        L.log("[签到] 未找到京豆分类，跳过签到卡")

    if not L.risky_page(ns):
        s = L.find(ns, r"^立即刮卡$|^立即签到$|^签到领京豆$|^去签到$", safe_only=True)
        if s:
            L.log("[签到] 京豆签到卡: %s" % L.label(s)[:28])
            L.tap(*L.center(s))
            time.sleep(3.6)
            ns2 = L.nodes()
            note_result(ns2, "签到卡")
            b = L.balance(ns2)
            if b:
                L.log("   签到后余额: %s" % b)
            out["bean_sign"] = 1
            L.confirm_and_close(ns2)
    out["ok"] = True
    return out


def recover_panel(tag=""):
    ns = L.full_navigation(tag)
    if not L.panel_open(ns):
        ns = L.full_navigation(tag + "-重试")
    return ns


def phase_panel():
    """「全部任务」面板：浏览 6 秒 / 去完成 类任务，含滚动后出现的任务"""
    done = set()
    ns = recover_panel("任务")
    if not L.panel_open(ns):
        L.log("!! 任务面板不可用，跳过本阶段")
        return 0
    stagnant = 0
    for rnd in range(cfg("max_panel_rounds", 12)):
        if not L.panel_open(ns):
            ns = recover_panel("任务续")
            if not L.panel_open(ns):
                break
        cands = [c for c in L.todo_buttons(ns) if L.key(c) not in done]
        if not cands:
            L.swipe_panel()
            ns = L.nodes()
            cands = [c for c in L.todo_buttons(ns) if L.key(c) not in done]
            if not cands:
                stagnant += 1
                if stagnant >= 2:
                    break
                continue
        stagnant = 0
        c = cands[0]
        done.add(L.key(c))
        L.log("[面板%02d] %s" % (rnd + 1, c["desc"][:52]))
        L.tap(*L.center(c))
        time.sleep(cfg("browse_wait", 8.5) if c["desc"].endswith("去浏览") else 5.0)
        L.back()
        time.sleep(1.6)
        ns = L.nodes()
        if not L.panel_open(ns) and any("全部任务" in d for d in L.descs(ns)):
            ns = L.open_all_tasks(ns)
            L.log("   同页重开任务面板")
    return len(done)


def phase_scratch():
    """把任务赚到的刮卡 / 开盒机会兑换成京豆"""
    scratched = set()
    ns = recover_panel("刮卡")
    for rnd in range(cfg("max_scratch", 8)):
        if not L.panel_open(ns):
            ns = recover_panel("刮卡续")
            if not L.panel_open(ns):
                break
        cands = [c for c in L.scratch_buttons(ns) if L.key(c) not in scratched]
        if not cands:
            L.swipe_panel()
            ns = L.nodes()
            cands = [c for c in L.scratch_buttons(ns) if L.key(c) not in scratched]
            if not cands:
                break
        c = cands[0]
        scratched.add(L.key(c))
        L.log("[刮%02d] %s" % (rnd + 1, c["desc"][:46]))
        L.tap(*L.center(c))
        time.sleep(3.2)
        ns2 = L.nodes()
        b = L.balance(ns2)
        if b:
            L.log("   当前余额: %s" % b)
        L.confirm_and_close(ns2)
        L.back()
        time.sleep(1.4)
        ns = L.nodes()
        if not L.panel_open(ns):
            ns = recover_panel("刮卡恢复")
    return len(scratched)


def phase_popup():
    """权益中心浮层：浏览 8 秒得开盒次数 + 今日必领权益京豆卡片 + 开盒"""
    out = {"browse": 0, "cards": 0, "ok": False}
    ns = L.recon_equity()
    if not L.equity_loaded(ns):
        return out
    out["ok"] = True

    done = set()
    for rnd in range(cfg("max_popup_rounds", 6)):
        if not L.equity_loaded(ns):
            ns = L.recon_equity()
        cands = [c for c in L.popup_browse_buttons(ns) if L.key(c) not in done]
        if not cands:
            break
        c = cands[0]
        done.add(L.key(c))
        L.log("[弹窗浏览%02d] %s" % (rnd + 1, c["desc"][:50]))
        L.tap(*L.center(c))
        time.sleep(cfg("popup_browse_wait", 9.0))
        L.back()
        time.sleep(1.5)
        ns = L.nodes()
        if not L.equity_loaded(ns):
            ns = L.recon_equity()
    out["browse"] = len(done)

    done2 = set()
    ns = L.recon_equity()
    for rnd in range(cfg("max_card_rounds", 10)):
        if not L.equity_loaded(ns) or L.risky_page(ns):
            ns = L.recon_equity()
        cands = [c for c in L.card_buttons(ns) if L.key(c) not in done2]
        if not cands:
            break
        c = cands[0]
        done2.add(L.key(c))
        L.log("[卡片%02d] %s" % (rnd + 1, c["desc"][:48]))
        L.tap(*L.center(c))
        time.sleep(3.5)
        ns2 = L.confirm_and_close(L.nodes())
        b = L.balance(ns2)
        if b:
            L.log("   当前余额: %s" % b)
        L.back()
        time.sleep(1.4)
        ns = L.nodes()
        if not L.equity_loaded(ns):
            ns = L.recon_equity()
    out["cards"] = len(done2)

    ns = L.recon_equity()
    ob = L.find(ns, r"^立即开盒$|^一键开盒$", safe_only=True)
    if ob and not L.risky_page(ns):
        L.log("[开盒] %s" % L.label(ob)[:24])
        L.tap(*L.center(ob))
        time.sleep(3.0)
        L.confirm_and_close(L.nodes())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只预检，不点击")
    ap.add_argument("--dry-run", action="store_true", help="预检 + 只读扫描，不领取")
    ap.add_argument("--force", action="store_true", help="忽略每日 guard")
    ap.add_argument("--config", help="指定 config.json 路径")
    ap.add_argument("--phases", default="sign,panel,scratch,popup",
                    help="要执行的阶段，逗号分隔")
    args = ap.parse_args()
    L.config(args.config)

    guard_on = cfg("daily_guard", True)
    if guard_on and not args.force and not (args.check or args.dry_run) and L.already_done():
        g = L.read_guard()
        emit({"status": "skipped", "reason": "今天已成功执行过",
              "last_run": g.get("written_at"), "balance": g.get("balance_after")})
        return 0

    ok, reason = L.preflight()
    L.log("预检: %s / %s" % ("OK" if ok else "FAILED", reason))
    if not ok:
        emit({"status": "failed", "stage": "preflight", "reason": reason})
        return 2
    b0 = L.my_balance()

    if args.check:
        emit({"status": "ok", "mode": "check", "reason": reason, "balance": b0})
        return 0

    if args.dry_run:
        ns = L.goto_my_page()
        entries = [L.label(n)[:40] for n in ns
                   if n["clickable"] and L.visible(n)
                   and any(k in L.label(n) for k in ("京豆", "签到", "领取", "每日必领"))]
        emit({"status": "ok", "mode": "dry-run", "reason": reason,
              "balance": b0, "entries": list(dict.fromkeys(entries))[:20],
              "message": "只读扫描，未点击任何领取按钮"})
        return 0

    phases = [p.strip() for p in args.phases.split(",") if p.strip()]
    result = {"status": "ok", "balance_before": b0, "phases": phases}
    reached = False
    try:
        if "sign" in phases:
            L.log("=== 阶段 1/4 签到 ===")
            result["sign"] = phase_sign()
            reached = reached or result["sign"]["ok"]
        if "panel" in phases:
            L.log("=== 阶段 2/4 任务面板 ===")
            result["panel_tasks"] = phase_panel()
        if "scratch" in phases:
            L.log("=== 阶段 3/4 兑换刮卡 ===")
            result["scratch"] = phase_scratch()
        if "popup" in phases:
            L.log("=== 阶段 4/4 权益中心浮层 ===")
            result["popup"] = phase_popup()
            reached = reached or result["popup"]["ok"]
    except Exception as e:
        L.log("!! 运行异常: %s" % e)
        L.log(traceback.format_exc(limit=3))
        result["error"] = str(e)

    b1 = L.my_balance()
    result["balance_after"] = b1
    result["gain"] = (b1 - b0) if (b1 is not None and b0 is not None and b0 >= 0) else None
    result["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    if "error" in result or not reached:
        result["status"] = "failed"
        result["reason"] = "未能稳定进入权益中心或运行异常；不写 guard，等待下个整点重试"
        L.log("=== 失败，未写每日 guard ===")
        emit(result)
        return 3

    if guard_on:
        L.write_guard(result)
    L.log("=== 完成：京豆 %s -> %s (%s) ===" %
          (b0, b1, ("+%s" % result["gain"]) if result["gain"] is not None else "?"))
    emit(result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        emit({"status": "failed", "reason": "interrupted"})
        sys.exit(3)
