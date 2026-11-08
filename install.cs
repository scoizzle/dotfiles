#!/usr/bin/env dotnet
// install.cs — put this repo's opencode config in place on a machine.
//
//   ./install.cs --check     show what would change; exit 1 if anything would
//   ./install.cs             link everything into ~/.config/opencode
//   ./install.cs --copy      copy instead of link (one-way, for odd machines)
//   ./install.cs --home DIR  install under DIR instead of $HOME (tests, sandboxes)
//
// memory/ is not linked into the repo: ~/.config/opencode/.memory is a sparse git
// clone of this repo (only /memory/ and /.gitignore) and ~/.config/opencode/memory
// is a symlink to .memory/memory, so agent-written learnings can be committed from
// there and a deleted checkout loses nothing.
// --memory-remote URL (or MEMORY_REMOTE) overrides the clone source; the default
// is this repo's origin.
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
    "plugins",
    "evals",
];

var homeFlag = Array.IndexOf(args, "--home");
if (homeFlag >= 0 && (homeFlag + 1 >= args.Length || args[homeFlag + 1].StartsWith('-')))
{
    Console.WriteLine("  FAILED  --home needs a directory value (not falling back to the real home)");
    return 2;
}

var memoryRemoteFlag = Array.IndexOf(args, "--memory-remote");
if (memoryRemoteFlag >= 0 && (memoryRemoteFlag + 1 >= args.Length || args[memoryRemoteFlag + 1].StartsWith('-')))
{
    Console.WriteLine("  FAILED  --memory-remote needs a URL value (not falling back to MEMORY_REMOTE or origin)");
    return 2;
}

var repoRoot = ResolveRepoRoot();
var home = Path.GetFullPath(
    ArgValue("--home")
    ?? (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("HOME")) ? null : Environment.GetEnvironmentVariable("HOME"))
    ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
var targetRoot = Path.Combine(home, ".config", "opencode");

// Links outside ~/.config/opencode, home-relative destination -> repo path. Claude Code
// reads ~/.claude/CLAUDE.md and Grok Build reads ~/.grok/AGENTS.md, so all three
// harnesses load the one AGENTS.md. Skills and commands go to
// ~/.claude/{skills,commands}, which Claude Code reads and Grok Build reads through
// its Claude compatibility layer. These are always symlinks, even with --copy: they
// exist to be shared. New skills and commands are picked up on the next run.
var homeEntries = new List<(string Dest, string Src, bool IsDir)>
{
    (Path.Combine(".claude", "CLAUDE.md"), "AGENTS.md", false),
    (Path.Combine(".grok", "AGENTS.md"), "AGENTS.md", false),
};
if (Directory.Exists(Path.Combine(repoRoot, "skills")))
    foreach (var dir in Directory.GetDirectories(Path.Combine(repoRoot, "skills")).OrderBy(d => d, StringComparer.Ordinal))
        homeEntries.Add((Path.Combine(".claude", "skills", Path.GetFileName(dir)), Path.Combine("skills", Path.GetFileName(dir)), true));
if (Directory.Exists(Path.Combine(repoRoot, "commands")))
    foreach (var file in Directory.GetFiles(Path.Combine(repoRoot, "commands"), "*.md").OrderBy(f => f, StringComparer.Ordinal))
        homeEntries.Add((Path.Combine(".claude", "commands", Path.GetFileName(file)), Path.Combine("commands", Path.GetFileName(file)), false));

string? ArgValue(string name)
{
    var i = Array.IndexOf(args, name);
    return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
}

var checkOnly = args.Contains("--check");
var copyMode = args.Contains("--copy");

