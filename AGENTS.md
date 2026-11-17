# AGENTS.md — 给编码 agent（Codex 等）的实现规格

本文件是 **xiaomi-remote-agent** 的完整设计。请按「里程碑」顺序实现，每个里程碑做完都要通过它的验收标准，再进入下一个。
需要用户按遥控器时，停下来告诉用户具体按哪几个键、看什么现象，**不要猜测硬件行为**。

---

## 0. 目标

做一个 **独立的 Windows 程序**，把「小米蓝牙语音遥控器 2 Pro」变成 AI 编程助手（Claude 桌面版、OpenAI Codex 桌面版）的遥控器：

- 按住遥控器麦克风说话 → 声音进入虚拟麦克风 → 触发应用自带的听写（Ctrl+D）→ 文字进入输入框。
- 遥控器按键 → 切换应用、滚动对话、在 agent 弹出的选项卡片里选择并提交、切换会话、中断 agent。

**不依赖** MiVibe Remote 或任何第三方遥控器桥接程序。唯一的外部依赖是 **VB-CABLE**（VB-Audio 出品的虚拟声卡驱动，用户自行从 https://vb-audio.com/Cable/ 安装）。

## 1. 硬约束

1. **许可证 MIT**。只能依据公开资料（Google 的 ATVV「Voice over BLE」规范、微软文档）和本仓库代码实现。
   **禁止复制 GPL 代码**（例如 MiVibe Remote、remote-mic-app 等 GPL 项目的源码），也不要逐行翻译它们。
2. 语言与框架：**C# / .NET 8**，目标框架 `net8.0-windows10.0.19041.0`（这样可以直接使用 WinRT 蓝牙 API）。
   - UI：WinForms，只要一个托盘图标和一个简单的设置/日志窗口。
   - 允许的 NuGet 依赖：`NAudio`（MIT，用于 WASAPI 播放），其余尽量不用。
   - 发布：`dotnet publish -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true`，产物是一个 exe。
3. **绝对不要启动控制台子进程**（powershell、cmd、icacls 等）。用户的默认终端是 Windows Terminal，任何控制台子进程都会弹出黑框，而且进程结束后窗口也不会关。所有动作都在进程内完成。
4. **切换前台窗口时不要模拟按 Alt 键**。在 Electron 应用（Claude、Codex）里，单独按一下 Alt 会打开应用菜单并抢走焦点。用 `AttachThreadInput` + `SetForegroundWindow`（见第 6 节）。
5. 程序以普通用户权限运行，**不需要管理员**，不注入任何进程。

## 2. 硬件事实（已在真机上观察到）

| 项目 | 值 |
|---|---|
| 设备 | 小米蓝牙语音遥控器 2 Pro，Windows 里显示为 `MI RC` / 「小米蓝牙语音遥控器」 |
| USB 风格 ID | `VID_2717&PID_32B8`（出现在 BLE HID 设备实例路径中，如 `...DEV_VID&012717_PID&32B8...`） |
| 连接 | BLE。按键走标准 HID-over-GATT（服务 0x1812），由 Windows 自带驱动处理 |
| HID 服务 | **Windows 不允许应用直接读 0x1812 的特征值**（访问被拒），所以按键只能从 Windows 输入系统里拿 |
| 语音 | 厂商自定义 GATT 服务，即 ATVV（见第 4 节），应用可以正常访问 |
| 配对 | 同时按住「主页」+「菜单」几秒进入配对。遥控器同一时间只连一台设备 |

按键到 Windows 虚拟键（VK）的映射（已观察；`E0` 表示扩展扫描码）：

