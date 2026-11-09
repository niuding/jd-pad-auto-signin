# jd-pad-auto-signin

把安卓平板 / 手机用 USB 连上电脑，每天自动完成京东 App 的签到开盲盒、京豆签到卡、浏览任务、刮卡兑换与「今日必领权益」京豆卡片，跑完报一句京豆余额。

**不下单、不付款、不开通任何消费信贷或金融服务。** 个人自用自动化，请遵守京东用户协议；页面结构、任务列表和奖励随时可能变化。

本仓库同时是一个 [WorkBuddy](https://www.workbuddy.cn/) Skill。完整技术说明（选择器、导航状态机、排障表）见 [SKILL.md](SKILL.md) 与 [references/pitfalls.md](references/pitfalls.md)。与网页版 [jd-daily-beans-skill](https://github.com/niuding/jd-daily-beans-skill) 互补：一个跑 App，一个跑 Chrome 后台标签页，两边入口不同，可同时用。

## 给接手的 AI：一次装好

用户把配套文章丢给你、说「参考这篇文章，帮我在电脑上搭好」时，按下面顺序做完，全程不要反复追问用户：

1. **准备 adb**：下载 Google 官方 platform-tools（Windows 用 `platform-tools-latest-windows.zip`）解压，把 `platform-tools` 目录加入用户 PATH；或 `winget install --id Google.PlatformTools`。macOS / Linux 用各自的包管理器。
2. **确认设备**：`adb devices -l` 必须显示 `device`。若是 `unauthorized`，提示用户**先解锁设备**，在「允许 USB 调试吗」弹窗勾「一律允许」；`offline` 就重插数据线。记下 serial 和 `adb shell wm size`。设备必须已登录京东 App。
3. **拉代码并配置**：
   ```bash
   git clone https://github.com/niuding/jd-pad-auto-signin.git ~/.workbuddy/skills/jd-adb-device-beans
   cd ~/.workbuddy/skills/jd-adb-device-beans/scripts
   cp config.example.json config.json
   ```
   Windows 对应 `%USERPROFILE%\.workbuddy\skills\jd-adb-device-beans`（`cp` 换成 `copy`）。`config.json` 的 `adb` 和 `serial` 都可留空——前者自动探测，后者用唯一连接的设备。坐标按 `wm size` 相对 2136×3200 自动缩放，换设备不用改脚本。`config.json` 与 `state/` 已被 `.gitignore` 排除。
4. **先自检，再实跑**：
   ```bash
   python jd_daily_run.py --check      # 设备 / 授权 / 锁屏 / 登录 / 起始余额
   python jd_daily_run.py --dry-run    # 只读扫描，一个领取按钮都不点
   python jd_daily_run.py              # 完整跑一遍
   ```
   成功时打印一行 `RESULT_JSON={...}`，含 `balance_before` / `balance_after` 和各阶段完成数。**不要加 `--force`。**
   Windows 若 `python` 指向商店占位程序（退出码 9009），改用真实解释器的完整路径，或直接双击 `scripts/run-daily.bat`（它会自动找可用 Python 并生成配置）。
5. **设每天 09:00 定时**：Windows 任务计划程序，或 WorkBuddy 自动化 `FREQ=DAILY;BYHOUR=9;BYMINUTE=0`（注意 `FREQ=DAILY` 的 BYHOUR 只接受单个整数；用 `HOURLY;BYHOUR=9,12,20` 会被调度器忽略列表，变成每小时触发）。脚本自带按天 guard，只有完整跑通才写 `state/last_run.json`，所以也可以每小时触发做失败重试。
6. **向用户汇报**：今天京豆余额变化、各阶段完成数、定时几点跑、平时要保持什么状态（电脑开机 + 平板解锁 + USB 连接 + 调试授权 + 京东保持登录）。

## 手动运行

不想经过 AI 或命令行：Windows 双击 `scripts/run-daily.bat`，跑完停在窗口显示结果。其余平台按 [SKILL.md](SKILL.md) 的 Quick start。

## 硬边界

- 只做签到、浏览、刮卡、领权益卡片，以及不花钱的关注 / 评价 / 订阅。
- **绝不**下单、付款、开通「先享后付」「0 元下单」等消费信贷。脚本用 `BAN` 正则 + `risky_page()` 整页上下文双重拦截，疑似页面整页不点——那个「立即领取」按钮本身不含任何禁用词，只过滤按钮文案会漏。
- 不读取、不保存账号密码、Cookie、锁屏密码；不解锁锁屏、不改设备系统设置、不安装 APK。
- 任务列表每次重进会重置回「去浏览」，脚本已有轮次上限与「连续两轮无新任务即停」，不要写无限循环。

## 常见坑

锁屏时授权弹窗根本不出现；只有充电功能的数据线；H5 半加载时 UI 树只有十几个节点（必须轮询等到节点数充足且出现特征元素）；连按返回键会把页面栈退穿、甚至退回桌面（要用 `am start` 显式回主框架）；「每日必领」横幅文案会轮播，按区域定位而不是按文字匹配。详见 [references/pitfalls.md](references/pitfalls.md)。