if (args.Contains("--help") || args.Contains("-h") || args.Contains("help"))
{
    Console.WriteLine("usage: ./install.cs [--check] [--copy] [--doctor] [--home DIR] [--memory-remote URL]");
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
            backupRoot ??= MakeBackupRoot(home);
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

{
    var memory = ProvisionMemory(home, targetRoot, repoRoot, ArgValue("--memory-remote"), checkOnly, ref backupRoot);
    if (memory.Drift) drift.Add("memory");
    if (memory.Failed) failures++;
}

foreach (var (rel, srcName, isDirEntry) in homeEntries)
{
    var src = Path.Combine(repoRoot, srcName);
    var dst = Path.Combine(home, rel);
    var label = "~/" + rel;
    if (!(isDirEntry ? Directory.Exists(src) : File.Exists(src)))
    {
        Console.WriteLine($"  skip    {label} ({srcName} not in repo)");
        continue;
    }

    var exists = TryAttrs(dst, out var attrs);
    var isLink = exists && IsLink(dst, attrs);
    if (isLink && SameLinkTarget(dst, src))
    {
        Console.WriteLine($"  ok      {label}");
        continue;
    }

    drift.Add(label);
    var action = !exists ? "create" : isLink ? "relink" : "replace";
    if (checkOnly)
    {
        Console.WriteLine($"  would   {action} {label}");
        continue;
    }

    try
    {
        Directory.CreateDirectory(Path.GetDirectoryName(dst)!);
        if (exists && !isLink)
        {
            backupRoot ??= MakeBackupRoot(home);
            var bak = Path.Combine(backupRoot, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(bak)!);
            MovePath(dst, bak);
            Console.WriteLine($"  saved   {label} -> {Path.GetRelativePath(home, bak)}");
        }
        else if (isLink)
        {
            DeleteLink(dst);
        }

        CreateLink(dst, src, isDir: isDirEntry);
        Console.WriteLine($"  {action,-7} {label} -> {src}");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"  FAILED  {label}: {ex.Message}");
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

    if (!VerifyMemory(targetRoot))
    {
        Console.WriteLine("  BROKEN  memory");
        broken++;
    }

    foreach (var (rel, srcName, isDirEntry) in homeEntries)
    {
        var src = Path.Combine(repoRoot, srcName);
        if (!(isDirEntry ? Directory.Exists(src) : File.Exists(src))) continue;

        var dst = Path.Combine(home, rel);
        var exists = TryAttrs(dst, out var attrs);
        if (!(exists && IsLink(dst, attrs) && SameLinkTarget(dst, src)))
        {
            Console.WriteLine($"  BROKEN  ~/{rel}");
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

static string MakeBackupRoot(string home)
{
    var stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
    var root = Path.Combine(home, ".config", $"opencode.bak-{stamp}");
    // two installs inside one second must not share (and clobber) a backup
    for (var n = 2; Directory.Exists(root); n++)
        root = Path.Combine(home, ".config", $"opencode.bak-{stamp}-{n}");
    Directory.CreateDirectory(root);
    return root;
}

// ---------------------------------------------------------------------------
// memory: ~/.config/opencode/.memory is a sparse git clone of this repo; the
// managed path ~/.config/opencode/memory is a symlink to .memory/memory.
// ---------------------------------------------------------------------------
static string MigratingMarkerName() => ".migrating";

static string MemoryCloneName() => ".memory";
static string MemoryLinkTarget() => ".memory/memory";

static string? ResolveMemoryRemote(string repoRoot, string? arg)
{
    if (!string.IsNullOrWhiteSpace(arg)) return arg.Trim();
    var env = Environment.GetEnvironmentVariable("MEMORY_REMOTE");
    if (!string.IsNullOrWhiteSpace(env)) return env.Trim();
    return Git(repoRoot, 15000, "remote", "get-url", "origin");
}

static (int Code, string Out, string Err) RunGit(string? workdir, int timeoutMs, params string[] gitArgs)
{
    try
    {
        var psi = new ProcessStartInfo("git")
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            UseShellExecute = false,
        };
        if (workdir is not null) { psi.ArgumentList.Add("-C"); psi.ArgumentList.Add(workdir); }
        foreach (var a in gitArgs) psi.ArgumentList.Add(a);
        psi.Environment["GIT_TERMINAL_PROMPT"] = "0";

        using var p = Process.Start(psi)!;
        p.StandardInput.Close();
        var so = p.StandardOutput.ReadToEndAsync();
        var se = p.StandardError.ReadToEndAsync();
        if (!p.WaitForExit(timeoutMs))
        {
            try { p.Kill(entireProcessTree: true); } catch { }
            return (-1, "", $"git {string.Join(' ', gitArgs)} timed out after {timeoutMs / 1000}s");
        }
        p.WaitForExit();
        return (p.ExitCode, so.Result, se.Result);
    }
    catch (Exception ex)
    {
        return (-1, "", ex.Message);
    }
}

static string? Git(string dir, int timeoutMs, params string[] gitArgs)
{
    var (code, o, _) = RunGit(dir, timeoutMs, gitArgs);
    return code == 0 ? o.Trim() : null;
}

static bool SameRemote(string a, string b)
{
    static string Norm(string s)
    {
        s = s.Trim();
        if (Directory.Exists(s)) s = Path.GetFullPath(s);
        return s.TrimEnd('/');
    }
    return string.Equals(Norm(a), Norm(b), StringComparison.Ordinal);
}

static bool HasDotGit(string dir) =>
    Directory.Exists(Path.Combine(dir, ".git")) || File.Exists(Path.Combine(dir, ".git"));

static bool IsCloneDir(string dest) =>
    Directory.Exists(dest)
    && !(TryAttrs(dest, out var attrs) && IsLink(dest, attrs))
    && HasDotGit(dest)
    && Git(dest, 15000, "rev-parse", "--is-inside-work-tree") == "true";

static HashSet<string> SparsePatterns(string dest) =>
    Git(dest, 15000, "sparse-checkout", "list") is { } list
        ? list.Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0).ToHashSet()
        : [];

// Both patterns are part of the clone's contract: /memory/ holds the data and
// /.gitignore keeps dream's pending/ files out of `git status`.
static bool SparseHasPatterns(string dest)
{
    var set = SparsePatterns(dest);
    return set.Contains("/memory/") && set.Contains("/.gitignore");
}

// Where learnings live inside a memory source: <src>/memory/learnings when the
// source is a clone (or repo root), <src>/learnings when it is a memory/ dir.
static string LearningsDirOf(string source)
{
    var nested = Path.Combine(source, "memory", "learnings");
    return Directory.Exists(nested) ? nested : Path.Combine(source, "learnings");
}

static bool MemoryLinkOk(string targetRoot)
{
    var link = Path.Combine(targetRoot, "memory");
    return TryAttrs(link, out var attrs) && IsLink(link, attrs)
        && SameLinkTarget(link, Path.Combine(targetRoot, MemoryCloneName(), "memory"));
}

static bool VerifyMemory(string targetRoot)
{
    var clone = Path.Combine(targetRoot, MemoryCloneName());
    if (!IsCloneDir(clone)) return false;
    if (!SparseHasPatterns(clone)) return false;
    if (!File.Exists(Path.Combine(clone, "memory", "INDEX.md"))) return false;
    return MemoryLinkOk(targetRoot) && File.Exists(Path.Combine(targetRoot, "memory", "INDEX.md"));
}

static (bool Drift, bool Failed) ProvisionMemory(
    string home, string targetRoot, string repoRoot, string? remoteArg, bool checkOnly, ref string? backupRoot)
{
    var remote = ResolveMemoryRemote(repoRoot, remoteArg);
    if (remote is null)
    {
        Console.WriteLine("  FAILED  memory: no clone remote — pass --memory-remote <url>, set MEMORY_REMOTE, or give this repo an 'origin' remote");
        return (false, true);
    }

    var clone = ProvisionMemoryClone(home, targetRoot, remote, checkOnly, ref backupRoot);
    if (clone.Failed) return (clone.Drift, true);

    var link = ProvisionMemoryLink(home, targetRoot, checkOnly, ref backupRoot);
    if (link.Failed) return (clone.Drift || link.Drift, true);

    var pending = FinishInterruptedMigrations(home, Path.Combine(targetRoot, MemoryCloneName()), checkOnly);
    return (clone.Drift || link.Drift || pending > 0, false);
}

// The clone at <targetRoot>/.memory: create, verify, or repair its sparse set.
static (bool Drift, bool Failed) ProvisionMemoryClone(
    string home, string targetRoot, string remote, bool checkOnly, ref string? backupRoot)
{
    var dest = Path.Combine(targetRoot, MemoryCloneName());
    var exists = TryAttrs(dest, out _);

    if (exists && IsCloneDir(dest))
        return ReconcileMemoryClone(dest, remote, checkOnly);

    // A .git that git cannot read is not "no clone": replacing it could destroy history.
    if (exists && HasDotGit(dest) && !(TryAttrs(dest, out var da) && IsLink(dest, da)))
    {
        Console.WriteLine($"  FAILED  memory: {dest} has a .git that git cannot read; fix or move it manually");
        return (false, true);
    }

    if (checkOnly)
    {
        Console.WriteLine($"  would create memory (clone {remote})");
        return (true, false);
    }

    // Clone beside the destination first, so a failed clone never costs an existing
    // directory its place.
    var tmp = Path.Combine(targetRoot, $".memory-clone-{Environment.ProcessId}");
    string? movedBak = null;
    try
    {
        if (Directory.Exists(tmp)) Directory.Delete(tmp, recursive: true);

        void Step(int timeoutMs, params string[] gitArgs)
        {
            var (code, _, err) = RunGit(null, timeoutMs, gitArgs);
            if (code != 0) throw new InvalidOperationException($"git {string.Join(' ', gitArgs)}: {err.Trim()}");
        }

        Step(60000, "clone", "--no-checkout", remote, tmp);
        // The repo's root .gitignore rides along: dream writes into memory/learnings/pending/,
        // and without it the clone sees those files as untracked.
        Step(60000, "-C", tmp, "sparse-checkout", "set", "--no-cone", "/memory/", "/.gitignore");
        Step(60000, "-C", tmp, "checkout");
        if (!File.Exists(Path.Combine(tmp, "memory", "INDEX.md")))
            throw new InvalidOperationException($"{remote} has no memory/INDEX.md on its checked-out branch");

        if (exists)
        {
            backupRoot ??= MakeBackupRoot(home);
            var bak = Path.Combine(backupRoot, "memory-src");
            MovePath(dest, bak);
            movedBak = bak;
            Console.WriteLine($"  saved   {MemoryCloneName()} -> {Path.GetRelativePath(home, bak)}");
        }

        Directory.Move(tmp, dest);
        Console.WriteLine($"  create  memory (clone {remote})");
        return (true, false);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"  FAILED  memory: {ex.Message}");
        try { if (Directory.Exists(tmp)) Directory.Delete(tmp, recursive: true); } catch { }
        if (movedBak is not null)
        {
            try
            {
                if (!TryAttrs(dest, out _))
                {
                    MovePath(movedBak, dest);
                    Console.WriteLine($"  restore {MemoryCloneName()} (rolled back from {movedBak})");
                }
            }
            catch (Exception rex)
            {
                Console.WriteLine($"  FAILED  memory: rollback failed ({rex.Message}); the old {MemoryCloneName()} is at {movedBak}");
            }
        }
        return (true, true);
    }
}

// The managed path <targetRoot>/memory: a relative symlink to .memory/memory.
// Whatever sits there instead is moved to the backup and its learnings copied in.
static (bool Drift, bool Failed) ProvisionMemoryLink(
    string home, string targetRoot, bool checkOnly, ref string? backupRoot)
{
    var link = Path.Combine(targetRoot, "memory");
    var exists = TryAttrs(link, out var attrs);
    var isLink = exists && IsLink(link, attrs);

    if (MemoryLinkOk(targetRoot))
    {
        Console.WriteLine("  ok memory (link)");
        return (false, false);
    }

    if (checkOnly)
    {
        Console.WriteLine(exists
            ? "  would link memory (existing memory is moved to the backup)"
            : "  would link memory");
        return (true, false);
    }

    var cloneDir = Path.Combine(targetRoot, MemoryCloneName());
    string? movedBak = null;      // old memory file/directory now sitting in the backup
    string? linkRestore = null;   // old memory symlink target, removed from link
    string? markerPath = null;
    string? migrateFrom = null;
    var danglingLink = false;
    var committed = false;
    try
    {
        if (exists)
        {
            backupRoot ??= MakeBackupRoot(home);
            if (isLink)
            {
                var raw = LinkTargetOf(link)!;
                File.WriteAllText(Path.Combine(backupRoot, "memory.link-target"), raw + "\n");
                var resolved = Path.GetFullPath(raw, targetRoot);
                danglingLink = !Directory.Exists(resolved);
                migrateFrom = LearningsDirOf(resolved);
                markerPath = Path.Combine(backupRoot, "memory", MigratingMarkerName());
                if (!danglingLink)
                {
                    // The marker records where the learnings live, so a later run can finish the copy.
                    Directory.CreateDirectory(Path.GetDirectoryName(markerPath)!);
                    File.WriteAllText(markerPath, migrateFrom + "\n");
                }
                DeleteLink(link); // the link only, never what it points at
                linkRestore = raw;
                Console.WriteLine($"  saved   memory link target -> {Path.GetRelativePath(home, Path.Combine(backupRoot, "memory.link-target"))}");
            }
            else
            {
                var bak = Path.Combine(backupRoot, "memory");
                if (Directory.Exists(link))
                {
                    markerPath = Path.Combine(bak, MigratingMarkerName());
                    // Written inside the old memory first so it travels into the backup with the move.
                    File.WriteAllText(Path.Combine(link, MigratingMarkerName()), "");
                }
                var wasDir = Directory.Exists(link);
                MovePath(link, bak);
                movedBak = bak;
                if (wasDir) migrateFrom = LearningsDirOf(bak);
                Console.WriteLine($"  saved   memory -> {Path.GetRelativePath(home, bak)}");
            }
        }

        CreateLink(link, MemoryLinkTarget(), isDir: true);
        committed = true; // the link is live; a failure from here is finished by the next run
        Console.WriteLine($"  link    memory -> {MemoryLinkTarget()}");

        if (danglingLink)
            Console.WriteLine("  warn    memory was a dangling symlink; nothing to migrate");
        else if (migrateFrom is not null)
            MigrateLearnings(migrateFrom, Path.Combine(cloneDir, "memory", "learnings"));

        if (markerPath is not null && File.Exists(markerPath)) File.Delete(markerPath);
        return (true, false);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"  FAILED  memory: {ex.Message}");
        if (committed) return (true, true);
        try
        {
            var destFree = !TryAttrs(link, out _);
            if (movedBak is not null && destFree)
            {
                MovePath(movedBak, link);
                var stray = Path.Combine(link, MigratingMarkerName());
                if (File.Exists(stray)) File.Delete(stray);
                Console.WriteLine($"  restore memory (rolled back from {movedBak})");
            }
            else if (linkRestore is not null && destFree)
            {
                CreateLink(link, linkRestore, true);
                if (markerPath is not null && File.Exists(markerPath)) File.Delete(markerPath);
                Console.WriteLine("  restore memory (symlink recreated)");
            }
            else if (movedBak is not null)
            {
                Console.WriteLine($"  FAILED  memory: could not restore; the old memory is at {movedBak}");
            }
        }
        catch (Exception rex)
        {
            Console.WriteLine($"  FAILED  memory: rollback failed ({rex.Message}); the old memory is at {movedBak ?? markerPath}");
        }
        return (true, true);
    }
}

