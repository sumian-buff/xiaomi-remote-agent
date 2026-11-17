# 第三方组件说明

本文件记录本项目离线构建所打包或运行时使用的第三方组件。它们不受本项目 GPL-3.0 重新授权，仍适用各自条款。

## Frida Gadget 17.15.3

- 用途：读取 RC003 返回键对应的 HID 报告；Windows 的普通键盘和 Raw Input 路径会丢弃该报告。
- 官方文件：[frida-gadget-17.15.3-windows-x86_64.dll.xz](https://github.com/frida/frida/releases/download/17.15.3/frida-gadget-17.15.3-windows-x86_64.dll.xz)
- SHA-256：`B566D70189B6D551AD8F4E0BEA24DE08A3D4C0F559BB35B2BDB67D45182240C2`
- 协议：Frida core 的 [wxWindows Library Licence 3.1 / LGPL exception](https://github.com/frida/frida-core/blob/main/COPYING)。本地协议文本保存在 `licenses/frida-COPYING.txt`，构建时复制到程序目录的 `licenses/`。

Frida Gadget 在这里是硬件输入兼容层，不参与软件授权、加密或防破译。

## VB-CABLE Driver Pack 4.5

- 用途：把小米遥控器的 ATVV 蓝牙音频输出为 Windows 可用的虚拟麦克风。
- 官方页面：[VB-CABLE Virtual Audio Device](https://vb-audio.com/Cable/)
- 官方文件：[VBCABLE_Driver_Pack45.zip](https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip)
- SHA-256：`B950E39F01AF1D04EA623C8F6D8EB9B6EA5C477C637295FABF20631C85116BFB`
- 模式：Donationware。安装说明明确标注 VB-Audio 来源。

Xiaomi Remote Agent 不内嵌或再分发 VB-CABLE。用户可以自行安装；应用中的“安装/修复语音驱动”仅在主动点击时通过保留的驱动安装脚本下载固定文件、校验 SHA-256 与发布者签名，再打开官方安装窗口。构建与测试不会执行该功能。专业、批量、集成或再分发场景应依据 [VB-Audio 当前许可](https://vb-audio.com/Services/licensing.htm)另行取得适用授权。

## Python 依赖

运行和构建依赖包括 hidapi、NumPy、python-sounddevice、Pillow、psutil、pystray、WinRT Python projections 与 PyInstaller。准确版本见 `requirements.txt` 和 `requirements-dev.txt`；再分发时应保留这些软件各自要求的许可证与通知。

## 产品图与应用图标

本项目图标由 app/scripts/generate-icon.py 使用 Pillow 生成，随本项目以 GPL-3.0 发布。

## 上游版权与修改说明

基于 MiVibe Remote（wyuzhi/MiVibe-Remote）修改，上游提交 `34d5244`。保留上游作者和贡献者的版权，Python 应用代码与本项目自有 helper 均按 GNU GPL-3.0 发布。许可证全文见 LICENSE。生成图标不使用上游受限品牌素材。
