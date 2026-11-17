// SPDX-License-Identifier: GPL-3.0-only
// remote-helper.exe — actions for Xiaomi Remote Agent.
//
//   remote-helper.exe activate <AUMID>   bring a packaged app (e.g. Claude, Codex) to the front, or start it
//   remote-helper.exe session prev|next  left/right keys: within armSeconds after Menu/TV (activate) =
//                                        previous/next session; otherwise Claude suggestion buttons or plain arrows
//   remote-helper.exe arrow up|down      up/down keys: Claude cards; in an empty prompt, an app's downWhenEmpty
//                                        key (Codex: Tab = accept its suggested next prompt)
//   remote-helper.exe scroll <delta>     volume keys: scroll the conversation under an auto-placed cursor
//   remote-helper.exe new                Home key: new session/chat in the active app (its "newSession" shortcut
//                                        from remote-helper.json, else press its 新聊天 / New chat button)
//   remote-helper.exe apps <json-path>   enumerate installed app names and AppIDs without launching them
//   remote-helper.exe shortcut <lnk> <AUMID>  (re)create a .lnk that points at the app itself, so its
//                                        icon and target follow app updates
//
// Settings: remote-helper.json next to the exe (created with defaults on first run).
// Built as a GUI-subsystem exe (/target:winexe) so no console window ever appears.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Automation;