// Finishes learnings copies that a previous run began and did not complete. Each
// opencode.bak-*/memory/.migrating marker names (first line) the learnings source,
// defaulting to the backup's own learnings. Idempotent; copies never clobber.
static int FinishInterruptedMigrations(string home, string cloneDir, bool checkOnly)
{
    var configDir = Path.Combine(home, ".config");
    if (!Directory.Exists(configDir)) return 0;
    var done = 0;
    foreach (var bak in Directory.GetDirectories(configDir, "opencode.bak-*").OrderBy(d => d, StringComparer.Ordinal))
    {
        var marker = Path.Combine(bak, "memory", MigratingMarkerName());
        if (!File.Exists(marker)) continue;
        done++;
        if (checkOnly)
        {
            Console.WriteLine($"  would finish interrupted memory migration ({Path.GetRelativePath(home, bak)})");
            continue;
        }
        try
        {
            var first = File.ReadLines(marker).FirstOrDefault()?.Trim();
            var from = string.IsNullOrEmpty(first) ? LearningsDirOf(Path.Combine(bak, "memory")) : first;
            Console.WriteLine($"  resume  interrupted memory migration ({Path.GetRelativePath(home, bak)})");
            MigrateLearnings(from, Path.Combine(cloneDir, "memory", "learnings"));
            File.Delete(marker);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"  warn    could not finish migration from {bak}: {ex.Message}");
        }
    }
    return done;
}

