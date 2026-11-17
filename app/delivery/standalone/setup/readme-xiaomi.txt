Xiaomi Remote Agent 0.1.21

用途
把小米蓝牙语音遥控器 2 / 2 Pro 用于 Claude / Codex 桌面版。无需安装 MiVibe Remote；已安装 MiVibe 时请先从托盘退出，两者不能同时连接遥控器。
本程序不包含输入法或语音识别功能，听写由 Claude / Codex 提供；VB-CABLE 需单独安装。

首次使用
1. 准备 Windows 蓝牙、已配对的遥控器、VB-CABLE 和 Claude / Codex。
2. 从资源管理器或本程序的开始菜单快捷方式启动 XiaomiRemoteAgent.exe。不要从 Claude 内置终端或 WMI 启动正式程序，以免 APPDATA 被重定向。
3. “按键与语音设置”选 Claude + Codex：Ctrl+D、按住型、增益 4 dB。
4. Codex 语音切换快捷键设为 Ctrl+D，麦克风选 CABLE Output；上一/下一侧边栏项目绑定 Ctrl+Shift+F1 / F2。
5. Claude 使用 Ctrl+D 听写。在“环境检查”点击“把默认录音设备设为 CABLE Output”。只更改普通和多媒体角色（eConsole=0、eMultimedia=1），不更改通信角色（eCommunications=2）。需要时点击“恢复原录音设备”。退出程序不自动恢复。
6. 首次完整返回键接管可能要求一次管理员确认：Frida Gadget 兼容层读取返回键 HID 报告。此确认与普通控制台黑框不同。

默认按键
麦克风：按住听写，松开结束；连续测试 10 次且没有削波破音。
菜单：切到 Claude 并聚焦输入框。
TV：切到 Codex 主窗口，跳过透明工具浮层。
电源：Esc，中断 agent。
OK：发送；Claude 选项卡片选中并提交，“其他”输入框也能提交，提交后回到输入框。
上/下：先进入 Claude 选项卡片，再移动选项；无卡片时为普通方向键。
左/右：Claude 输入为空时点回复末尾第一个/第二个建议；Codex 切上一个/下一个会话。
音量+/-：滚动对话，必要时自动移动鼠标；按住连滚，松开停止。
返回：退格，按住连删。主页：Win+D 显示桌面。

启动时枚举 shell:AppsFolder 并通过当前 AppID 激活 Claude/Codex，不通过它们的 .lnk 快捷方式。应用更新后如识别异常，重启 Xiaomi Remote Agent。

文件夹版请保留全部文件，放在用户可写的固定位置。remote-helper.exe 首次运行会在同目录生成 remote-helper.json；可备份后调整滚动区域和会话快捷键。配置、主日志与原录音设备备份位于 %APPDATA%\XiaomiRemoteAgent；helper 错误日志位于程序目录。

文件夹版开机启动：创建 XiaomiRemoteAgent.exe 的快捷方式，目标末尾加 --minimized，起始位置设为程序目录，放入 Win+R -> shell:startup 打开的文件夹。本程序自身使用快捷方式不影响 Claude/Codex 的 AppID 激活方式。彻底退出使用托盘“退出”。

本轮仅做离线检查和构建，没有连接遥控器或改动真实录音设备。请按根 README 完成按键、焦点、长按、10 次语音、启动无黑框、休眠唤醒重连，以及普通/多媒体设备恢复与通信设备不变的人工验证。

许可证与致谢
基于 MiVibe Remote（wyuzhi/MiVibe-Remote）修改，上游提交 34d5244。保留上游作者及贡献者版权；本程序和 remote-helper 采用 GNU GPL-3.0，无任何担保。完整许可证见 LICENSE，第三方条款见 licenses 及 THIRD_PARTY_NOTICES.md。
上游：https://github.com/wyuzhi/MiVibe-Remote
本项目：https://github.com/sumian-buff/xiaomi-remote-agent