static class Helper
{
    static readonly string Dir = AppDomain.CurrentDomain.BaseDirectory;
    static readonly string LogFile = Path.Combine(Dir, "remote-helper.log");

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch { SetProcessDPIAware(); }
            if (args.Length == 0) return 2;
            var cfg = Settings.Load(Path.Combine(Dir, "remote-helper.json"));
            switch (args[0].ToLowerInvariant())
            {
                case "activate": Activate(args[1]); return 0;
                case "session": Session(cfg, args[1].ToLowerInvariant() == "prev"); return 0;
                case "arrow": Arrow(cfg, args[1].ToLowerInvariant() == "up"); return 0;
                case "ok": Ok(); return 0;
                case "new": NewSession(cfg); return 0;
                case "scroll": Scroll(cfg, args.Length > 1 ? int.Parse(args[1]) : cfg.scrollDelta); return 0;
                case "apps":
                    if (args.Length != 2) return 2;
                    ExportApps(args[1]); return 0;
                case "shortcut": Lnk.Create(args[1], args[2]); return 0;
                case "sidebar":   // read-only diagnostics: write what the Claude helpers would act on, click nothing
                    if (args.Length != 2) return 2;
                    DumpClaude(args[1]); return 0;
            }
            return 2;
        }
        catch (Exception e)
        {
            try { File.AppendAllText(LogFile, DateTime.Now.ToString("s") + " " + string.Join(" ", args) + " : " + e + Environment.NewLine); } catch { }
            return 1;
        }
    }

    // Read AppsFolder directly so application updates cannot leave us using stale .lnk targets.
    // Reflection keeps this compatible with the system .NET Framework compiler without dynamic.
    static void ExportApps(string outputPath)
    {
        object shell = null, folder = null, items = null;
        var apps = new List<Dictionary<string, string>>();
        try
        {
            shell = Activator.CreateInstance(Type.GetTypeFromProgID("Shell.Application", true));
            folder = shell.GetType().InvokeMember("NameSpace", BindingFlags.InvokeMethod, null,
                shell, new object[] { "shell:AppsFolder" });
            if (folder == null) throw new InvalidOperationException("shell:AppsFolder is unavailable");
            items = folder.GetType().InvokeMember("Items", BindingFlags.InvokeMethod, null, folder, null);
            int count = Convert.ToInt32(items.GetType().InvokeMember("Count", BindingFlags.GetProperty,
                null, items, null));
            for (int index = 0; index < count; index++)
            {
                object item = null;
                try
                {
                    item = items.GetType().InvokeMember("Item", BindingFlags.InvokeMethod, null,
                        items, new object[] { index });
                    string name = Convert.ToString(item.GetType().InvokeMember("Name",
                        BindingFlags.GetProperty, null, item, null));
                    string appId = Convert.ToString(item.GetType().InvokeMember("ExtendedProperty",
                        BindingFlags.InvokeMethod, null, item, new object[] { "System.AppUserModel.ID" }));
                    if (!string.IsNullOrEmpty(appId))
                        apps.Add(new Dictionary<string, string> { { "name", name }, { "app_id", appId } });
                }
                finally { ReleaseCom(item); }
            }
        }
        finally
        {
            ReleaseCom(items);
            ReleaseCom(folder);
            ReleaseCom(shell);
        }
        string destination = Path.GetFullPath(outputPath);
        Directory.CreateDirectory(Path.GetDirectoryName(destination));
        File.WriteAllText(destination, new JavaScriptSerializer().Serialize(apps), new UTF8Encoding(false));
    }

    static void ReleaseCom(object value)
    {
        if (value != null && Marshal.IsComObject(value)) Marshal.FinalReleaseComObject(value);
    }

    // ---------- scroll / session switch ----------

    // Left/Right.
    //   Within armSeconds after Menu/TV (activate), or after a previous switch: previous/next session
    //   (Claude: sidebar order; other apps: their prev/next shortcut). A deliberate combo, because a bare
    //   Left/Right also clicks suggestion buttons and switching by accident is confusing.
    //   Otherwise: Claude with an empty prompt and a suggestion box -> press its first/second button;
    //   everything else -> plain arrow keys.
    static readonly string ArmFile = Path.Combine(Dir, "session-arm.state");

    // Short decision trace for session switching (remote-helper-trace.log, capped at ~200 KB).
    static readonly string TraceFile = Path.Combine(Dir, "remote-helper-trace.log");
    static void Trace(string message)
    {
        try
        {
            var fi = new FileInfo(TraceFile);
            if (fi.Exists && fi.Length > 200000) fi.Delete();
            File.AppendAllText(TraceFile, DateTime.Now.ToString("HH:mm:ss.fff") + " [" + Process.GetCurrentProcess().Id + "] " + message + Environment.NewLine);
        }
        catch { }
    }

    static void ArmSessionSwitch()
    {
        try { File.WriteAllText(ArmFile, DateTime.UtcNow.Ticks.ToString()); } catch { }
    }

    static bool SessionSwitchArmed(Settings cfg)
    {
        try
        {
            long t = long.Parse(File.ReadAllText(ArmFile).Trim());
            return (DateTime.UtcNow - new DateTime(t, DateTimeKind.Utc)).TotalSeconds <= cfg.armSeconds;
        }
        catch { return false; }
    }

    static void Session(Settings cfg, bool prev)
    {
        IntPtr fg = GetForegroundWindow();
        bool armed = SessionSwitchArmed(cfg);
        Trace("session " + (prev ? "prev" : "next") + " armed=" + armed + " claude=" + IsClaude(fg) + " fg=" + ProcessPath(fg));
        if (armed)
        {
            // Rapid presses start several helpers at once; queue them so each switch starts from the
            // session the previous one opened (otherwise they all read the same sidebar and collide).
            using (var queue = new Mutex(false, "Local\\XiaomiRemoteAgent.SessionSwitch"))
            {
                bool owned = false;
                try { owned = queue.WaitOne(15000); } catch (AbandonedMutexException) { owned = true; }
                if (!owned) return;
                try
                {
                    bool done = false;
                    fg = GetForegroundWindow();
                    if (IsClaude(fg))
                    {
                        try { done = SwitchClaudeSession(fg, prev); }
                        catch (Exception e) { try { File.AppendAllText(LogFile, DateTime.Now.ToString("s") + " claude session: " + e.Message + Environment.NewLine); } catch { } }
                    }
                    else
                    {
                        AppKeys keys = KeysFor(cfg, ProcessPath(fg));
                        string combo = keys == null ? null : (prev ? keys.prev : keys.next);
                        if (!string.IsNullOrEmpty(combo)) { SendCombo(combo); Thread.Sleep(300); done = true; }
                    }
                    if (done) { ArmSessionSwitch(); return; }   // keep the window open so you can keep stepping
                }
                finally { queue.ReleaseMutex(); }
            }
        }
        if (IsClaude(fg))
        {
            try { if (ClickClaudeSuggestion(fg, prev ? 0 : 1)) return; }
            catch (Exception e) { try { File.AppendAllText(LogFile, DateTime.Now.ToString("s") + " suggestion: " + e.Message + Environment.NewLine); } catch { } }
        }
        SendCombo(prev ? "left" : "right");
    }

    // True when keyboard focus is in a ProseMirror prompt box (Claude and Codex both use one) that
    // contains text. Errors count as "no text" so the quick actions keep working.
    static bool PromptHasText()
    {
        try
        {
            var f = AutomationElement.FocusedElement;
            if (f == null || (f.Current.ClassName ?? "").IndexOf("ProseMirror", StringComparison.Ordinal) < 0) return false;
            object vp;
            return f.TryGetCurrentPattern(ValuePattern.Pattern, out vp) && ((ValuePattern)vp).Current.Value.Trim().Length > 0;
        }
        catch { return false; }
    }

    static bool FocusInEmptyPrompt()
    {
        try
        {
            var f = AutomationElement.FocusedElement;
            if (f == null || (f.Current.ClassName ?? "").IndexOf("ProseMirror", StringComparison.Ordinal) < 0) return false;
            object vp;
            return !f.TryGetCurrentPattern(ValuePattern.Pattern, out vp) || ((ValuePattern)vp).Current.Value.Trim().Length == 0;
        }
        catch { return false; }
    }

    // Home key: start a new session in the active app.
    //   Claude: Ctrl+N (the accelerator of its 新建 button), then put the cursor in the new prompt box.
    //   Codex:  it exposes no shortcut for this, so press its 新聊天 (New chat) button via UI Automation.
    // An app's "newSession" entry in remote-helper.json overrides both.
    static readonly string[] NewChatButtonNames = { "新聊天", "New chat", "新线程", "New thread" };

    static void NewSession(Settings cfg)
    {
        IntPtr fg = GetForegroundWindow();
        bool claude = IsClaude(fg);
        AppKeys keys = KeysFor(cfg, ProcessPath(fg));
        string combo = keys == null ? null : keys.newSession;
        if (string.IsNullOrEmpty(combo) && claude) combo = "ctrl+n";
        if (!string.IsNullOrEmpty(combo)) SendCombo(combo);
        else if (!InvokeButtonNamed(fg, NewChatButtonNames)) return;
        if (claude)
        {
            Thread.Sleep(700);   // let the new session open, then focus its prompt box
            try { FocusClaudePrompt(fg); } catch { }
        }
    }

    static bool InvokeButtonNamed(IntPtr hwnd, string[] names)
    {
        var root = AutomationElement.FromHandle(hwnd);
        var cache = new CacheRequest();
        cache.Add(AutomationElement.NameProperty);
        cache.AutomationElementMode = AutomationElementMode.Full;
        AutomationElement hit = null;
        using (cache.Activate())
        {
            var buttons = root.FindAll(TreeScope.Descendants,
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button));
            foreach (AutomationElement b in buttons)
            {
                if (Array.IndexOf(names, (b.Cached.Name ?? "").Trim()) >= 0) { hit = b; break; }   // first = top of the sidebar
            }
        }
        if (hit == null) return false;
        object ip;
        if (hit.TryGetCurrentPattern(InvokePattern.Pattern, out ip)) ((InvokePattern)ip).Invoke();
        else { hit.SetFocus(); Thread.Sleep(50); SendCombo("enter"); }
        return true;
    }

    // Up/Down. In Claude, a question or approval card does not take keyboard focus: it stays in the
    // prompt box, where Up/Down recall history. So if such a card is showing and focus is not already
    // inside it, the first press moves focus to the card's first (Down) or last (Up) option instead.
    // Other apps: an app's "downWhenEmpty" key (Codex: Tab, which accepts its suggested next prompt) is
    // sent instead of Down, but only while focus is in an empty prompt box.
    static void Arrow(Settings cfg, bool up)
    {
        IntPtr fg = GetForegroundWindow();
        if (IsClaude(fg))
        {
            try
            {
                if (FocusClaudeCard(fg, up)) return;
                // No card: Down in an empty prompt forks the conversation at its newest message.
                if (!up && FocusInEmptyPrompt() && ForkClaudeAtLatest(fg)) return;
            }
            catch (Exception e) { try { File.AppendAllText(LogFile, DateTime.Now.ToString("s") + " arrow: " + e.Message + Environment.NewLine); } catch { } }
        }
        else if (!up)
        {
            AppKeys keys = KeysFor(cfg, ProcessPath(fg));
            if (keys != null && !string.IsNullOrEmpty(keys.downWhenEmpty) && FocusInEmptyPrompt())
            {
                SendCombo(keys.downWhenEmpty);
                return;
            }
        }
        SendCombo(up ? "up" : "down");
    }

    // ---------- Claude sidebar sessions and forks ----------
    //
    // Sidebar (Claude desktop 5.x): nav buttons (新建, 搜索, …) on top; then project groups — header
    // buttons such as "companion" with ExpandCollapse and a "hide-focus-ring" class — each followed by its
    // sessions (buttons whose class starts with "w-full shrink-0 border-none", named "<title>",
    // "<title> 运行中" or "<title> 从 <parent> 分叉"). Nested-session toggles ("显示 N 个嵌套会话 …",
    // "隐藏嵌套会话 …") share the header class and are excluded. The current session's title comes from
    // the header button "<title>，重命名会话". Every message has a 从此处分叉 (fork) button.

    static readonly string[] RenameSuffixes = { "，重命名会话", ", rename session", ", Rename session" };
    static readonly string[] ForkButtonNames = { "从此处分叉", "Fork from here", "Branch from here" };

    class ClaudeSidebar
    {
        public string Title;
        public List<AutomationElement> Sessions = new List<AutomationElement>();
        public List<string> Names = new List<string>();
        public int Current = -1;
        public AutomationElement LatestFork;
        public int ForkCount;
    }

    static bool IsNestedToggle(string name)
    {
        return name.StartsWith("隐藏嵌套会话") || (name.StartsWith("显示 ") && name.Contains("嵌套会话"))
            || name.StartsWith("Show ") || name.StartsWith("Hide ");
    }

    static ClaudeSidebar ReadClaudeSidebar(IntPtr hwnd)
    {
        var info = new ClaudeSidebar();
        var root = AutomationElement.FromHandle(hwnd);
        var cache = new CacheRequest();
        cache.Add(AutomationElement.NameProperty);
        cache.Add(AutomationElement.ClassNameProperty);
        cache.Add(AutomationElement.BoundingRectangleProperty);
        cache.Add(AutomationElement.IsExpandCollapsePatternAvailableProperty);
        cache.AutomationElementMode = AutomationElementMode.Full;
        AutomationElementCollection buttons;
        using (cache.Activate())
            buttons = root.FindAll(TreeScope.Descendants,
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button));

        double firstGroupTop = double.MaxValue;
        var candidates = new List<KeyValuePair<double, AutomationElement>>();
        foreach (AutomationElement b in buttons)
        {
            string name = (b.Cached.Name ?? "").Trim();
            string cls = b.Cached.ClassName ?? "";
            var rect = b.Cached.BoundingRectangle;
            foreach (var suffix in RenameSuffixes)
                if (info.Title == null && name.EndsWith(suffix)) info.Title = name.Substring(0, name.Length - suffix.Length).Trim();
            if (Array.IndexOf(ForkButtonNames, name) >= 0) { info.LatestFork = b; info.ForkCount++; }   // last = newest message
            if (rect.IsEmpty) continue;
            bool canExpand = (bool)b.GetCachedPropertyValue(AutomationElement.IsExpandCollapsePatternAvailableProperty);
            if (canExpand && cls.Contains("hide-focus-ring") && !IsNestedToggle(name) && rect.Top < firstGroupTop)
                firstGroupTop = rect.Top;
            if (cls.StartsWith("w-full shrink-0 border-none")) candidates.Add(new KeyValuePair<double, AutomationElement>(rect.Top, b));
        }
        candidates.Sort((a, c) => a.Key.CompareTo(c.Key));
        foreach (var kv in candidates)
        {
            if (kv.Key <= firstGroupTop) continue;   // nav buttons above the first project group
            string name = (kv.Value.Cached.Name ?? "").Trim();
            if (info.Current < 0 && info.Title != null && (name == info.Title || name.StartsWith(info.Title + " ")))
                info.Current = info.Sessions.Count;
            info.Sessions.Add(kv.Value);
            info.Names.Add(name);
        }
        return info;
    }

    // Left/Right with an empty prompt: open the previous/next session in sidebar order (across projects,
    // including expanded forks). At either end nothing happens.
    static bool SwitchClaudeSession(IntPtr fg, bool prev)
    {
        var info = ReadClaudeSidebar(fg);
        int target = info.Current < 0 ? 0 : info.Current + (prev ? -1 : 1);
        Trace("  sidebar title='" + info.Title + "' current=" + info.Current + "/" + info.Sessions.Count
              + " target=" + target + (target >= 0 && target < info.Names.Count ? " '" + info.Names[target] + "'" : ""));
        if (info.Sessions.Count == 0) return false;   // sidebar hidden: fall back to plain arrows
        if (target < 0 || target >= info.Sessions.Count) return true;
        InvokeOrEnter(info.Sessions[target]);
        Thread.Sleep(700);
        try { FocusClaudePrompt(fg); } catch { }
        return true;
    }

    // Down with an empty prompt and no card: fork the conversation at its newest message.
    static bool ForkClaudeAtLatest(IntPtr fg)
    {
        var info = ReadClaudeSidebar(fg);
        if (info.LatestFork == null) return false;
        InvokeOrEnter(info.LatestFork);
        Thread.Sleep(900);
        try { FocusClaudePrompt(fg); } catch { }
        return true;
    }

    static void InvokeOrEnter(AutomationElement e)
    {
        object ip;
        if (e.TryGetCurrentPattern(InvokePattern.Pattern, out ip)) ((InvokePattern)ip).Invoke();
        else { e.SetFocus(); Thread.Sleep(50); SendCombo("enter"); }
    }

    static void DumpClaude(string outputPath)
    {
        IntPtr hwnd = IntPtr.Zero;
        foreach (var p in Process.GetProcessesByName("claude"))
            if (p.MainWindowHandle != IntPtr.Zero && p.MainWindowTitle == "Claude") { hwnd = p.MainWindowHandle; break; }
        var sb = new StringBuilder();
        if (hwnd == IntPtr.Zero) sb.AppendLine("Claude window not found");
        else
        {
            var info = ReadClaudeSidebar(hwnd);
            sb.AppendLine("title: " + info.Title);
            sb.AppendLine("current index: " + info.Current + " of " + info.Sessions.Count);
            for (int i = 0; i < info.Names.Count; i++) sb.AppendLine((i == info.Current ? " -> " : "    ") + i + "  " + info.Names[i]);
            sb.AppendLine("fork buttons: " + info.ForkCount + (info.LatestFork != null ? " (latest found)" : ""));
        }
        File.WriteAllText(outputPath, sb.ToString(), new UTF8Encoding(false));
    }

    static bool IsClaude(IntPtr hwnd)
    {
        string path = ProcessPath(hwnd);
        return path != null && path.IndexOf("\\Claude_", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    // OK. On an answer option of a Claude question card, Enter only toggles that option; the card also
    // has 跳过 / 提交 buttons. So: select the option, then press 提交. Everywhere else: plain Enter.
    static void Ok()
    {
        IntPtr fg = GetForegroundWindow();
        if (IsClaude(fg))
        {
            try { if (OkInClaudeCard(fg)) return; }
            catch (Exception e) { try { File.AppendAllText(LogFile, DateTime.Now.ToString("s") + " ok: " + e.Message + Environment.NewLine); } catch { } }
        }
        SendCombo("enter");
    }

    // Returns true when it handled the press. Cases inside a Claude question card:
    //   answer option        -> select it (if not already), press 提交, back to the prompt box
    //   "其他" text field     -> press 提交 (Enter in that field only adds a new line), back to the prompt box
    //   提交 / 跳过 button     -> press it, back to the prompt box
    //   anything else (e.g. the 其他 button, which opens the text field) -> plain Enter
    static bool OkInClaudeCard(IntPtr fg)
    {
        var focused = AutomationElement.FocusedElement;
        if (focused == null) return false;
        string cls = focused.Current.ClassName ?? "";
        if (cls.IndexOf("ProseMirror", StringComparison.Ordinal) >= 0) return false;   // prompt box: plain Enter, fast path

        var card = FindClaudeCard(fg);
        if (card == null || !IsInside(focused, card)) return false;

        string name = focused.Current.Name ?? "";
        if (cls.IndexOf("answer-option", StringComparison.Ordinal) >= 0)
        {
            object tp;   // only toggle if it is not already selected (the first option starts selected)
            bool on = focused.TryGetCurrentPattern(TogglePattern.Pattern, out tp)
                      && ((TogglePattern)tp).Current.ToggleState == ToggleState.On;
            if (!on) { SendCombo("enter"); Thread.Sleep(150); }
            PressSubmit(card);
        }
        else if (focused.Current.ControlType == ControlType.Edit)
        {
            PressSubmit(card);
        }
        else if (name == "提交" || name == "跳过" || name == "Submit" || name == "Skip")
        {
            SendCombo("enter");
        }
        else return false;

        Thread.Sleep(400);   // let the card close, then put the cursor back in the prompt box
        FocusClaudePrompt(fg);
        return true;
    }

    // Left/Right in Claude: press button 0 / 1 of the "suggested next steps" box that Claude shows at the
    // end of a reply (group named 建议的后续操作; its first button has the Ctrl+Enter accelerator, which is
    // how we find it, so this does not depend on the UI language). Only when the prompt box is empty, so
    // dictated text that has not been sent yet is never lost; otherwise the keys stay plain arrows.
    static bool ClickClaudeSuggestion(IntPtr fg, int index)
    {
        var focused = AutomationElement.FocusedElement;
        if (focused == null || (focused.Current.ClassName ?? "").IndexOf("ProseMirror", StringComparison.Ordinal) < 0) return false;
        object vp;
        if (focused.TryGetCurrentPattern(ValuePattern.Pattern, out vp) && ((ValuePattern)vp).Current.Value.Trim().Length > 0) return false;

        var root = AutomationElement.FromHandle(fg);
        var cache = new CacheRequest();
        cache.Add(AutomationElement.AcceleratorKeyProperty);
        cache.AutomationElementMode = AutomationElementMode.Full;
        AutomationElement first = null;
        using (cache.Activate())
        {
            var buttons = root.FindAll(TreeScope.Descendants,
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button));
            foreach (AutomationElement b in buttons)
                if ((b.Cached.AcceleratorKey ?? "") == "Control+Enter") first = b;   // last one = newest
        }
        if (first == null) return false;
        var group = TreeWalker.ControlViewWalker.GetParent(first);
        if (group == null) return false;
        var inGroup = group.FindAll(TreeScope.Children,
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button));
        if (index >= inGroup.Count) return false;
        object ip;
        if (inGroup[index].TryGetCurrentPattern(InvokePattern.Pattern, out ip)) ((InvokePattern)ip).Invoke();
        else { inGroup[index].SetFocus(); Thread.Sleep(50); SendCombo("enter"); }
        Thread.Sleep(300);
        FocusClaudePrompt(fg);
        return true;
    }

    static bool IsInside(AutomationElement e, AutomationElement container)
    {
        var walker = TreeWalker.ControlViewWalker;
        for (var p = e; p != null; p = walker.GetParent(p))
            if (Automation.Compare(p, container)) return true;
        return false;
    }

    static void PressSubmit(AutomationElement card)
    {
        var submit = card.FindFirst(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button),
            new OrCondition(new PropertyCondition(AutomationElement.NameProperty, "提交"),
                            new PropertyCondition(AutomationElement.NameProperty, "Submit"))));
        if (submit == null) { SendCombo("enter"); return; }
        object ip;
        if (submit.TryGetCurrentPattern(InvokePattern.Pattern, out ip)) ((InvokePattern)ip).Invoke();
        else { submit.SetFocus(); Thread.Sleep(50); SendCombo("enter"); }
    }


    // Put keyboard focus in Claude's prompt box (a ProseMirror editor named 提示词).
    static void FocusClaudePrompt(IntPtr hwnd)
    {
        var root = AutomationElement.FromHandle(hwnd);
        var cache = new CacheRequest();
        cache.Add(AutomationElement.ClassNameProperty);
        cache.Add(AutomationElement.NameProperty);
        cache.AutomationElementMode = AutomationElementMode.Full;
        AutomationElement prompt = null;
        using (cache.Activate())
        {
            var edits = root.FindAll(TreeScope.Descendants,
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Edit));
            foreach (AutomationElement e in edits)
            {
                string cls = e.Cached.ClassName ?? "";
                if (cls.IndexOf("ProseMirror", StringComparison.Ordinal) >= 0)
                {
                    prompt = e;
                    if (e.Cached.Name == "提示词") break;
                }
            }
        }
        if (prompt != null) prompt.SetFocus();
    }

    static AutomationElement FindClaudeCard(IntPtr hwnd)
    {
        var root = AutomationElement.FromHandle(hwnd);
        var cache = new CacheRequest();
        cache.Add(AutomationElement.ClassNameProperty);
        cache.AutomationElementMode = AutomationElementMode.Full;
        AutomationElement card = null;
        using (cache.Activate())
        {
            var groups = root.FindAll(TreeScope.Descendants,
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Group));
            foreach (AutomationElement g in groups)
                if ((g.Cached.ClassName ?? "").IndexOf("epitaxy-approval-card", StringComparison.Ordinal) >= 0) card = g;
        }
        return card;
    }

    static bool FocusClaudeCard(IntPtr hwnd, bool up)
    {
        var card = FindClaudeCard(hwnd);   // the newest question/approval card, if any
        if (card == null) return false;

        var focused = AutomationElement.FocusedElement;
        if (focused != null && IsInside(focused, card)) return false;   // already in the card: plain arrow

        var buttons = card.FindAll(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button),
            new PropertyCondition(AutomationElement.IsKeyboardFocusableProperty, true),
            new PropertyCondition(AutomationElement.IsEnabledProperty, true)));
        if (buttons.Count == 0) return false;
        // Prefer answer options (question cards); otherwise any button (approval cards).
        var options = new List<AutomationElement>();
        foreach (AutomationElement b in buttons)
            if ((b.Current.ClassName ?? "").IndexOf("answer-option", StringComparison.Ordinal) >= 0) options.Add(b);
        if (options.Count == 0) foreach (AutomationElement b in buttons) options.Add(b);
        options[up ? options.Count - 1 : 0].SetFocus();
        return true;
    }

    static void Scroll(Settings cfg, int delta)
    {
        IntPtr fg = GetForegroundWindow();
        RECT r;
        if (fg != IntPtr.Zero && GetWindowRect(fg, out r) && !IsIconic(fg))
        {
            int w = r.Right - r.Left, h = r.Bottom - r.Top;
            POINT p; GetCursorPos(out p);
            bool inArea = p.X >= r.Left + w * cfg.areaLeft && p.X <= r.Left + w * cfg.areaRight
                       && p.Y >= r.Top + h * cfg.areaTop && p.Y <= r.Top + h * cfg.areaBottom;
            if (!inArea)
            {
                SetCursorPos(r.Left + (int)(w * cfg.targetX), r.Top + (int)(h * cfg.targetY));
                Thread.Sleep(20);
            }
        }
        mouse_event(0x0800 /*WHEEL*/, 0, 0, delta, UIntPtr.Zero);
    }

    static AppKeys KeysFor(Settings cfg, string exePath)
    {
        if (exePath == null) return null;
        foreach (var a in cfg.apps)
            if (!string.IsNullOrEmpty(a.match) && exePath.IndexOf(a.match, StringComparison.OrdinalIgnoreCase) >= 0) return a;
        return null;
    }

    static readonly Dictionary<string, byte> Vk = new Dictionary<string, byte>(StringComparer.OrdinalIgnoreCase)
    {
        {"ctrl",0x11},{"alt",0x12},{"shift",0x10},{"win",0x5B},{"tab",0x09},{"enter",0x0D},{"esc",0x1B},
        {"pageup",0x21},{"pagedown",0x22},{"up",0x26},{"down",0x28},{"left",0x25},{"right",0x27},
        {"[",0xDB},{"]",0xDD},{",",0xBC},{".",0xBE},{"/",0xBF},{"`",0xC0},{"-",0xBD},{"=",0xBB}
    };

    static void SendCombo(string combo)
    {
        var codes = new List<byte>();
        foreach (var raw in combo.Split('+'))
        {
            string k = raw.Trim();
            byte v;
            if (Vk.TryGetValue(k, out v)) codes.Add(v);
            else if (k.Length > 1 && (k[0] == 'f' || k[0] == 'F')) codes.Add((byte)(0x6F + int.Parse(k.Substring(1))));
            else if (k.Length == 1) codes.Add((byte)char.ToUpperInvariant(k[0]));
            else throw new ArgumentException("unknown key: " + k);
        }
        foreach (var c in codes) keybd_event(c, 0, 0, UIntPtr.Zero);
        Thread.Sleep(30);
        for (int i = codes.Count - 1; i >= 0; i--) keybd_event(codes[i], 0, 2 /*KEYUP*/, UIntPtr.Zero);
    }

    // ---------- activate a packaged app ----------

    static void Activate(string aumid)
    {
        ArmSessionSwitch();   // Menu/TV then Left/Right within armSeconds = switch session
        Trace("activate " + aumid + " (armed)");
        if (aumid.EndsWith(".lnk", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("AppID required; shortcuts are not supported");
        // Retained optional desktop-app presets use their shell AppIDs too.
        if (aumid.IndexOf('!') < 0)
        {
            object shell = Activator.CreateInstance(Type.GetTypeFromProgID("Shell.Application", true));
            try
            {
                shell.GetType().InvokeMember("ShellExecute", BindingFlags.InvokeMethod, null,
                    shell, new object[] { "shell:AppsFolder\\" + aumid, "", "", "open", 1 });
            }
            finally { ReleaseCom(shell); }
            return;
        }
        // Package family "Name_PublisherId" -> installed path contains "\Name_" ... "__PublisherId\"
        string family = aumid.Split('!')[0];
        int cut = family.LastIndexOf('_');
        string name = family.Substring(0, cut), publisher = family.Substring(cut + 1);
        IntPtr best = IntPtr.Zero; long bestArea = -1;
        EnumWindows((h, l) =>
        {
            if (!IsWindowVisible(h) || GetWindow(h, 4 /*GW_OWNER*/) != IntPtr.Zero || GetWindowTextLength(h) == 0) return true;
            int cloaked; DwmGetWindowAttribute(h, 14, out cloaked, 4); if (cloaked != 0) return true;
            // Skip overlays (Codex has a transparent, topmost, click-through tool window covering part of
            // the screen): tool windows, click-through windows, no-activate windows, and windows without a caption.
            int ex = GetWindowLong(h, -20), style = GetWindowLong(h, -16);
            if ((ex & (0x80 /*TOOLWINDOW*/ | 0x20 /*TRANSPARENT*/ | 0x08000000 /*NOACTIVATE*/)) != 0) return true;
            if ((style & 0x00C00000 /*WS_CAPTION*/) == 0) return true;
            string path = ProcessPath(h);
            if (path == null || path.IndexOf("\\" + name + "_", StringComparison.OrdinalIgnoreCase) < 0
                || path.IndexOf("__" + publisher + "\\", StringComparison.OrdinalIgnoreCase) < 0) return true;
            RECT r; GetWindowRect(h, out r);
            long area = (long)(r.Right - r.Left) * (r.Bottom - r.Top);
            if (area > bestArea) { bestArea = area; best = h; }
            return true;
        }, IntPtr.Zero);

        if (best != IntPtr.Zero)
        {
            if (IsIconic(best)) ShowWindow(best, 9 /*SW_RESTORE*/);
            BringToFront(best);
            if (IsClaude(best))
            {
                Thread.Sleep(150);
                try { FocusClaudePrompt(best); }
                catch (Exception e) { try { File.AppendAllText(LogFile, DateTime.Now.ToString("s") + " prompt focus: " + e.Message + Environment.NewLine); } catch { } }
            }
            return;
        }
        uint pid;
        var mgr = (IApplicationActivationManager)new ApplicationActivationManager();
        Marshal.ThrowExceptionForHR(mgr.ActivateApplication(aumid, null, 0, out pid));
    }

    // Windows only lets the foreground process hand the foreground to another window. We temporarily
    // attach our input queue to the current foreground thread so the switch is allowed. No key is
    // injected: an Alt tap (the usual trick) opens the app menu in Electron apps and steals focus.
    static void BringToFront(IntPtr target)
    {
        IntPtr fg = GetForegroundWindow();
        uint dummy;
        uint fgThread = fg == IntPtr.Zero ? 0 : GetWindowThreadProcessId(fg, out dummy);
        uint me = GetCurrentThreadId();
        bool attached = fgThread != 0 && fgThread != me && AttachThreadInput(me, fgThread, true);
        try
        {
            BringWindowToTop(target);
            SetForegroundWindow(target);
        }
        finally { if (attached) AttachThreadInput(me, fgThread, false); }
        if (GetForegroundWindow() != target)
        {
            // Fallback: a zero-distance mouse move counts as our input, which also unlocks the switch.
            mouse_event(0x0001 /*MOVE*/, 0, 0, 0, UIntPtr.Zero);
            SetForegroundWindow(target);
        }
    }

    static string ProcessPath(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return null;
        uint pid; GetWindowThreadProcessId(hwnd, out pid);
        IntPtr hp = OpenProcess(0x1000 /*QUERY_LIMITED_INFORMATION*/, false, pid);
        if (hp == IntPtr.Zero) return null;
        try
        {
            var sb = new StringBuilder(1024); int size = sb.Capacity;
            return QueryFullProcessImageName(hp, 0, sb, ref size) ? sb.ToString() : null;
        }
        finally { CloseHandle(hp); }
    }

    // ---------- settings ----------

    public class AppKeys { public string name; public string match; public string prev; public string next; public string newSession; public string downWhenEmpty; }
    public class Settings
    {
        public int scrollDelta = 240;
        // Seconds after Menu/TV (or the last switch) during which Left/Right switch sessions.
        public double armSeconds = 3;
        // The cursor is moved to (targetX, targetY) of the active window unless it is already inside the
        // area box — so scrolling hits the conversation, not the sidebar or the input box.
        public double targetX = 0.45, targetY = 0.40;
        public double areaLeft = 0.25, areaRight = 0.97, areaTop = 0.08, areaBottom = 0.80;
        public List<AppKeys> apps = new List<AppKeys>();

        public static Settings Load(string path)
        {
            var js = new JavaScriptSerializer();
            if (File.Exists(path)) return js.Deserialize<Settings>(File.ReadAllText(path, Encoding.UTF8));
            var s = new Settings();
            s.apps.Add(new AppKeys { name = "Codex", match = "\\OpenAI.Codex_", prev = "ctrl+shift+f1", next = "ctrl+shift+f2", newSession = "", downWhenEmpty = "tab" });
            s.apps.Add(new AppKeys { name = "Claude", match = "\\Claude_", prev = "", next = "", newSession = "ctrl+n", downWhenEmpty = "" });
            File.WriteAllText(path, Pretty(js.Serialize(s)), new UTF8Encoding(false));
            return s;
        }

        static string Pretty(string json)
        {
            var sb = new StringBuilder(); int indent = 0; bool str = false;
            foreach (char c in json)
            {
                if (c == '"' && (sb.Length == 0 || sb[sb.Length - 1] != '\\')) str = !str;
                if (str) { sb.Append(c); continue; }
                if (c == '{' || c == '[') { sb.Append(c).Append('\n').Append(' ', ++indent * 2); }
                else if (c == '}' || c == ']') { sb.Append('\n').Append(' ', --indent * 2).Append(c); }
                else if (c == ',') { sb.Append(c).Append('\n').Append(' ', indent * 2); }
                else if (c == ':') { sb.Append(": "); }
                else sb.Append(c);
            }
            return sb.ToString();
        }
    }

    // ---------- shell link that points at the app itself ----------

    static class Lnk
    {
        public static void Create(string lnkPath, string aumid)
        {
            IntPtr pidl; uint attrs;
            int hr = SHParseDisplayName("shell:AppsFolder\\" + aumid, IntPtr.Zero, out pidl, 0, out attrs);
            Marshal.ThrowExceptionForHR(hr);
            try
            {
                var link = (IShellLinkW)new ShellLink();
                Marshal.ThrowExceptionForHR(link.SetIDList(pidl));
                ((IPersistFile)link).Save(lnkPath, true);
            }
            finally { Marshal.FreeCoTaskMem(pidl); }
        }
    }

    // ---------- interop ----------

    delegate bool EnumProc(IntPtr h, IntPtr l);
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] static extern bool SetProcessDpiAwarenessContext(IntPtr v);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint cmd);
    [DllImport("user32.dll")] static extern int GetWindowTextLength(IntPtr h);
    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr h, int index);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT p);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] static extern void mouse_event(uint f, int dx, int dy, int data, UIntPtr extra);
    [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out int v, int size);
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr h, int flags, StringBuilder sb, ref int size);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern int SHParseDisplayName(string name, IntPtr bc, out IntPtr pidl, uint sfgaoIn, out uint sfgaoOut);

    [ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IApplicationActivationManager
    {
        int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appUserModelId, [MarshalAs(UnmanagedType.LPWStr)] string arguments, int options, out uint processId);
    }
    [ComImport, Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")] class ApplicationActivationManager { }

    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLinkW
    {
        int GetPath(IntPtr a, int b, IntPtr c, int d); int GetIDList(out IntPtr p); int SetIDList(IntPtr pidl);
    }
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")] class ShellLink { }
    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPersistFile
    {
        int GetClassID(out Guid g); [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint mode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string f, [MarshalAs(UnmanagedType.Bool)] bool remember);
    }
}
