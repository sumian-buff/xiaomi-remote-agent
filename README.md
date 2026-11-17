# xiaomi-remote-agent

把**小米蓝牙语音遥控器 2 Pro**变成 AI 编程助手（Claude 桌面版、OpenAI Codex 桌面版）的遥控器：
坐在沙发上，按住遥控器说话下指令，用方向键回答 agent 的选项，用音量键翻看长回答。

> 状态：**设计完成，正在开发**。完整技术规格见 [AGENTS.md](AGENTS.md)，可以直接交给 Codex 等编码 agent 实现。
> 目前能用的是 `src/remote-helper.cs`（按键动作部分），它需要配合 [MiVibe Remote](https://github.com/wyuzhi/MiVibe-Remote) 接收遥控器信号。
> 本项目的目标是做成不依赖 MiVibe 的独立程序。

## 按键

| 遥控器 | 作用 |
|---|---|
| 麦克风（按住说话） | Claude / Codex 自带的听写（Ctrl+D） |
| 菜单 | 切到 Claude，光标回到输入框 |
| TV | 切到 Codex |
| 电源 | Esc：中断 agent |
| OK | 发送；在 agent 的选项卡片上时，选中并提交 |
| 返回 | 退格 |
| 上 / 下 | 方向键；Claude 弹出选项卡片时，第一下先进入卡片 |
| 左 / 右 | Claude：点回复末尾「建议的后续操作」框里的第一个 / 第二个按钮。Codex：上一个 / 下一个会话 |
| 音量 + / − | 滚动对话（会自动把鼠标移到对话区） |
| 主页 | 显示桌面 |

## 需要准备

- Windows 10/11，电脑有蓝牙
- 小米蓝牙语音遥控器 2 Pro（同时按住「主页」+「菜单」进入配对，在 Windows 蓝牙设置里添加）
- [VB-CABLE](https://vb-audio.com/Cable/) 虚拟声卡驱动（免费，捐赠软件）
- Claude 桌面版 和/或 Codex 桌面版

## 应用里的设置

- **Codex** → 设置 → 语音输入：「切换型」快捷键设为 **Ctrl+D**，麦克风设为 **CABLE Output**。
- **Codex** → 设置 → 键盘快捷键：「上一个侧边栏项目」设为 **Ctrl+Shift+F1**，「下一个侧边栏项目」设为 **Ctrl+Shift+F2**。
- **Claude**：Ctrl+D 本身就是听写开关；Windows 默认录音设备设为 CABLE Output（通信设备不用改）。

## 许可证

MIT。欢迎任何人拿去继续开发。