| 遥控器键 | Windows 收到的键 | HID 用法码（键盘页） |
|---|---|---|
| 上 / 下 / 左 / 右 | VK_UP 0x26 / VK_DOWN 0x28 / VK_LEFT 0x25 / VK_RIGHT 0x27 | 0x52 / 0x51 / 0x50 / 0x4F |
| OK | VK_RETURN 0x0D | 0x28 |
| 返回 | VK_BROWSER_BACK 0xA6（部分固件为 VK_BACK 0x08） | — |
| 主页 | VK_BROWSER_HOME 0xAC（部分固件为 VK_HOME 0x24） | — |
| 菜单 | VK_APPS 0x5D | 0x65 |
| TV | VK_OEM_3 0xC0（即反引号键 `，扫描码 0x29） | 0x35 |
| 电源 | VK 0xFF，扫描码 0x5E（E0） | — |
| 音量 + / − | VK_VOLUME_UP 0xAF / VK_VOLUME_DOWN 0xAE | 0x80 / 0x81 |
| 麦克风 | 开始一次 ATVV 语音会话；部分固件**同时**发送 F5（VK 0x74），必须吞掉 | — |

> 注意：上下左右、OK、TV（反引号）、菜单这些键和**普通键盘发出的完全一样**，所以必须按设备区分（第 5 节）。

## 3. 架构

```
XiaomiRemoteAgent.exe（托盘程序，单进程）
├── RemoteKeyFilter     低层键盘钩子 + Raw Input：识别并吞掉遥控器按键，转成 RemoteButton 事件
├── AtvvVoiceClient     WinRT BLE：连接遥控器的 ATVV 服务，收音频、解码
├── VirtualMicOutput    NAudio WASAPI：把 16 kHz PCM 重采样后播放到「CABLE Input」
├── ActionEngine        按配置把 RemoteButton 映射为动作（从 src/remote-helper.cs 移植）
├── Config              %APPDATA%\XiaomiRemoteAgent\config.json（第 8 节）
└── TrayUi              托盘菜单：启用/暂停、打开日志、重新连接、开机自启、退出
```

`src/remote-helper.cs` 是一个**已在真机上验证过**的独立小程序（MIT，本项目自有代码），里面的动作逻辑要整体移植进 `ActionEngine`。把它的命令行入口改成方法调用。

## 4. 语音：ATVV（Android TV Voice over BLE）

依据 Google 公开的「Voice over BLE」（ATVV）规范实现。以下数值部分来自规范、部分来自真机日志；标注 **[核对]** 的地方，请对照规范原文确认。

- 服务 UUID：`AB5E0001-5A21-4F05-BC7D-AF01F617B664`
  - `AB5E0002-…`：TX，主机写命令
  - `AB5E0003-…`：RX，音频数据（notify）
  - `AB5E0004-…`：CTL，控制事件（notify）
- 主机 → 遥控器（写 TX）[核对]：`GET_CAPS 0x0A`、`MIC_OPEN 0x0C`、`MIC_CLOSE 0x0D`、`MIC_EXTEND 0x0E`（v1.0）
- 遥控器 → 主机（CTL notify）[核对]：`AUDIO_STOP 0x00`、`AUDIO_START 0x04`、`START_SEARCH 0x08`、`AUDIO_SYNC 0x0A`、`GET_CAPS_RESP 0x0B`、`MIC_OPEN_ERROR 0x0C`
- 真机日志：发送 `0A 01 00 00 03 03`（GET_CAPS：版本 1.0，支持编解码位图 0x0003，交互模型 0x03）后，
  遥控器回复 `version=1.0 codec=0x02 sample_rate=16000 frame_size=120`。
  **偶尔第一次连接时会回复 codec=0x00 / 8000 Hz**，这时断开重连一次就会变成 16 kHz。实现时要么重连，要么同时支持 8 kHz。
- 编解码 0x02 = IMA/DVI ADPCM，16 kHz，单声道，16 bit。
- **每次会话开始（AUDIO_START）都要把 ADPCM 解码器状态重置为 predictor=0、step_index=0**。真机实测：遥控器不一定发 AUDIO_SYNC，不重置的话第二次说话会饱和失真。
  收到 AUDIO_SYNC 时，按规范用其中的 predictor / step index 重新同步。
- 交互：按住麦克风 → 遥控器发会话开始事件 → 主机按规范回应（需要时发 MIC_OPEN）→ 音频通知持续到来 → 松开 → AUDIO_STOP。
  会话时长没有发现限制（实测连续 27 秒正常）。
- 默认增益 **0 dB**。参考程序用了 +10 dB，结果大多数录音都削波了（峰值 32767）。在设置里提供增益选项。
- 连接：用 `BluetoothLEDevice.FromIdAsync` / `GetGattServicesForUuidAsync`。设备从已配对设备里按名称 `MI RC` 或 VID/PID 查找。
  断线后每 3 秒自动重试。遥控器休眠后按任意键会被唤醒并重连。

## 5. 按键：区分遥控器与真键盘

目标：只拦截**来自遥控器**的按键，同一个键从真键盘按下时完全不受影响。

推荐方案（公开、常用，不需要驱动或注入）：

1. 注册 Raw Input（`RegisterRawInputDevices`，键盘 + 消费者控制页 0x0C，`RIDEV_INPUTSINK`，用一个隐藏的消息窗口接收）。
   用 `GetRawInputDeviceInfo(RIDI_DEVICENAME)` 拿到设备路径，路径里含 `VID&012717_PID&32B8`（或 `VID_2717&PID_32B8`）的就是遥控器。
2. 安装 `WH_KEYBOARD_LL` 低层钩子。钩子回调**先于** WM_INPUT 被调用，所以要做关联：
   - 对「遥控器可能发出的键」（第 2 节表里的 VK），在钩子里调用 `PeekMessage(..., WM_INPUT, WM_INPUT, PM_NOREMOVE)` / `GetRawInputBuffer` 检查同一按键的原始输入是否来自遥控器；
   - 来自遥控器且该键有映射 → 返回 1 吞掉，再把事件交给 ActionEngine；否则放行。
   - 这是网上「Combining Raw Input and keyboard Hook to selectively block input from multiple keyboards」那种做法，请先查阅这一类公开资料再实现。
3. 音量、电源这类键在真键盘上很少见，也要用同样的设备判断，不能「见键就吞」。
4. 钩子回调必须很快（Windows 默认超时约 300 ms），动作放到另一个线程执行。

**这是整个项目风险最高的一步**，所以里程碑 M1 只做「识别 + 打日志」，不吞键。

## 6. 动作（从 src/remote-helper.cs 移植，已在真机验证）

| 默认按键 | 动作 |
|---|---|
| 麦克风 | 会话开始时轻点一次 Ctrl+D，结束时再轻点一次（Claude、Codex 的听写开关）。按键可配置，模式可选 `toggle`（按下、松开各轻点一次）/ `hold`（按下即按住，松开才放开） |
| 菜单 | 切到 Claude（`activate`），并把焦点放到 Claude 输入框 |
| TV | 切到 Codex |
| 电源 | Esc（中断 agent） |
| OK | 回车；在 Claude 选项卡片里时见下方「Claude 卡片」 |
| 返回 | 退格 |
| 上 / 下 | 方向键；Claude 有卡片且焦点不在卡片里时，第一次按先聚焦卡片 |
| 左 / 右 | Claude：输入框为空、且回复末尾有「建议的后续操作」框时，左 = 点第一个按钮（带 Ctrl+Enter 快捷键的那个），右 = 点第二个按钮，之后焦点回到输入框。Codex：「上一个 / 下一个会话」快捷键 Ctrl+Shift+F1 / F2（需要用户在 Codex 里把「上一个/下一个侧边栏项目」绑定到这两个键）。都不满足时就是普通左右键 |
| 音量 + / − | 鼠标滚轮 ±240，按住连发（首次延迟 0.4 s，之后每 0.12 s 一次）。如果鼠标不在前台窗口的对话区域里，先把鼠标移到对话区 |
| 主页 | Win+D |

移植时必须保留的细节（每一条都是踩过的坑）：

- **按应用 ID（AUMID）切换应用**：Claude = `Claude_pzs8sxrjxfjjc!Claude`，Codex = `OpenAI.Codex_2p2nqsd0c76g0!App`。
  启动时用 `Get-StartApps` 的等价 API（shell:AppsFolder 枚举）确认一遍，**不要通过开始菜单的 .lnk 快捷方式启动**：应用更新后，旧快捷方式会指向已删除的版本文件夹，弹出「快捷方式存在问题」。
- **选窗口时跳过浮层**：Codex 有一个透明、置顶、鼠标可以点穿的工具窗口（`WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED`，没有 `WS_CAPTION`），覆盖屏幕右侧。要跳过 TOOLWINDOW / TRANSPARENT / NOACTIVATE 以及没有 WS_CAPTION 的窗口，并按进程映像路径匹配包名。
- **切前台**：`AttachThreadInput(当前线程, 前台窗口线程, true)` → `BringWindowToTop` → `SetForegroundWindow` → detach；如果失败，发一次零距离 `mouse_event(MOVE)` 再试。不要按 Alt。
- **DPI**：进程声明 Per-Monitor-V2 DPI 感知，否则坐标会错。
- **滚动定位**：目标点 = 窗口宽 45%、高 40% 处；鼠标已在宽 25%–97%、高 8%–80% 的区域内时不移动。
- **Claude 卡片（UI Automation）**，类名来自 Claude 桌面版 5.x，版本更新后可能变化，要写成可配置并做容错：
  - 输入框：`ControlType.Edit`，类名含 `ProseMirror`，名称为「提示词」（英文界面可能叫 Prompt）。
  - 卡片容器：`ControlType.Group`，类名含 `epitaxy-approval-card`（问题卡片还同时含 `epitaxy-question-card`）；取最后一个，即最新的。
  - 选项：`ControlType.Button`，类名含 `epitaxy-answer-option`，支持 TogglePattern（选中 = On；第一项默认就是 On）。
  - 「其他」：一个 Button（名称「其他」）。按回车后出现 `ControlType.Edit`，名称「其他选项」。**在这个输入框里按回车只会换行，不会提交**，听写的文字会写进这里。
  - 底部按钮：「跳过」「提交」（英文 Skip / Submit）。
  - OK 键规则：焦点在选项上 → 如果没选中就先回车选中，然后调用「提交」的 InvokePattern；焦点在「其他选项」输入框 → 直接点「提交」；焦点在「提交 / 跳过」→ 回车；以上几种情况结束后，都等 400 ms 再把焦点放回输入框。焦点在输入框（ProseMirror）时直接回车，不做任何 UIA 查询（这条路径必须快）。
  - 「建议的后续操作」框：Claude 在回复结束后显示，`ControlType.Group`，名称「建议的后续操作」，里面有 1–2 个 Button；第一个按钮的 `AcceleratorKey` 是 `Control+Enter`。
    靠这个快捷键找按钮，不要靠中文名称，这样换成英文界面也能用；取最后一个（最新的）。只有输入框为空时才去点它，免得用户还没发出去的听写内容丢失。
  - 读 UIA 属性时用 `CacheRequest` 批量读取，否则每次查询要 1 秒左右。
  - 卡片出现时，Claude **不会**把焦点移到卡片上，焦点仍在输入框（在输入框里按上下键会翻历史记录），所以才需要「上 / 下第一次先聚焦卡片」这条规则。

## 7. 系统设置

- 虚拟麦克风：VB-CABLE 的播放端「CABLE Input」接收我们输出的声音，录音端「CABLE Output」就是应用听到的麦克风。
- Claude 的听写使用 Windows 默认录音设备。首次运行时询问用户：是否把「默认设备」角色（eConsole + eMultimedia）设为 CABLE Output。
  **「默认通信设备」角色（eCommunications）不要动**，通话软件仍然使用原来的耳机麦克风。实现参考 `scripts/audio-default.ps1`（IPolicyConfig）。
- Codex：用户需要在 Codex 设置 → 语音输入里，把「切换型」快捷键设为 Ctrl+D、麦克风设为 CABLE Output。Codex **不接受三个修饰键加 F 键的组合**。
- 开机自启：写入 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`。

