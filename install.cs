#!/usr/bin/env dotnet
// install.cs — put this repo's opencode config in place on a machine.
//
//   ./install.cs --check     show what would change; exit 1 if anything would
//   ./install.cs             link everything into ~/.config/opencode
//   ./install.cs --copy      copy instead of link (one-way, for odd machines)
//
// Symlinks are the default so edits are live in both directions: there is one
// copy of each file, in this repo. Anything already sitting at a destination is
// MOVED to ~/.config/opencode.bak-<stamp> first — this script never deletes data.

using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;

// ---------------------------------------------------------------------------
// what we manage. Everything else in ~/.config/opencode is machine-local and
// deliberately left alone (see README.md).
// ---------------------------------------------------------------------------
string[] entries =
[
    "AGENTS.md",
    "opencode.json",
    "agents",
    "commands",
    "skills",
    "bin",
    "evals",
];

var repoRoot = ResolveRepoRoot();
var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
var targetRoot = Path.Combine(home, ".config", "opencode");

var checkOnly = args.Contains("--check");
var copyMode = args.Contains("--copy");

if (args.Contains("--help") || args.Contains("-h") || args.Contains("help"))
{
    Console.WriteLine("usage: ./install.cs [--check] [--copy] [--doctor]");
    return 0;
}

if (args.Contains("--doctor"))
    return RunDoctor(home, repoRoot);

string mode = copyMode ? "copy" : "link";
Console.WriteLine($"repo     {repoRoot}");
Console.WriteLine($"target   {targetRoot}");
Console.WriteLine($"platform {RuntimeInformation.OSDescription.Trim()}");
Console.WriteLine($"mode     {mode}{(checkOnly ? " (check only)" : "")}");
Console.WriteLine();

Directory.CreateDirectory(targetRoot);

List<string> drift = [];
string? backupRoot = null;
int failures = 0;

