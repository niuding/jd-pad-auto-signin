# -*- coding: utf-8 -*-
"""京东 App 京豆签到自动化的 adb / UI 通用层。

只依赖 Python 标准库 + adb.exe + 设备上的 uiautomator。
所有坐标以 2136x3200 为基准，运行时按 `wm size` 实际分辨率缩放。
"""
import json
import os
import re
import shutil
import subprocess
import time
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE = os.path.join(ROOT, "state")
os.makedirs(STATE, exist_ok=True)

BASE_W, BASE_H = 2136, 3200
DEV_UI = "/sdcard/wb_jd_bean_ui.xml"
UI = os.path.join(STATE, "ui.xml")
GUARD = os.path.join(STATE, "last_run.json")

# 任何含这些词的按钮一律不点。用户授权边界：不下单、不付款、不开金融服务。
BAN = re.compile(
    r"下单|付款|支付|抢购|一分|白条|借钱|贷款|去使用|试用|种树|玩一玩|合成"
    r"|先享后付|金融|信用|分期|开通|0元"
)
CONFIRM = (r"^(立即领取|点击领取|一键领取|领取|去签到|签到领京豆|立即开盒|一键开盒"
           r"|立即刮卡|刮开|开心收下|收下|我知道了|知道了|立即签到)$")
CARD_TAIL = ("去领京豆", "立即领取", "点击领取", "去签到", "去领豆")
TASK_TAIL = re.compile(r"(去浏览|去完成)\s*$")

_cfg = None
_sx = _sy = 1.0


def config(path=None):
    global _cfg
    if _cfg is None or path:
        p = path or os.environ.get("JD_BEAN_CONFIG") or os.path.join(HERE, "config.json")
        with open(p, encoding="utf-8") as f:
            _cfg = json.load(f)
    return _cfg


def pkg():
    return config().get("package", "com.jingdong.app.mall")


