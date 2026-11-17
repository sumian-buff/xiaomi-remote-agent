# AGENTS.md — 给编码 agent（Codex 等）的实现规格

## 0. 目标

把 `app/` 里的 MiVibe Remote Windows 源码（上游 wyuzhi/MiVibe-Remote@34d5244，GPL-3.0，已原样导入）改造成我们自己的独立程序
**Xiaomi Remote Agent**：只支持「小米蓝牙语音遥控器 2 / 2 Pro」，内置控制 Claude 桌面版和 Codex 桌面版的按键方案，
**以后不再依赖 MiVibe 上游是否维护**。

最终验收标准：在一台卸载或停用 MiVibe 的电脑上，只装本程序和 VB-CABLE，就能做到第 3 节表格里的全部功能。

## 1. 硬约束

1. 许可证 **GPL-3.0**。保留上游版权与 GPL 文本，在 README 和「关于」窗口里注明「基于 MiVibe Remote（wyuzhi/MiVibe-Remote）修改」。
2. **保留上游已经验证过的核心实现，不要重写**：ATVV 蓝牙语音（`bridges/xiaomi/atvv_live_bridge.py`、`audio/audio_router.py`）、
   按键识别与拦截（`raw_input_bridge.py`、`bridges/xiaomi/hid_report_tap.py`、`hid_tap_runtime.py`、`hid_tap_injector.py`，
   其中 Frida Gadget 只用于读取返回键的 HID 报告，需要一次管理员确认），以及按键映射和配置（`xiaomi_config.py`）。只做下面要求的改动。
3. **任何子进程都不能弹出控制台窗口**。用户的默认终端是 Windows Terminal，控制台子进程会弹出黑框，而且进程结束后窗口也不关闭（上游 0.1.20 版每次启动都会弹几个）。
   所有 `subprocess.run/Popen/check_output/call` 都必须带 `creationflags=CREATE_NO_WINDOW`，并加 `STARTUPINFO(dwFlags=STARTF_USESHOWWINDOW, wShowWindow=SW_HIDE)`。
   已知的漏网之处：`hid_tap_runtime.py` 里的 `icacls.exe`。请 grep 全部调用逐一检查。`ShellExecuteW(runas)` 调起的提权注入器也要用 SW_HIDE。
4. 不要修改、启动或停止用户电脑上已安装的 MiVibe（`D:\MiVibe Remote`、`%APPDATA%\MiVibeRemote`），也不要运行本程序去连接遥控器。硬件测试由人来做。
5. 不要联网，依赖已经装在 `app/.venv`（用 `app\.venv\Scripts\python.exe`）。Frida Gadget 已经由人下载到 `app/source/bridges/xiaomi/assets/`。
6. 每完成一个小节就 `git commit` 一次（不要 push），提交信息写清楚改了什么。

## 2. 要做的改动

### 2.1 改名，与 MiVibe 隔离（两者可以同时安装，但不能同时运行）

- 应用名 `Xiaomi Remote Agent`，APP_ID / 运行时 ID `XiaomiRemoteAgent`，可执行文件 `XiaomiRemoteAgent.exe`。
- 配置和日志目录改成 `%APPDATA%\XiaomiRemoteAgent`；所有单实例互斥量名称、托盘名称、环境变量里的 MiVibe/RemoteBridge 标识都改掉。
- 本地端口整体换段，避免和 MiVibe 冲突：PCM 31680→32680，音频控制 31681→32681，主控 31690→32690，其他用到的 3168x/3169x 端口同样处理。
- 删除图标 `MiVibeRemote.ico` 的所有引用（这个文件只授权给 MiVibe，已从仓库删除）。用 Pillow 在构建时生成一个新的简单图标：深色圆角方块加白色麦克风轮廓，保存为 `app/source/assets/app.ico`，并提交生成脚本。
- 如果检测到 MiVibe 正在运行（进程 `MiVibeRemote.exe`），启动时弹窗提示「请先退出 MiVibe Remote，两者不能同时连接遥控器」，然后退出。

### 2.2 删掉不需要的部分

- T1、V60、Hanvon 相关的桥接、入口、spec、安装脚本和测试全部删除（`bridges/t1`、`bridges/hanvon`、`standalone/t1_main.py`、`standalone/v60_main.py`、对应的 `.spec` / `.iss` / readme）。
- 在线更新整体删除：`standalone/windows_update.py`、WinSparkle 相关的构建步骤和 vendor 文件、主程序里的更新检查与菜单项。
- 「关于」窗口里指向 MiVibe 作者社群或推广的链接全部删除，只保留：版本号、GPL 声明、上游项目链接、本项目链接 https://github.com/sumian-buff/xiaomi-remote-agent 。
- 只保留小米遥控器相关代码，删掉之后要保证没有残留 import。

### 2.3 内置「Claude + Codex」预设，并设为默认

