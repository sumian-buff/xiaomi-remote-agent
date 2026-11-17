# 贡献指南

本项目仅维护小米蓝牙语音遥控器 2 / 2 Pro。保留上游已经验证的 ATVV、音频路由和按键拦截核心；每次修改限定范围，并说明测试结果与未执行的硬件验证。

不要提交真实设备地址、用户日志、账号、密钥或第三方二进制。一个提交解决一个明确问题，保留上游归属与 GPL-3.0 许可证。

在 app 目录使用已准备好的虚拟环境，离线运行：

```powershell
.venv\Scripts\python.exe -m compileall -q source
.venv\Scripts\python.exe -m ruff check source/standalone/xiaomi_main.py source/bridges/xiaomi --select F
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\delivery\build-standalone-packages.ps1
```

构建只使用本地依赖与已经校验的 Frida Gadget。缺少 Inno Setup 时正常跳过安装包，仍生成仓库根目录 dist\XiaomiRemoteAgent。测试不得连接遥控器、注入进程、改变默认麦克风或操作用户安装的 MiVibe；这些功能由人工按根 README 验收。
