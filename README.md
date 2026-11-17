# Xiaomi Remote Agent

把**小米蓝牙语音遥控器 2 / 2 Pro**变成 Claude 桌面版和 Codex 桌面版的控制器：按住麦克风说话，用按键发送、回答选项、切换会话和滚动对话。

程序独立接收遥控器按键与 ATVV 蓝牙语音，**运行不依赖 MiVibe Remote**。两者可以同时安装，但不能同时运行或连接同一遥控器。检测到 `MiVibeRemote.exe` 时，本程序会提示先退出 MiVibe 后退出。

已在真机上验证（2026-11-17，Windows 11、小米蓝牙语音遥控器 2 Pro、Claude 桌面版 5.11、Codex 26.1111）：语音输入、切换应用、选项卡片、建议按钮、切换会话、滚动、长按、开机自启、遥控器休眠唤醒重连，全程不弹黑框。换了电脑或应用版本后，请按下方表格重新检查一遍。

## 需要准备

- 64 位 Windows 10 / 11 电脑，蓝牙可用。
- 小米蓝牙语音遥控器 **2 或 2 Pro**。
- 已安装的 [VB-CABLE 虚拟声卡](https://vb-audio.com/Cable/)，按官方说明完成安装和必要的重启。
- Claude 桌面版、Codex 桌面版，以及应用内可用的语音输入功能。

遥控器声音经 `CABLE Input` 播放端送入虚拟声卡，Claude / Codex 从 `CABLE Output` 录音端接收。Xiaomi Remote Agent 不自带语音识别模型；听写由目标应用提供。VB-CABLE 不包含在本程序文件夹里。

## 安装和首次设置

1. 从 MiVibe 托盘菜单退出它，确保它不会在本程序运行时自动启动。无需卸载或移动 MiVibe 的文件和配置。
2. 将交付的整个 `dist\XiaomiRemoteAgent\` 文件夹复制到固定、当前用户可写的位置，例如 `%LOCALAPPDATA%\Programs\XiaomiRemoteAgent`。保留两个 exe、`_internal`、许可证等全部文件，不要只复制 exe。
3. 按遥控器说明书进入蓝牙配对模式，在 Windows 蓝牙设置中完成配对。
4. **从资源管理器双击 `XiaomiRemoteAgent.exe`**。也可从本程序的开始菜单快捷方式或开机自启项启动。不要从 Claude 内置终端的 MSIX 容器或 WMI 启动正式程序，这些方式可能导致 `%APPDATA%` 被重定向。
5. 在「按键与语音设置」确认当前预设为 **Claude + Codex**，语音快捷键 **Ctrl+D**，触发方式**按住型 / hold**，增益 **4 dB**。按住遥控器麦克风期间，程序一直按住 Ctrl+D，松开时一起松开。
6. 打开「环境检查」，检查遥控器、VB-CABLE 和后台桥接状态。首次完整返回键接管可能弹出一次 Windows 管理员确认：沿用的 Frida Gadget 兼容层读取返回键 HID 报告，并保留校验和受保护运行目录。
7. 配置 Claude / Codex，再按下方按键表验收。

程序启动时枚举 `shell:AppsFolder` 中的 AppID，识别 `Claude_*!Claude` 和 `OpenAI.Codex_*!App`；Codex 在开始菜单中可能显示为 ChatGPT。菜单键和 TV 键直接通过当前 AppID 激活应用，**不通过 Claude / Codex 的 `.lnk` 快捷方式启动**。应用更新后如识别异常，重启 Xiaomi Remote Agent 重新枚举，不要填写旧版本 exe 路径。

## Claude / Codex 中的设置

**Codex：**

- 语音输入的听写快捷键设为**长按（按住型）`Ctrl+D`**，麦克风选择 `CABLE Output`。
- 「上一个侧边栏项目」绑定 `Ctrl+Shift+F1`，「下一个侧边栏项目」绑定 `Ctrl+Shift+F2`，与 `remote-helper.json` 一致。
- 不要用「三个修饰键 + F 键」代替这些组合。

**Claude：**

- 听写快捷键为**长按 `Ctrl+D`**（Claude 默认就是这样），确认设置里没有改成别的键。
- Claude 听写使用 Windows 默认录音设备。在本程序「环境检查」点击**「把默认录音设备设为 CABLE Output」**。
- 只切换 `eConsole`（0，普通）和 `eMultimedia`（1，多媒体），**不修改 `eCommunications`（2，通信）**。通话软件可继续使用原通信麦克风。
- 第一次实际切换前会记录原设备。需要时点击**「恢复原录音设备」**。备份位于 `%APPDATA%\XiaomiRemoteAgent\default-microphone.json`；恢复前保留此文件，并连接原麦克风。

打开环境检查只读取状态，不会自动修改默认麦克风。退出程序也不会自动恢复；不用遥控器听写时可主动点击恢复。

## 默认按键与人工验收

| 按键 | 预期行为与验收要点 |
|---|---|
| 麦克风按住说话 | Claude / Codex 听写出字，松开结束；连续测试 10 次，确认没有遗漏结束、削波或破音。默认增益 4 dB。 |
| 菜单 | 切到 Claude，光标落在输入框，不落到左上角菜单。 |
| TV | 切到 Codex 主窗口，跳过透明、置顶、可点穿的工具浮层；不弹「快捷方式存在问题」。 |
| 电源 | 发送 `Esc`，中断当前 agent。 |
| OK | 发送；在 Claude 选项卡片上选中并提交，在「其他」输入框内也能提交；提交后光标回到输入框。 |
| 上 / 下 | 出现 Claude 选项卡片时，第一下进入卡片，之后在选项间移动；没有卡片时发送普通方向键。 |
| 左 / 右 | Claude 输入框为空时，点回复末尾建议框的第一个 / 第二个按钮；Codex 切换上一个 / 下一个会话。 |
| 音量 + / − | 滚动对话，鼠标不在对话区域时自动移入；按住持续滚动，松开停止。增量 `240` / `-240`。 |
| 返回 | 退格，按住连续删除，松开停止；默认 `hold_ms=20`。 |
| 主页 | 发送 `Win+D`，显示桌面。 |
| 启动 / 开机自启 | 不弹控制台黑框；遥控器休眠后唤醒能自动重连，语音和按键都恢复。 |

人工验证先使用可丢弃的草稿和测试会话，分别检查普通文本框、选项卡片和「其他」输入框。音量键与返回键都要检查长按和松开。改变鼠标位置、窗口尺寸及显示缩放后再检查滚动定位。重启程序、登录 Windows、遥控器休眠唤醒后重复关键项目；验证普通/多媒体麦克风的设置与恢复，并确认通信角色未变。

## 开机启动、配置和日志

文件夹版可创建**本程序自己的**快捷方式：右键 `XiaomiRemoteAgent.exe` 创建快捷方式，在目标末尾添加 ` --minimized`，起始位置设为程序目录。按 `Win+R` 输入 `shell:startup`，将快捷方式放入打开的文件夹。删除此快捷方式即可关闭开机自启。本程序的快捷方式与菜单键 / TV 键通过 AppID 激活 Claude / Codex 是两条不同路径。

关闭主窗口后可通过托盘找回；彻底停止使用托盘「退出」。配置与主日志位于 `%APPDATA%\XiaomiRemoteAgent`；主窗口提供「打开日志」。

`remote-helper.exe` 首次运行会在**程序目录**生成 `remote-helper.json`，记录滚动定位和会话快捷键；错误写入同目录 `remote-helper.log`。可备份 JSON 后调整：

- `targetX`、`targetY`：需要移动鼠标时，对话目标点在当前窗口内的比例，默认 `0.45`、`0.40`。
- `areaLeft`、`areaRight`、`areaTop`、`areaBottom`：允许直接滚动的区域，比例取值 0 到 1。
- `apps` 中 Codex 的 `prev`、`next`：默认 `ctrl+shift+f1`、`ctrl+shift+f2`，修改后同步 Codex 设置。

默认音量键动作显式传入 `240` / `-240`，覆盖 helper 的 `scrollDelta` 默认值。修改按键滚动量时，应备份并调整 `%APPDATA%\XiaomiRemoteAgent\xiaomi_keys.json` 中对应 helper 动作参数，再重启程序；保持 JSON 格式有效。

## 开发与许可证

离线检查和构建命令见 [app/README.md](app/README.md)，实现规格见 [AGENTS.md](AGENTS.md)。文件夹构建不要求 Inno Setup；有 ISCC 时可额外生成安装包。项目不含在线自动更新。

**基于 MiVibe Remote（wyuzhi/MiVibe-Remote）修改**，上游源码导入自提交 `34d5244`。感谢上游作者及贡献者的 ATVV、音频路由、按键识别与拦截、配置实现；保留其版权和 GPL 文本。`remote-helper.cs` 随本项目采用 GPL-3.0。

本项目采用 **GNU GPL-3.0**，完整条款见 [LICENSE](LICENSE)，不提供任何担保。第三方组件保留各自许可证，见 [第三方组件说明](app/THIRD_PARTY_NOTICES.md) 和交付目录 `licenses/`。

- 上游项目：<https://github.com/wyuzhi/MiVibe-Remote>
- 本项目：<https://github.com/sumian-buff/xiaomi-remote-agent>
