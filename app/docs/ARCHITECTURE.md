# Xiaomi Remote Agent 架构

基于 MiVibe Remote（wyuzhi/MiVibe-Remote）提交 `34d5244` 修改，保留上游版权和 GPL-3.0。本仓库只维护小米蓝牙语音遥控器 2 / 2 Pro，无统一多设备中心、其他硬件产品或在线更新组件。

## 主进程与内部角色

入口为 `source/standalone/xiaomi_main.py`，冻结程序为 `XiaomiRemoteAgent.exe`。主进程提供托盘、设置、环境检查和后台工作进程管理。启动先读取进程名检查 MiVibe 冲突，再取得本程序互斥量、枚举目标 AppID、载入配置和启动工作进程。

`runtime_launcher.py` 让源码与冻结程序使用同一角色分发。冻结程序重启自身，源码模式调用小米入口；内部角色包括 `audio`、`xiaomi-worker`、`xiaomi-settings`、`xiaomi-hid-injector`。Python 子进程显式传入 `CREATE_NO_WINDOW` 与 `hidden_startupinfo()`；提权注入器通过 `ShellExecuteW(runas)` 请求管理员确认并使用 `SW_HIDE`。

## 输入与音频

- `bridges/xiaomi/atvv_live_bridge.py`、`atvv_record.py`：WinRT GATT 接收 ATVV 语音并解码为 PCM，沿用上游重连和语音快捷键边沿逻辑。
- `bridges/audio/audio_router.py`、`bridges/audio_client.py`：PCM 送到 VB-CABLE 播放端 `CABLE Input`，目标应用从录音端 `CABLE Output` 获取声音。
- `bridges/raw_input_bridge.py`：遥控器 Raw Input 识别与动作分发。
- `bridges/xiaomi/hid_report_tap.py`、`hid_tap_runtime.py`、`hid_tap_injector.py`：保留上游返回键 HID 兼容层、Gadget 校验、目标进程限制和运行目录 ACL。管理员注入承担 HID 报告读取，不承担应用动作或语音识别。
- 返回键与音量键长按重复仍走上游定时路径；音量键重复调用配置的 helper 滚动动作。

## 配置与桌面助手

`xiaomi_config.py` 管理按键表、保存的预设、自定义预设、语音快捷键与重复时序。新安装默认 `agent`，显示“Claude + Codex”，语音为 `Ctrl+D` / `toggle`，增益 `4 dB`；旧应用预设继续可选。

`app_catalog.py` 在启动时通过 `remote-helper.exe apps` 枚举 `shell:AppsFolder`，将选中的 AppID 通过本程序环境变量交给工作进程。Claude 按名称及 `Claude_*!Claude` 识别，Codex 按 `OpenAI.Codex_*!App` 识别，不依赖开始菜单显示名。激活时解析逻辑别名，避免保存旧版本文件路径。

`helper_actions.py` 校验 `{"type":"helper","args":[...]}`，生成固定程序目录下 `remote-helper.exe` 的参数数组，直接执行而不经过 shell。`helper/remote-helper.cs` 保留 AttachThreadInput 前台切换、Codex 透明窗口排除、Claude 选项卡片/“其他”提交与焦点恢复、建议按钮、滚动定位和会话快捷键逻辑。激活应用只用 AppID，不读取开始菜单 `.lnk` 作为启动目标。

helper 用系统 .NET Framework 编译为 GUI 子系统 exe，与主 exe 同级。首次运行在同目录写入 `remote-helper.json`，每次动作读取配置；主程序与 helper 分别记录日志。

## 默认录音设备

`standalone/default_microphone.py` 通过 ctypes 调用 MMDeviceEnumerator / IPolicyConfig，只管理 eConsole（0）和 eMultimedia（1），不修改 eCommunications（2）。环境检查读取状态；用户点击设置后先保存原设备，再逐项修改并读回。失败时尝试回滚并保留备份，恢复成功后移除备份。此功能不调用 PowerShell。

## 隔离与文件布局

| 资源 | 本程序取值 |
|---|---|
| 应用与运行时 ID | `XiaomiRemoteAgent` |
| 配置、日志、录音备份 | `%APPDATA%\XiaomiRemoteAgent` |
| Gadget 受保护目录 | `%PROGRAMDATA%\XiaomiRemoteAgent\hid-tap` |
| 环境变量前缀 | `XIAOMI_REMOTE_AGENT_` |
| PCM / 音频控制 | `32680` / `32681` |
| Raw Input 内部控制 | `32682` |
| HID 报告通道 | `32684` |
| 主控 / 设置单实例 | `32690` / `32691` |
| 独立安装器 AppId | `774A45B5-2B5E-419C-B8C5-1FC498E9C317` |

程序不读写已安装 MiVibe 的配置，也不停止其进程，冲突时提示并退出。正式启动由资源管理器、开始菜单或开机自启完成，避免 MSIX 内置终端导致 APPDATA 重定向。

## 构建与验收边界

`source/XiaomiRemoteAgent.spec` 打包唯一主程序与 WinRT 投影。`delivery/build-standalone-packages.ps1` 使用现有 `.venv`，校验本地 Gadget，生成图标并编译 helper，输出仓库根 `dist/XiaomiRemoteAgent/`。缺少 ISCC 时跳过安装包。GPL、Frida 和 Python 依赖许可证随文件夹交付，PyInstaller 缓存留在工作区。

compileall、指定范围 ruff F、unittest 与产物归档检查用于离线验收。测试 mock 桌面动作与录音设备修改；产物存在不代表硬件、焦点、音质或实际无黑框已经通过。完整人工验收表见 [根 README](../../README.md)。