在 `xiaomi_config.py` 的预设里加入 `agent`（显示名「Claude + Codex」），放在预设列表第一位，作为全新安装时的默认预设。可以保留上游的 codex / workbuddy / wechat / qianwen 预设。

语音：快捷键 `ctrl+d`，模式 **`hold`**（麦克风按住期间一直按住 Ctrl+D，松开时一起松开）。
Claude 和 Codex 的听写快捷键都是「长按 Ctrl+D」；实测用 `toggle`（轻点两次）时，两个应用的听写都不会启动（2026-11-17 重启后验证）。默认增益改成 **4 dB**（上游默认 10 dB，实测大多数录音会削波）。

按键（`helper:` 表示调用随程序一起发布的 `remote-helper.exe`，见 2.4）：

| 按键 | 动作 |
|---|---|
| 菜单 | `helper: activate Claude_pzs8sxrjxfjjc!Claude` |
| TV | `helper: activate OpenAI.Codex_2p2nqsd0c76g0!App` |
| 电源 | 热键 `esc` |
| OK | `helper: ok` |
| 返回 | 热键 `backspace`（hold_ms 20，保持上游长按连删） |
| 上 / 下 | `helper: arrow up` / `helper: arrow down` |
| 左 / 右 | `helper: session prev` / `helper: session next` |
| 音量 + / − | `helper: scroll 240` / `helper: scroll -240`（必须保留上游的音量键长按连发） |
| 上 / 下（补充） | Codex：焦点在**空的**输入框（ProseMirror，名称「和 Codex 一起工作」）时，「下」发 `remote-helper.json` 里的 `downWhenEmpty`（Codex 默认 `tab`，即采纳建议的下一句）；输入框有字时仍是方向键 |
| 上 / 下（Claude 补充） | 输入框为空且没有选项卡片时，「下」= 点**最新一条**消息的「从此处分叉」按钮（UIA 里最后一个），然后聚焦新输入框 |
| 左 / 右（补充） | **切换会话只用组合键**：`helper: activate`（菜单 / TV）会写入 `session-arm.state`，之后 `armSeconds`（默认 3 秒）内的左 / 右 = 上一个 / 下一个会话，每切一次重新计时。Claude 按侧边栏顺序切换（见 remote-helper.cs 的 ReadClaudeSidebar：项目分组按钮带 ExpandCollapse，会话按钮的类名以 `w-full shrink-0 border-none` 开头，当前会话来自标题按钮「<标题>，重命名会话」）；其他应用发各自的 prev/next 快捷键。连按时多个 helper 进程用命名互斥量 `Local\XiaomiRemoteAgent.SessionSwitch` 排队，否则它们会同时读到同一个当前会话、互相冲突。不在计时内时：Claude 有建议框就点按钮，否则普通方向键。决策过程写在程序目录的 `remote-helper-trace.log`（约 200 KB 封顶） |
| 主页 | `helper: new`：新建会话。Claude 发 Ctrl+N（它「新建」按钮的 AcceleratorKey），然后聚焦新输入框；Codex 没有公开快捷键，用 UIA 点名称为「新聊天」/ New chat 的按钮。`remote-helper.json` 里各应用的 `newSession` 可以覆盖 |

AUMID 不要写死：启动时枚举 `shell:AppsFolder`（或读取开始菜单应用列表），找名称为 Claude、AppID 形如 `Claude_*!Claude` 的项，以及 AppID 形如 `OpenAI.Codex_*!App` 的项（Codex 在开始菜单里叫 ChatGPT）。
**一律用 AppID 启动，绝对不要用开始菜单的 `.lnk` 快捷方式**：应用更新后，旧快捷方式会指向已删除的版本文件夹，弹出「快捷方式存在问题」。

### 2.4 打包 remote-helper.exe

- 把仓库根目录的 `src/remote-helper.cs` 移到 `app/helper/remote-helper.cs`（这是我们自己写、已经过真机验证的代码，随本项目改用 GPL-3.0）。
- 构建脚本用系统自带的 .NET Framework 编译器编译它：
  `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:winexe /optimize /r:System.Web.Extensions.dll /r:<WPF>\UIAutomationClient.dll /r:<WPF>\UIAutomationTypes.dll /r:<WPF>\WindowsBase.dll`
  其中 `<WPF>` = `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\WPF`。
- 产物放进打包后的程序目录，和 `XiaomiRemoteAgent.exe` 同级。
- 在 `xiaomi_config.py` / 动作执行处新增动作类型 `helper`：`{"type": "helper", "args": ["ok"]}`，运行时解析成 `[<程序目录>\remote-helper.exe, *args]`，按上游 `command` 的方式启动（`CREATE_NO_WINDOW`）。
  设置界面里显示为「助手：…」。不要用 PowerShell 来实现任何动作。
- `remote-helper.exe` 第一次运行时，会在自己的目录里生成 `remote-helper.json`，里面有滚动定位和 Codex 切换会话的快捷键（默认 Ctrl+Shift+F1 / F2）。保持这个行为。