## 8. 配置文件 `%APPDATA%\XiaomiRemoteAgent\config.json`

```json
{
  "remote": { "name": "MI RC", "vidPid": "VID_2717&PID_32B8" },
  "voice": { "gainDb": 0, "hotkey": "ctrl+d", "mode": "toggle" },
  "scroll": { "delta": 240, "targetX": 0.45, "targetY": 0.40,
              "area": { "left": 0.25, "right": 0.97, "top": 0.08, "bottom": 0.80 } },
  "apps": [
    { "name": "Claude", "aumid": "Claude_pzs8sxrjxfjjc!Claude", "match": "\\Claude_", "prev": "", "next": "" },
    { "name": "Codex", "aumid": "OpenAI.Codex_2p2nqsd0c76g0!App", "match": "\\OpenAI.Codex_", "prev": "ctrl+shift+f1", "next": "ctrl+shift+f2" }
  ],
  "buttons": {
    "menu": "activate:Claude", "tv": "activate:Codex", "power": "key:esc", "ok": "ok",
    "back": "key:backspace", "up": "arrow:up", "down": "arrow:down",
    "left": "session:prev", "right": "session:next",
    "volume_up": "scroll:up", "volume_down": "scroll:down", "home": "key:win+d"
  }
}
```

## 9. 里程碑与验收

