---
name: jd-adb-device-beans
description: 用 adb 驱动已连接的安卓设备上的京东 App，自动完成每日签到（签到开盲盒 + 京豆签到卡）、「全部任务」浏览/关注/评价类任务、刮卡兑换与「今日必领权益」京豆卡片，并核对京豆余额。当用户要求「操作这台设备上的京东 / 平板上的京东签到 / 领京豆 / 跑京东每日任务 / 把 adb 签到整理成 skill / 每天定时领京豆」，或需要排查设备端京东自动化的导航失败时使用。与网页版 jd-daily-beans 互补：这个是 App 端，那个是 Chrome 后台标签页。硬性禁止下单、付款、开通消费信贷。
agent_created: true
---

# 京东 App 设备端每日京豆自动化（adb）

## Overview

一条命令跑完一台 USB 连接的安卓设备上的京东每日京豆流程，不占用电脑前台浏览器，
也不看账号 Cookie。核心是 **UI 树动态定位 + 状态机导航**，不是固定坐标盲点：京东的
H5 权益中心文案会轮播、弹窗会反复遮挡、任务面板会在页面跳转后消失。

这套方法 2026-11-09 在一台 Xiaomi Pad 7（2136x3200 / Android 16）上实测跑通：
当日京豆 1109 → 1121，另得 3 张红包券。

## 安装

```bash
git clone https://github.com/niuding/jd-pad-auto-signin.git \
  ~/.workbuddy/skills/jd-adb-device-beans
```

Windows 对应 `%USERPROFILE%\.workbuddy\skills\jd-adb-device-beans`。
不装 WorkBuddy 也能单独用，直接进 `scripts/` 跑下面的命令就行。

## Prerequisites

- `adb.exe`（Google platform-tools）可用，已写入 PATH 或在 `scripts/config.json` 指定。
- 设备 USB 连接且已授权：`adb devices` 显示为 `device`，**不是** `unauthorized` / `offline`。
- 设备屏幕已解锁、京东 App 已登录。脚本只唤醒屏幕（KEYCODE_WAKEUP），**从不解锁、不碰密码**。
- Python 3.9+（仅标准库）。
- 配置：把 `scripts/config.example.json` 复制为 `scripts/config.json`。`adb` 留空则自动探测；
  `serial` 留空则用唯一设备；`base_width` / `base_height` 是坐标基准，运行时按
  `wm size` 自动缩放。`config.json` 与 `state/` 已在 `.gitignore` 中，不会误提交。

换设备或京东改版时先跑 `--check` 和 `--dry-run`，不要直接挂定时。

## Quick start

```bash
cd scripts
cp config.example.json config.json     # Windows: copy config.example.json config.json

python jd_daily_run.py --check       # 只预检：设备/授权/锁屏/登录/余额
python jd_daily_run.py --dry-run     # 预检 + 只读扫描入口，一个领取按钮都不点
python jd_daily_run.py               # 完整跑一遍；当天已成功则自动跳过
python jd_daily_run.py --force       # 忽略每日 guard，手动补跑
python jd_daily_run.py --phases sign,panel   # 只跑指定阶段
```

Windows 上不碰命令行也行：直接双击 `scripts/run-daily.bat`。它会自动从
`config.example.json` 生成 `config.json`（单设备、adb 在 PATH 或常见目录时无需填任何配置），
跑完停在窗口上让人看结果。

退出码：`0` 成功或当天已完成 / `2` 预检失败（**不写 guard**）/ `3` 页面无法加载或
运行异常（同样不写 guard）。失败不标记完成，下一次定时触发才会重试。

成功后打印 `RESULT_JSON={...}`（余额、各阶段完成数、收益），并写
`state/last_run.json`。日志按天落在 `state/run_YYYYMMDD.log`。

## Workflow（脚本内四个阶段）

1. **预检 + 起始余额**：`adb devices` 状态、包是否安装、屏幕休眠则唤醒，
   `am start -n com.jingdong.app.mall/.MainFrameActivity` 回「我的」页读 `\d+京豆`。