### 2.5 默认麦克风

Claude 的听写使用 Windows 默认录音设备。在「环境检查」里增加一项「把默认录音设备设为 CABLE Output」，点击后只设置 eConsole 和 eMultimedia 两个角色，**不改 eCommunications**（通话软件继续用原来的麦克风），并记住原来的设备，以便「恢复」。
实现参考 `scripts/audio-default.ps1`（IPolicyConfig），但要在 Python 里用 ctypes/comtypes 实现，或者放进 remote-helper.exe 新增的子命令里实现，不能调 PowerShell。

### 2.6 构建

- 把 `XiaomiRemoteBridge.spec` 改成 `XiaomiRemoteAgent.spec`，`delivery/build-standalone-packages.ps1` 改成只构建本程序，输出 `dist\XiaomiRemoteAgent\`（一个文件夹，含 exe、remote-helper.exe、Frida Gadget、许可证文本）。
  Inno Setup 安装包可以保留脚本，但这台机器没有装 Inno Setup，所以构建脚本在没有 ISCC 时要跳过安装包这一步、只出文件夹，不能报错。
- 检查方式与上游 CI 一致，在 `app/` 目录下运行：
  - `.venv\Scripts\python.exe -m compileall -q source`
  - `.venv\Scripts\python.exe -m ruff check source/standalone/xiaomi_main.py source/bridges/xiaomi --select F`（全目录的风格检查本来就不通过，不用管）
  - `.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`
  - 基线：上游 126 个测试中有 2 个失败（`test_about_window` 里依赖作者推广图片的两个测试，图片不在仓库里）。删掉作者推广内容时，一并删除或改写这两个测试。改完后必须全部通过。
- 新增测试：`agent` 预设的按键表、`helper` 动作的参数解析、端口和目录已改名、所有 subprocess 调用都带 `CREATE_NO_WINDOW`（可以用 AST 扫描源码来检查）。

### 2.7 文档

- 根目录 `README.md` 改写成用户说明：用途、按键表（第 3 节）、需要准备什么（蓝牙、VB-CABLE、Claude/Codex）、安装步骤、应用里要做的设置（Codex：语音输入快捷键长按 Ctrl+D、麦克风 CABLE Output；侧边栏上一项/下一项绑定 Ctrl+Shift+F1/F2）、致谢与 GPL 说明。
- 根目录 `LICENSE` 换成 GPL-3.0 全文（直接复制 `app/LICENSE`）。
- 删除根目录的 `src/` 与 `scripts/`（内容已移到 `app/helper/`）。

## 3. 功能验收表（人工用遥控器测试，Codex 不需要执行）

| 按键 | 预期 |
|---|---|
| 麦克风按住说话 | Claude / Codex 的听写出字，松开结束；连续 10 次正常，没有削波破音 |
| 菜单 | 切到 Claude，光标落在输入框（不会落在左上角菜单） |
| TV | 切到 Codex 主窗口（不是透明浮层），不弹「快捷方式存在问题」 |
| 电源 | Esc 中断 agent |
| OK | 发送；在 Claude 选项卡片上时选中并提交；在「其他」输入框里时提交；提交后光标回到输入框 |
| 上 / 下 | 有选项卡片时第一下进入卡片，之后在选项间移动；没有卡片时是普通方向键 |
| 左 / 右 | Claude：输入框为空时点回复末尾建议框的第一个 / 第二个按钮；菜单 / TV 后 3 秒内：上一个 / 下一个会话（连按逐个切换） |
| 下（Claude） | 输入框为空、没有卡片时，从最新一条消息分叉 |
| 音量 + / − | 滚动对话，鼠标不在对话区时自动移过去；按住连续滚 |
| 返回 / 主页 | 退格（按住连删）/ 在当前应用里新建会话 |
| 启动 / 开机自启 | 不弹任何黑框；遥控器休眠唤醒后自动重连 |

## 4. 已知的坑（都在真机上遇到过，remote-helper.cs 已处理，改动时不要破坏）

- 切前台窗口不能模拟按 Alt：Electron 应用会打开应用菜单并抢走焦点。helper 用的是 AttachThreadInput。
- Codex 有一个透明、置顶、鼠标可以点穿的工具窗口，选窗口时要跳过。
- Claude 弹出选项卡片时焦点仍在输入框里；卡片里每个选项其实是开关，提交要点「提交」按钮；「其他」输入框里按回车只会换行。
- Claude 回复末尾的建议框：第一个按钮的 AcceleratorKey 是 `Control+Enter`。
- 从 Claude 桌面版内置终端（MSIX 容器）里启动的进程，`%APPDATA%` 会被重定向。正式启动本程序要靠资源管理器、开始菜单或开机自启，不要靠 WMI。
- Codex 的快捷键设置不接受「三个修饰键 + F 键」的组合。