foreach (var name in entries)
{
    var src = Path.Combine(repoRoot, name);
    var dst = Path.Combine(targetRoot, name);
    var srcIsDir = Directory.Exists(src);

    if (!srcIsDir && !File.Exists(src))
    {
        Console.WriteLine($"  skip    {name} (not in repo)");
        continue;
    }

    var exists = TryAttrs(dst, out var attrs);
    var isLink = exists && IsLink(dst, attrs);
    var upToDate = copyMode
        ? exists && !isLink && CopiesMatch(src, dst, srcIsDir)
        : isLink && SameLinkTarget(dst, src);

    if (upToDate)
    {
        Console.WriteLine($"  ok      {name}");
        continue;
    }

    drift.Add(name);
    var action = !exists ? "create" : isLink ? "relink" : "replace";
    if (checkOnly)
    {
        Console.WriteLine($"  would   {action} {name}");
        continue;
    }

    try
    {
        // Preserve whatever is really there before we take the spot.
        if (exists && !isLink)
        {
            backupRoot ??= MakeBackupRoot();
            var bak = Path.Combine(backupRoot, name);
            Directory.CreateDirectory(Path.GetDirectoryName(bak)!);
            MovePath(dst, bak);
            Console.WriteLine($"  saved   {name} -> {Path.GetRelativePath(home, bak)}");
        }
        else if (isLink)
        {
            DeleteLink(dst);
        }

        if (copyMode)
        {
            CopyPath(src, dst, srcIsDir);
        }
        else
        {
            CreateLink(dst, src, srcIsDir);
        }

        Console.WriteLine($"  {action,-7} {name} -> {src}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"  FAILED  {name}: {ex.Message}");
        failures++;
    }
}

// ---------------------------------------------------------------------------
// verify: re-read the filesystem, don't trust the writes above
// ---------------------------------------------------------------------------
int broken = 0;
if (!checkOnly)
{
    Console.WriteLine();
    foreach (var name in entries)
    {
        var src = Path.Combine(repoRoot, name);
        var dst = Path.Combine(targetRoot, name);
        if (!Directory.Exists(src) && !File.Exists(src)) continue;

        var exists = TryAttrs(dst, out var attrs);
        var isLink = exists && IsLink(dst, attrs);
        var ok = copyMode
            ? exists && !isLink && CopiesMatch(src, dst, Directory.Exists(src))
            : isLink && SameLinkTarget(dst, src);

        if (!ok)
        {
            Console.WriteLine($"  BROKEN  {name}");
            broken++;
        }
    }

    if (broken == 0)
        Console.WriteLine("  all entries verified in place");
}

// ---------------------------------------------------------------------------
// environment checks that would otherwise fail silently on a new machine
// ---------------------------------------------------------------------------
Console.WriteLine();
var warnings = EnvironmentWarnings(targetRoot, home);
foreach (var w in warnings) Console.WriteLine($"  warn    {w}");
if (warnings.Count == 0) Console.WriteLine("  env     ok");

foreach (var local in new[] { "service.json", "cli.json", "reviews.jsonl" })
{
    if (File.Exists(Path.Combine(targetRoot, local)))
        Console.WriteLine($"  kept    {local} (machine-local, untracked)");
}

// ---------------------------------------------------------------------------
Console.WriteLine();
if (failures > 0 || broken > 0)
{
    Console.WriteLine($"failed ({failures + broken} problem(s))");
    return 2;
}
if (checkOnly && drift.Count > 0)
{
    Console.WriteLine($"{drift.Count} path(s) would change — run ./install.cs to apply");
    return 1;
}
Console.WriteLine(checkOnly ? "nothing to do" : $"done ({drift.Count} path(s) changed)");
return 0;

// ===========================================================================
// helpers
// ===========================================================================

static string ResolveRepoRoot([System.Runtime.CompilerServices.CallerFilePath] string source = "")
{
    // A file-based app runs from a shadow build directory, so neither the process
    // path nor argv[0] points at install.cs — CallerFilePath is baked in at
    // compile time and is the only reliable anchor. This matters because the
    // script must work when invoked by absolute path from any directory.
    if (!string.IsNullOrEmpty(source))
    {
        var fromSource = Path.GetDirectoryName(Path.GetFullPath(source));
        if (fromSource is not null && File.Exists(Path.Combine(fromSource, "install.cs")))
            return fromSource;
    }

    var dir = Directory.GetCurrentDirectory();
    while (dir is not null)
    {
        if (File.Exists(Path.Combine(dir, "install.cs"))) return dir;
        dir = Path.GetDirectoryName(dir);
    }

    throw new InvalidOperationException("cannot locate repo root (no install.cs next to the script)");
}

static bool TryAttrs(string path, out FileAttributes attrs)
{
    try
    {
        attrs = File.GetAttributes(path); // lstat: reports ReparsePoint even if broken
        return true;
    }
    catch (Exception e) when (e is FileNotFoundException or DirectoryNotFoundException)
    {
        attrs = default;
        return false;
    }
}

static bool IsLink(string path, FileAttributes attrs) =>
    attrs.HasFlag(FileAttributes.ReparsePoint) || LinkTargetOf(path) is not null;

static string? LinkTargetOf(string path)
{
    try { return new FileInfo(path).LinkTarget; } catch { }
    try { return new DirectoryInfo(path).LinkTarget; } catch { }
    return null;
}

static bool SameLinkTarget(string dst, string src)
{
    var target = LinkTargetOf(dst);
    if (target is null) return false;

    var resolved = Path.GetFullPath(target, Path.GetDirectoryName(dst)!);
    return string.Equals(
        Path.TrimEndingDirectorySeparator(resolved),
        Path.TrimEndingDirectorySeparator(Path.GetFullPath(src)),
        StringComparison.Ordinal);
}

static void CreateLink(string dst, string src, bool isDir)
{
    if (isDir) Directory.CreateSymbolicLink(dst, src);
    else File.CreateSymbolicLink(dst, src);
}

static void DeleteLink(string path)
{
    // non-recursive delete removes the link itself, never what it points at
    if (Directory.Exists(path)) Directory.Delete(path);
    else File.Delete(path);
}

static void MovePath(string from, string to)
{
    if (Directory.Exists(from)) Directory.Move(from, to);
    else File.Move(from, to);
}

static void CopyPath(string from, string to, bool isDir)
{
    if (isDir)
    {
        foreach (var file in Directory.EnumerateFiles(from, "*", SearchOption.AllDirectories))
        {
            var rel = Path.GetRelativePath(from, file);
            var dest = Path.Combine(to, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
            File.Copy(file, dest, overwrite: true);
        }
    }
    else
    {
        File.Copy(from, to, overwrite: true);
    }
}

static bool CopiesMatch(string src, string dst, bool isDir)
{
    if (isDir)
    {
        if (!Directory.Exists(dst)) return false;
        var a = Directory.EnumerateFiles(src, "*", SearchOption.AllDirectories)
            .Select(f => Path.GetRelativePath(src, f)).Order().ToArray();
        var b = Directory.EnumerateFiles(dst, "*", SearchOption.AllDirectories)
            .Select(f => Path.GetRelativePath(dst, f)).Order().ToArray();
        return a.SequenceEqual(b);
    }

    if (!File.Exists(dst)) return false;
    var sa = new FileInfo(src);
    var sb = new FileInfo(dst);
    return sa.Length == sb.Length && sa.LastWriteTimeUtc == sb.LastWriteTimeUtc;
}

static string MakeBackupRoot()
{
    var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    var stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
    var root = Path.Combine(home, ".config", $"opencode.bak-{stamp}");
    Directory.CreateDirectory(root);
    return root;
}

static List<string> EnvironmentWarnings(string targetRoot, string home)
{
    List<string> warnings = [];

    // opencode.json is symlinked straight from the repo, so any absolute path in
    // it is shared by every machine. Substituting {env:HOME} first means the
    // check is about this machine, not the one the config was written on.
    var configPath = Path.Combine(targetRoot, "opencode.json");
    if (File.Exists(configPath))
    {
        var text = File.ReadAllText(configPath).Replace("{env:HOME}", home);
        foreach (var m in System.Text.RegularExpressions.Regex.Matches(text, "\"(/[^\"\\s]+)\"").Cast<System.Text.RegularExpressions.Match>())
        {
            var path = m.Groups[1].Value;
            if (!File.Exists(path) && !Directory.Exists(path))
                warnings.Add($"opencode.json refers to {path}, which does not exist here");
        }
    }

    // roslynk MCP server must be resolvable; on a fresh machine ~/.dotnet/tools
    // is only on PATH after the shell rc file is sourced.
    if (!File.Exists(Path.Combine(home, ".dotnet", "tools", "roslynk")))
        warnings.Add("~/.dotnet/tools/roslynk missing — run: dotnet tool install -g roslynk");

    return warnings;
}

// ---------------------------------------------------------------------------
// --doctor: what a fresh machine needs before any of this works
// ---------------------------------------------------------------------------
static int RunDoctor(string home, string repoRoot)
{
    var isArch = File.Exists("/etc/arch-release");
    var isMac = OperatingSystem.IsMacOS();
    var toolsDir = Path.Combine(home, ".dotnet", "tools");
    var blocking = 0;
    var advisory = 0;

    void Check(string what, Func<bool> probe, string hint, bool required)
    {
        bool ok;
        try { ok = probe(); } catch { ok = false; }

        // "required" gates the exit code; the rest are recommendations. A missing
        // opencode or roslynk makes the config useless but still installs fine, so
        // treating it as fatal would block a perfectly good install.
        Console.WriteLine($"  {(ok ? "ok      " : required ? "MISSING " : "note    ")} {what}");
        if (ok) return;

        if (required) blocking++; else advisory++;
        Console.WriteLine($"           -> {hint}");
    }

    Console.WriteLine($"platform {RuntimeInformation.OSDescription.Trim()}");
    Console.WriteLine($"home     {home}");
    Console.WriteLine();
    Console.WriteLine("prerequisites");

    Check($"dotnet SDK 10+ (found {DotnetVersion()})",
        () => DotnetVersion() >= new Version(10, 0),
        isArch ? "sudo pacman -S --needed dotnet-sdk"
               : isMac ? "brew install --cask dotnet-sdk"
                       : "install the .NET 10 SDK",
        required: true);

    Check("python3", () => OnPath("python3"),
        isArch ? "sudo pacman -S --needed python" : "install python3",
        required: true);

    Check("git", () => OnPath("git"),
        isArch ? "sudo pacman -S --needed git" : "install git",
        required: true);

    // CI lints with shellcheck; a machine without it cannot reproduce the build.
    Check("shellcheck (CI lints with it)", () => OnPath("shellcheck"),
        isMac ? "brew install shellcheck"
              : isArch ? "sudo pacman -S --needed shellcheck"
                       : "sudo apt-get install -y shellcheck",
        required: false);

    // .NET needs the system ICU on Linux and dotnetup installs no system dependencies.
    // Blocking because a missing ICU makes .NET apps fail, not just warnings.
    if (!OperatingSystem.IsMacOS())
    {
        Check("icu (.NET runtime dependency)", HasIcu,
            isArch ? "sudo pacman -S --needed icu" : "sudo apt-get install -y libicu-dev",
            required: true);
    }

    Check("opencode", () => OnPath("opencode"), "install opencode, then re-run",
        required: false);

    // A Claude subscription reaches opencode through the Claude Agent integration,
    // which borrows the local Claude Code login instead of an API key. Neither is
    // needed by the rest of the config, so both checks are advisory.
    Check("claude CLI (Claude subscription via Claude Agent)",
        () => OnPath("claude"),
        "install Claude Code, then run: claude auth login",
        required: false);

    if (OnPath("claude"))
    {
        Check("claude login (opencode Claude Agent)",
            () => ClaudeLoggedIn() == true,
            "claude auth login",
            required: false);
    }

    // A global tool's version is not visible to Dependabot, so tools.json pins it and
    // the scheduled tools workflow compares that pin to NuGet. Compare here too, or the
    // pin is decorative.
    var pinned = PinnedRoslynkVersion(repoRoot);
    var installedRoslynk = InstalledRoslynkVersion(home);

    if (pinned is null)
    {
        Check("roslynk tool", () => File.Exists(Path.Combine(toolsDir, "roslynk")),
            "dotnet tool install -g roslynk",
            required: false);
    }
    else
    {
        Check($"roslynk {pinned} (pin; installed {installedRoslynk ?? "none"})",
            () => installedRoslynk == pinned,
            installedRoslynk is null
                ? $"dotnet tool install -g roslynk --version {pinned}"
                : $"dotnet tool update -g roslynk --version {pinned}",
            required: false);
    }

    // Aspire is a project tool, not a config prerequisite, so it is advisory.
    // Read the bundle version file rather than executing a 182 MB binary.
    var aspireVersion = AspireBundleVersion(home);
    Check($"aspire bundle{(aspireVersion is null ? "" : $" ({aspireVersion})")}",
        () => aspireVersion is not null || OnPath("aspire"),
        "curl -sSL https://aspire.dev/install.sh | bash",
        required: false);

    // The Roslynk package ships no skill, so setup.sh restores it from the tag.
    Check("roslynk skill in ~/.agents/skills",
        () => File.Exists(Path.Combine(home, ".agents", "skills", "roslynk", "SKILL.md")),
        "re-run ./setup.sh to restore it from the pinned tag",
        required: false);

    Check("~/.dotnet/tools on PATH",
        () => (Environment.GetEnvironmentVariable("PATH") ?? "")
            .Split(Path.PathSeparator)
            .Any(d => string.Equals(
                Path.TrimEndingDirectorySeparator(d.Replace("~", home)),
                Path.TrimEndingDirectorySeparator(toolsDir),
                StringComparison.Ordinal)),
        ShellRcHint(home),
        required: false);

    Console.WriteLine();
    if (blocking == 0)
    {
        Console.WriteLine(advisory == 0
            ? "all prerequisites present"
            : $"usable — {advisory} recommendation(s) above");
        return 0;
    }

    Console.WriteLine($"{blocking} blocking prerequisite(s) missing — fix the lines above");
    return 1;
}

static string ShellRcHint(string home)
{
    // Omarchy/Arch users land in zsh or bash; macOS uses .zprofile because the
    // GUI does not read .zshrc. Pick whichever file actually exists.
    var zshrc = Path.Combine(home, ".zshrc");
    var bashrc = Path.Combine(home, ".bashrc");
    var profile = Path.Combine(home, ".zprofile");

    var target = OperatingSystem.IsMacOS() && File.Exists(profile) ? profile
        : File.Exists(bashrc) && !File.Exists(zshrc) ? bashrc
        : zshrc;

    return $"add to {target}: export PATH=\"$PATH:$HOME/.dotnet/tools\"";
}

static Version DotnetVersion()
{
    var (code, output) = RunCapture("dotnet", "--version");
    var firstLine = output.Split('\n').FirstOrDefault(l => l.Trim().Length > 0)?.Trim();
    return code == 0 && Version.TryParse(firstLine, out var v) ? v : new Version(0, 0);
}

static bool OnPath(string exe)
{
    var path = Environment.GetEnvironmentVariable("PATH") ?? "";
    foreach (var dir in path.Split(Path.PathSeparator))
    {
        if (string.IsNullOrWhiteSpace(dir)) continue;
        if (File.Exists(Path.Combine(dir, exe))) return true;
    }
    return false;
}

static bool HasIcu()
{
    // .NET binds libicuuc; the soname lives in different directories per distro/arch.
    foreach (var dir in new[]
    {
        "/usr/lib", "/usr/lib64", "/lib", "/lib64",
        "/usr/lib/aarch64-linux-gnu", "/usr/lib/x86_64-linux-gnu",
    })
    {
        if (!Directory.Exists(dir)) continue;
        if (Directory.EnumerateFiles(dir, "libicuuc.so*").Any()) return true;
    }
    return false;
}

static string? AspireBundleVersion(string home)
{
    // Format: "13.6.1+<sha>|<bytes>|<ticks>"
    var path = Path.Combine(home, ".aspire", ".aspire-bundle-version");
    if (!File.Exists(path)) return null;

    var text = File.ReadAllText(path).Trim();
    var cut = text.IndexOfAny(new[] { '|', '+' });
    return cut > 0 ? text[..cut] : text;
}

static string? PinnedRoslynkVersion(string repoRoot)
{
    var path = Path.Combine(repoRoot, "tools.json");
    if (!File.Exists(path)) return null;

    var m = System.Text.RegularExpressions.Regex.Match(
        File.ReadAllText(path), "\"roslynk\"\\s*:\\s*\"([^\"]+)\"");
    return m.Success ? m.Groups[1].Value : null;
}

static string? InstalledRoslynkVersion(string home)
{
    // A global tool's version lives in its .store directory. `roslynk --version` starts
    // the daemon and fails, so read the directory rather than executing the tool.
    var store = Path.Combine(home, ".dotnet", "tools", ".store", "roslynk");
    if (!Directory.Exists(store)) return null;

    return Directory.GetDirectories(store)
        .Select(d => Path.GetFileName(d))
        .Where(v => Version.TryParse(v, out _))
        .OrderByDescending(v => Version.Parse(v))
        .FirstOrDefault();
}

static bool? ClaudeLoggedIn()
{
    // `claude auth status` prints a JSON object. Parse it rather than matching a
    // formatted substring: a spacing or key-order change must not flip the answer.
    // A missing CLI, a CLI without this subcommand, a non-zero exit or unparsable
    // output is null, which the doctor reports as "not logged in" instead of
    // crashing or claiming success.
    var (code, output) = RunCapture("claude", "auth status");
    if (code != 0) return null;

    // RunCapture merges stdout and stderr, so slice the outermost braces to ignore
    // any warning text around the object.
    var start = output.IndexOf('{');
    var end = output.LastIndexOf('}');
    if (start < 0 || end <= start) return null;

    try
    {
        using var status = JsonDocument.Parse(output[start..(end + 1)]);
        return status.RootElement.ValueKind == JsonValueKind.Object
            && status.RootElement.TryGetProperty("loggedIn", out var loggedIn)
            && loggedIn.ValueKind == JsonValueKind.True;
    }
    catch (JsonException)
    {
        return null;
    }
}

static (int Code, string Output) RunCapture(string file, string arguments)
{
    try
    {
        using var p = Process.Start(new ProcessStartInfo(file, arguments)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        })!;

        var output = p.StandardOutput.ReadToEnd() + p.StandardError.ReadToEnd();
        p.WaitForExit(15000);
        return (p.HasExited ? p.ExitCode : -1, output);
    }
    catch
    {
        return (-1, "");
    }
}