static (bool Drift, bool Failed) ReconcileMemoryClone(string dest, string remote, bool checkOnly)
{
    var origin = Git(dest, 15000, "remote", "get-url", "origin");
    if (origin is null || !SameRemote(origin, remote))
    {
        Console.WriteLine($"  FAILED  memory: origin is '{origin ?? "(none)"}', expected '{remote}' — not repointing; fix or remove it by hand");
        return (false, true);
    }
    var sparse = SparsePatterns(dest);
    if (!sparse.Contains("/memory/"))
    {
        Console.WriteLine("  FAILED  memory: sparse-checkout does not contain /memory/");
        return (false, true);
    }
    // A clone that predates the /.gitignore pattern (or lost it) is repaired as
    // drift, not a failure. Never reset, clean, or switch its branch, and never fetch.
    var sparseDrift = !sparse.Contains("/.gitignore");
    if (sparseDrift)
    {
        if (checkOnly)
        {
            Console.WriteLine("  would repair memory (sparse set)");
            return (true, false);
        }
        var (code, _, err) = RunGit(dest, 60000, "sparse-checkout", "set", "--no-cone", "/memory/", "/.gitignore");
        if (code != 0 || !SparseHasPatterns(dest))
        {
            Console.WriteLine($"  FAILED  memory: cannot repair the sparse set: {err.Trim()}");
            return (false, true);
        }
        Console.WriteLine("  repair  memory (sparse set)");
    }
    if (!File.Exists(Path.Combine(dest, "memory", "INDEX.md")))
    {
        Console.WriteLine("  FAILED  memory: memory/INDEX.md is missing from the clone");
        return (false, true);
    }

    if (!sparseDrift) Console.WriteLine("  ok memory (clone)");
    return (sparseDrift, false);
}

