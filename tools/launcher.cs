using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: System.Reflection.AssemblyTitle("符卡作业簿")]
[assembly: System.Reflection.AssemblyDescription("符卡作业簿 · 抽符 · 退治 · 收卡")]
[assembly: System.Reflection.AssemblyProduct("符卡作业簿")]
[assembly: System.Reflection.AssemblyCompany("Shinichi & Fastrof")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.0.0.0")]

class Launcher
{
    [STAThread]
    static void Main()
    {
        string dir = Path.GetDirectoryName(Application.ExecutablePath);
        // 优先启动打包版，这样任务栏显示的是「符卡作业簿」而不是 Python
        string bundled = Path.Combine(dir, "SpellCardHomework.exe");
        if (File.Exists(bundled))
        {
            try { Process.Start(bundled); return; }
            catch { }
        }
        string app = Path.Combine(dir, "app.pyw");
        if (!File.Exists(app))
        {
            Show("找不到 app.pyw，请把本程序和 app.pyw 放在同一个文件夹里。", "Shinichiの练习小工具");
            return;
        }

        string pyw = FindPythonw(dir);
        if (pyw == null)
        {
            DialogResult r = MessageBox.Show(
                "没有找到 Python。\n\n请先安装 Python 3.10 或更高版本（安装时勾选 Add python.exe to PATH），然后重新运行本程序。\n\n要现在打开下载页面吗？",
                "Shinichiの练习小工具", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (r == DialogResult.Yes)
            {
                try { Process.Start("https://www.python.org/downloads/"); }
                catch { }
            }
            return;
        }

        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(pyw);
            psi.Arguments = "\"" + app + "\"";
            psi.WorkingDirectory = dir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            Show("启动失败：" + ex.Message, "Shinichiの练习小工具");
        }
    }

    static string FindPythonw(string dir)
    {
        string local = Path.Combine(dir, "pythonw.exe");
        if (File.Exists(local)) return local;

        string path = Environment.GetEnvironmentVariable("PATH");
        if (!String.IsNullOrEmpty(path))
        {
            foreach (string p in path.Split(';'))
            {
                if (p.Trim().Length == 0) continue;
                try
                {
                    string cand = Path.Combine(p.Trim(), "pythonw.exe");
                    if (File.Exists(cand)) return cand;
                }
                catch { }
            }
        }

        string la = Environment.GetEnvironmentVariable("LOCALAPPDATA");
        if (!String.IsNullOrEmpty(la))
        {
            string root = Path.Combine(la, "Programs", "Python");
            try
            {
                if (Directory.Exists(root))
                {
                    string best = null;
                    foreach (string d in Directory.GetDirectories(root))
                    {
                        string cand = Path.Combine(d, "pythonw.exe");
                        if (File.Exists(cand)) best = cand;
                    }
                    if (best != null) return best;
                }
            }
            catch { }
        }

        string[] roots = new string[] { @"SOFTWARE\Python\PythonCore", @"SOFTWARE\WOW6432Node\Python\PythonCore" };
        RegistryKey[] hives = new RegistryKey[] { Registry.CurrentUser, Registry.LocalMachine };
        foreach (RegistryKey hive in hives)
        {
            foreach (string r in roots)
            {
                try
                {
                    using (RegistryKey k = hive.OpenSubKey(r))
                    {
                        if (k == null) continue;
                        foreach (string ver in k.GetSubKeyNames())
                        {
                            using (RegistryKey ip = k.OpenSubKey(ver + @"\InstallPath"))
                            {
                                if (ip == null) continue;
                                string exe = ip.GetValue("ExecutablePath") as string;
                                if (!String.IsNullOrEmpty(exe) && File.Exists(exe))
                                {
                                    string pyw = Path.Combine(Path.GetDirectoryName(exe), "pythonw.exe");
                                    if (File.Exists(pyw)) return pyw;
                                    return exe;
                                }
                            }
                        }
                    }
                }
                catch { }
            }
        }
        return null;
    }

    static void Show(string text, string title)
    {
        MessageBox.Show(text, title, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