| # | 内容 | 难度 | 验收（需要用户按遥控器的项目标了 👤） |
|---|---|---|---|
| M0 | 项目骨架：.NET 8 WinForms 托盘程序、日志文件、配置读写、单文件发布 | 低 | `dotnet build` 通过；托盘图标出现；退出干净 |
| M1 | Raw Input 设备识别，**只打日志不吞键** | 中 | 👤 按遥控器每个键，日志标记 `remote`；在真键盘上按同样的键，日志标记 `keyboard` |
| M2 | 低层钩子 + 关联，吞掉遥控器按键 | 高 | 👤 遥控器的上键不再传到记事本；真键盘的上键照常可用；连按 20 次没有漏判、误判 |
| M3 | ActionEngine：移植 src/remote-helper.cs 的全部动作 | 中 | 👤 第 6 节表中每个键都按预期工作；Claude 卡片的选择、提交、「其他」输入、回到输入框全部通过 |
| M4 | ATVV：连接、能力协商、收音频、解码，**先写成 WAV 文件** | 中 | 👤 按住说 5 秒，得到能听清的 16 kHz WAV |
| M5 | 实时输出到 CABLE Input，并在会话开始/结束时发 Ctrl+D | 中 | 👤 在 Claude 和 Codex 里按住遥控器说话都能出字；连续 10 次都正常 |
| M6 | 默认麦克风设置、开机自启、托盘菜单、断线重连 | 低 | 重启电脑后无需任何操作即可使用；遥控器休眠唤醒后能自动恢复 |
| M7 | README、发布说明、GitHub Release | 低 | 全新电脑按 README 操作 15 分钟内可以用起来 |

## 10. 本仓库现有文件

- `src/remote-helper.cs`：已验证的动作逻辑（命令行版本，供移植参考）。用 .NET Framework 自带的 csc 编译：
  `csc /target:winexe /r:System.Web.Extensions.dll /r:<WPF>\UIAutomationClient.dll /r:<WPF>\UIAutomationTypes.dll /r:<WPF>\WindowsBase.dll`
- `scripts/audio-default.ps1`：读取和设置默认录音设备（IPolicyConfig），供第 7 节参考。