2. **签到**：「每日必领」横幅 → 权益中心浮层 → 「一键领取」签到开盲盒；
   重新进入 → 左侧「京豆」分类 → 「立即刮卡」京豆签到卡。
3. **任务面板**：「全部任务」→ 逐个点 `去浏览` / `去完成`，等待 6–9 秒后返回；
   面板向上滑动以覆盖屏幕外的任务；随后把 `去刮卡` 机会全部兑换。
4. **权益中心浮层**：浏览 8 秒得开盒次数、「今日必领权益」京豆卡片、立即开盒；
   最后回「我的」页读结束余额，写 guard。

导航的唯一正确姿势（血泪）：**显式 `am start` 回主框架，绝不连按返回键**——
连按会把页面栈退穿，曾直接退回桌面。H5 必须轮询等节点数 > 80 且出现特征元素，
最多等 26 秒；只判断前台 Activity 会拿到半加载的 19 节点空树。

## Hard rules

- **绝对禁止**：下单、付款、支付、白条/借钱/贷款、先享后付、0 元下单、任何金融或
  信用服务开通。按钮自身文案和整页上下文都要过 `BAN` / `risky_page()` 双过滤；
  拿不准就跳过，不要"试一下"。
- 可自动执行：关注店铺、评价、订阅、桌面小组件等**非交易类**任务（需使用者自行授权）。
- 跳过耗时且收益低的小游戏：种树、玩一玩、合成类。
- 任务列表每次重进会重置回「去浏览」，**不要无限循环**。脚本每阶段有轮次上限，
  连续两轮无新任务即停；重复刷收益递减且易触发风控。
- 不读取、不打印、不保存 Cookie / 账号 / 密码；不自动解锁锁屏。
- 不改动设备上的系统设置、不开无线调试、不安装 APK。

## 每日定时（可选）

脚本自带 once-per-day guard，**当天只真正成功执行一次**，重复触发是 no-op。
用 cron / Windows 任务计划程序 / WorkBuddy 自动化每天整点触发一次即可：

```cron
0 9 * * * cd /path/to/jd-adb-device-beans/scripts && python jd_daily_run.py
```

WorkBuddy 自动化推荐 `rrule = FREQ=DAILY;BYHOUR=9;BYMINUTE=0`。调度器实测坑：
`FREQ=DAILY` 的 BYHOUR 只接受单个整数，写多个会报错；改成
`FREQ=HOURLY;INTERVAL=1;BYHOUR=9,12,20` 虽能创建成功，但 nextRunAt 会落到创建后
1 小时的非整点（BYHOUR 列表被忽略，实际变成每小时触发）。所以只用 DAILY 单整点。

无人值守的前提：设备保持 USB 连接、屏幕解锁、USB 调试授权有效。预检失败不写 guard，
次日同一整点会再跑，也可以当天手动执行一次脚本补跑。定时任务的指令要自包含，
不要中途问人、不要失败后自动 `--force` 重跑。

## Troubleshooting

| 现象 | 处理 |
|---|---|
| `--check` 报 `unauthorized` | 解锁设备 → 开发者选项 → 撤销 USB 调试授权 → 重插数据线 → 点「允许」 |
| 读不到「我的」页 | 多半是锁屏或京东未登录；脚本不会解锁，人工解锁后等下次触发 |
| 「权益中心未加载」 | 网络慢或 H5 改版；`--dry-run` 看入口，必要时调大 `wait_for` 秒数 |
| 找不到京豆分类 | 左侧分类滚动出可视区；`find_jd_category()` 已内置一次下滑，仍失败说明改版 |
| 横幅按钮匹配不上 | 文案轮播（去领取/去抽奖/立即领）；`tap_banner()` 按区域定位，勿改回文字匹配 |
| 收益为 0 | 今天已领过或任务已重置；属正常，不是失败 |
| 页面出现「立即领取」但旁边写着 0 元下单 | `risky_page()` 会整页拦截，这是刻意设计 |

完整的坐标基准、UI 判据和踩坑清单见 `references/pitfalls.md`。