def log(s):
    stamp = time.strftime("%H:%M:%S")
    line = "[%s] %s" % (stamp, s)
    try:
        with open(os.path.join(STATE, "run_%s.log" % date.today().strftime("%Y%m%d")),
                  "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


# ---------- adb 基础 ----------

def adb_exe():
    p = config().get("adb") or ""
    if p and os.path.exists(p):
        return p
    p = shutil.which("adb")
    if p:
        return p
    for c in (os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
              os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
              r"C:\adb\adb.exe", r"C:\platform-tools\adb.exe", "/usr/bin/adb"):
        if os.path.exists(c):
            return c
    raise RuntimeError("找不到 adb.exe，请在 config.json 的 adb 字段填写完整路径")


def adb(args, timeout=40):
    cmd = [adb_exe()]
    serial = config().get("serial") or ""
    if serial:
        cmd += ["-s", serial]
    cmd += [str(a) for a in args]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return ((r.stdout or b"").decode("utf-8", "replace")
                + (r.stderr or b"").decode("utf-8", "replace"))
    except Exception as e:
        return "ERR:" + str(e)


def init_scale():
    global _sx, _sy
    o = adb(["shell", "wm", "size"])
    m = re.search(r"(\d{3,5})x(\d{3,5})", o)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if (w > h) != (BASE_W > BASE_H):
            w, h = h, w
        _sx, _sy = w / BASE_W, h / BASE_H
    return _sx, _sy


def px(v):
    return int(v * _sx)


def py(v):
    return int(v * _sy)


def tap(x, y):
    adb(["shell", "input", "tap", str(int(x)), str(int(y))])


def back():
    adb(["shell", "input", "keyevent", "4"])


def swipe_panel():
    """任务面板内向上滑动，露出屏幕外的任务"""
    adb(["shell", "input", "swipe", str(px(1500)), str(py(2750)),
         str(px(1500)), str(py(1650)), "600"])
    time.sleep(1.3)


def top_activity():
    o = adb(["shell", "dumpsys", "activity", "activities"])
    m = re.search(r"topResumedActivity=ActivityRecord\{\S+ \S+ ([^ }]+)", o)
    return m.group(1) if m else ""


# ---------- UI 树 ----------

def _parse(xml):
    out = []
    for m in re.finditer(r"<node[^>]*>", xml):
        n = m.group(0)
        b = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
        if not b:
            continue
        d = re.search(r'content-desc="([^"]*)"', n)
        t = re.search(r'text="([^"]*)"', n)
        c = re.search(r'clickable="([^"]*)"', n)
        out.append({
            "desc": (d.group(1) if d else "").strip(),
            "text": (t.group(1) if t else "").strip(),
            "box": tuple(int(v) for v in b.groups()),
            "clickable": bool(c and c.group(1) == "true"),
        })
    return out


def nodes(retries=2):
    """uiautomator dump 偶发失败（动画未停），重试后返回节点列表"""
    for attempt in range(retries + 1):
        adb(["shell", "uiautomator", "dump", DEV_UI])
        if os.path.exists(UI):
            try:
                os.remove(UI)
            except Exception:
                pass
        adb(["pull", DEV_UI, UI])
        if os.path.exists(UI):
            try:
                with open(UI, encoding="utf-8") as f:
                    ns = _parse(f.read())
                if ns:
                    return ns
            except Exception:
                pass
        if attempt < retries:
            time.sleep(1.0)
    return []


def center(n):
    x1, y1, x2, y2 = n["box"]
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def visible(n):
    x1, y1, x2, y2 = n["box"]
    return x2 > x1 and y2 > y1 and y1 < py(3100) and y2 <= py(3200)


def label(n):
    return (n["desc"] or n["text"]).strip()


def safe(n):
    return not BAN.search(label(n))


def find(ns, pattern, safe_only=False):
    for n in ns:
        if not visible(n) or not n["clickable"]:
            continue
        s = label(n)
        if s and re.search(pattern, s) and (not safe_only or safe(n)):
            return n
    return None


def balance(ns):
    for n in ns:
        for s in (n["desc"], n["text"]):
            m = re.match(r"^(\d{3,7})京豆$", s.strip())
            if m:
                return int(m.group(1))
    return None


def descs(ns):
    return [n["desc"] for n in ns if n["desc"]]


def has_my_page(ns):
    return any(re.match(r"^\d{3,7}京豆$", d.strip()) for d in descs(ns))


def equity_loaded(ns):
    """H5 权益中心加载完成的判据：不能只看前台 Activity，必须等节点数够多"""
    if len(ns) < 80:
        return False
    return any(("权益中心" in d) or ("今日必领权益" in d) or ("已选中,推荐" in d)
               or ("签到盲盒奖品已到账" in d) or ("做任务解锁刮卡" in d)
               or ("一键领取" in d)
               for d in descs(ns))


def panel_open(ns):
    return any("订阅刮京豆" in d or "逛免费抽盲盒" in d for d in descs(ns))


def wait_for(pred, seconds=22):
    end = time.time() + seconds
    ns = []
    while time.time() < end:
        ns = nodes()
        if pred(ns):
            return ns
        time.sleep(1.2)
    return ns


def close_popups(ns, times=3):
    for _ in range(times):
        cl = find(ns, r"^关闭按钮$|^关闭$")
        if not cl:
            break
        tap(*center(cl))
        time.sleep(1.2)
        ns = nodes()
    return ns


def risky_page(ns):
    """整页出现消费信贷/开通类文案时，连「立即领取」这种中性按钮也不能点"""
    return any(k in d for d in descs(ns)
               for k in ("先享后付", "0元下单", "白条", "分期", "信用", "开通金融服务"))


def confirm_and_close(ns):
    """结果页的二次确认 + 关闭；带 BAN + 整页上下文过滤"""
    if risky_page(ns):
        log("   !! 当前页面含金融/开通类文案，跳过二次确认按钮")
        return ns
    btn = find(ns, CONFIRM, safe_only=True)
    if btn:
        log("   二次确认: %s" % label(btn)[:28])
        tap(*center(btn))
        time.sleep(2.4)
        ns = nodes()
    cl = find(ns, r"^关闭$|^关闭按钮$")
    if cl:
        tap(*center(cl))
        time.sleep(1.0)
        ns = nodes()
    return ns


# ---------- 导航状态机 ----------

def goto_my_page(seconds=14):
    """显式启动主框架回到「我的」页。绝不连按返回键——会把页面栈退穿到桌面。"""
    adb(["shell", "am", "start", "-n", pkg() + "/.MainFrameActivity"])
    time.sleep(2.0)
    ns = wait_for(has_my_page, seconds)
    if not has_my_page(ns):
        tap(px(1877), py(3070))
        time.sleep(2.2)
        ns = wait_for(has_my_page, 10)
    if not has_my_page(ns):
        adb(["shell", "monkey", "-p", pkg(),
             "-c", "android.intent.category.LAUNCHER", "1"])
        time.sleep(4.0)
        tap(px(1877), py(3070))
        time.sleep(2.5)
        ns = wait_for(has_my_page, seconds)
    return ns


def my_balance():
    return balance(goto_my_page())


def tap_banner(ns):
    """「每日必领」横幅右侧按钮：文案轮播（去领取/去抽奖/立即领），用区域定位"""
    for n in ns:
        x1, y1, x2, y2 = n["box"]
        if n["clickable"] and px(1700) < x1 < px(2050) and py(880) < y1 < py(1080) and y2 > y1:
            log("   横幅按钮: %s @%s" % (label(n)[:24], n["box"]))
            tap(*center(n))
            return
    tap(px(1951), py(968))


def recon_equity():
    """回主框架 -> 每日必领横幅 -> 权益中心弹窗（保留弹窗，不关）"""
    ns = goto_my_page()
    if not has_my_page(ns):
        return []
    tap_banner(ns)
    ns = wait_for(equity_loaded, 26)
    log("   权益中心加载: 节点=%d 前台=%s" % (len(ns), top_activity()))
    return ns


def find_jd_category(ns):
    for n in ns:
        if n["clickable"] and visible(n) and n["box"][0] < px(400) and re.search(r"京豆\s*\d+", n["desc"]):
            return n
    # 左侧分类列表可能滚动出可视区，向下滑一次再找
    adb(["shell", "input", "swipe", str(px(170)), str(py(1200)),
         str(px(170)), str(py(2500)), "500"])
    time.sleep(1.2)
    for n in nodes():
        if n["clickable"] and visible(n) and n["box"][0] < px(400) and re.search(r"京豆\s*\d+", n["desc"]):
            return n
    return None


def open_all_tasks(ns):
    ab = find(ns, r"^全部任务$")
    if ab:
        tap(*center(ab))
        time.sleep(2.0)
        return nodes()
    return ns


def full_navigation(tag=""):
    """从任意状态回到「京豆」分类并展开「全部任务」面板"""
    ns = recon_equity()
    if not equity_loaded(ns):
        log("!! %s 权益中心未加载，重试一次" % tag)
        ns = recon_equity()
    if not equity_loaded(ns):
        return []
    ns = close_popups(ns)
    jd = find_jd_category(ns)
    if jd:
        if "已选中" not in jd["desc"]:
            tap(*center(jd))
            time.sleep(2.2)
            ns = nodes()
    else:
        log("   !! 未找到京豆分类，可见分类: %s" % [d for d in descs(ns) if d][:10])
    ns = open_all_tasks(ns)
    return ns


# ---------- 任务选择器（全部基于 content-desc，且过 BAN） ----------

def todo_buttons(ns):
    out = []
    for n in ns:
        d = n["desc"]
        x1, y1, _, _ = n["box"]
        if not n["clickable"] or not visible(n) or x1 < px(1200) or y1 < py(1000):
            continue
        if TASK_TAIL.search(d) and safe(n):
            out.append(n)
    return out


def scratch_buttons(ns):
    out = []
    for n in ns:
        d = n["desc"]
        x1, y1, _, _ = n["box"]
        if (n["clickable"] and visible(n) and x1 >= px(1200) and y1 >= py(1000)
                and d.endswith("去刮卡") and safe(n)):
            out.append(n)
    return out


def popup_browse_buttons(ns):
    """权益中心弹窗里的「浏览 8 秒得开盒次数」"""
    out = []
    for n in ns:
        d = n["desc"]
        x1, y1, _, _ = n["box"]
        if (n["clickable"] and visible(n) and d.endswith("去浏览") and "开盒次数" in d
                and py(1200) < y1 < py(1700) and x1 >= px(400) and safe(n)):
            out.append(n)
    return out


def card_buttons(ns):
    """「今日必领权益」里的京豆卡片"""
    out = []
    for n in ns:
        d = n["desc"]
        x1, y1, _, _ = n["box"]
        if (n["clickable"] and visible(n) and "京豆" in d and d.endswith(CARD_TAIL)
                and safe(n) and px(400) < x1 < px(1700) and py(1600) < y1 < py(3100)):
            out.append(n)
    return out


def key(n, length=26):
    return re.sub(r"\s+", "", n["desc"])[:length]


# ---------- 预检 / 每日 guard ----------

def preflight():
    """返回 (ok, reason)。只做只读检查 + 拉起主页，不点击任何领取按钮。"""
    try:
        adb_exe()
    except Exception as e:
        return False, str(e)
    adb(["start-server"])
    out = adb(["devices"])
    rows = [l.strip() for l in out.splitlines()
            if re.match(r"^\S+\s+(device|unauthorized|offline|recovery|sideload)\b", l.strip())]
    if not rows:
        return False, "没有 adb 设备（数据线未连 / USB 调试关闭）"
    states = [r.split()[1] for r in rows]
    if "device" not in states:
        return False, "设备状态为 %s（需在设备上点「允许 USB 调试」）" % "/".join(states)
    if pkg() not in adb(["shell", "pm", "list", "packages", pkg()]):
        return False, "设备未安装京东 App (%s)" % pkg()
    # 屏幕休眠时唤醒（不解锁，绝不处理密码）
    p = adb(["shell", "dumpsys", "power"])
    if "mWakefulness=Asleep" in p or "mWakefulness=Dozing" in p:
        adb(["shell", "input", "keyevent", "224"])
        time.sleep(1.5)
    init_scale()
    ns = goto_my_page()
    if not has_my_page(ns):
        return False, "读不到「我的」页（可能锁屏 / 未登录 / 京东页面异常）"
    return True, "ok (%s, %s)" % (rows[0].split()[0], "%dx%d" % (px(BASE_W), py(BASE_H)))


def read_guard():
    try:
        with open(GUARD, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def already_done():
    g = read_guard()
    return g.get("date") == date.today().isoformat() and g.get("status") == "ok"


def write_guard(data):
    data = dict(data)
    data["date"] = date.today().isoformat()
    data["written_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(GUARD, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