// Copies learnings/** (dated, pending, working.md) without clobbering. The source
// is never moved or deleted: for a directory it already sits in the backup, for a
// symlink it is wherever the link pointed.
static void MigrateLearnings(string from, string to)
{
    if (!Directory.Exists(from))
    {
        Console.WriteLine($"  warn    nothing to migrate: {from} does not exist");
        return;
    }

    var copied = 0;
    foreach (var file in Directory.EnumerateFiles(from, "*", SearchOption.AllDirectories).OrderBy(f => f, StringComparer.Ordinal))
    {
        var rel = Path.GetRelativePath(from, file);
        var name = Path.GetFileName(file);
        if (name == ".working.lock" || (name.StartsWith(".working-") && name.EndsWith(".tmp"))) continue;

        try
        {
            if (!File.Exists(file))
            {
                Console.WriteLine($"  warn    skipped dangling symlink {rel}");
                continue;
            }

            var dest = Path.Combine(to, rel);
            if (File.Exists(dest))
            {
                if (!File.ReadAllBytes(dest).AsSpan().SequenceEqual(File.ReadAllBytes(file)))
                {
                    var conflict = Path.Combine(to, ".conflict", rel);
                    Directory.CreateDirectory(Path.GetDirectoryName(conflict)!);
                    File.Copy(file, conflict, overwrite: true);
                    Console.WriteLine($"  warn    kept existing learnings/{rel}; your local copy is saved at {conflict} (original also at {file})");
                }
                continue;
            }

            Directory.CreateDirectory(Path.GetDirectoryName(dest)!);
            File.Copy(file, dest, overwrite: false);
            copied++;
        }
        catch (Exception ex)
        {
            Console.WriteLine($"  warn    could not migrate learnings/{rel}: {ex.Message}");
        }
    }

    Console.WriteLine($"  migrated learnings ({copied} file(s))");
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
    // Prefer the CLI's own report: `aspire update --self` rewrites the binary but
    // not ~/.aspire/.aspire-bundle-version, so that file goes stale after an update.
    // Fall back to the file when the CLI cannot be run or its version cannot be parsed.
    var aspireVersion = AspireCliVersion() ?? AspireBundleVersion(home);
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

static string? AspireCliVersion()
{
    // `aspire --version` prints "13.6.4+c89352703f78ae46de90fbf751ed8b52b77b89bf".
    // RunCapture merges stdout and stderr, so take the first line that starts with
    // a version rather than assuming the banner is line one. A hyphenated preview
    // build keeps its numeric triple, which is the same shape the bundle file uses.
    var (code, output) = RunCapture("aspire", "--version");
    if (code != 0) return null;

    var m = System.Text.RegularExpressions.Regex.Match(output, "(?m)^\\s*(\\d+\\.\\d+\\.\\d+)");
    return m.Success ? m.Groups[1].Value : null;
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
