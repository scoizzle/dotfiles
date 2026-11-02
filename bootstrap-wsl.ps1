# bootstrap-wsl.ps1 - Windows cold start: get a WSL2 distro ready, then run bootstrap.sh in it.
#
# Windows native is unsupported. The worker is Linux inside WSL2; the clone, the
# tools and T3 all live in the distro (never on the Windows filesystem, never
# behind a \\wsl$ path). This script is a thin host wrapper: it does not
# reimplement bootstrap.sh, setup.sh or install.cs, it runs bootstrap.sh inside
# the distro.
#
#   powershell -ExecutionPolicy Bypass -File .\bootstrap-wsl.ps1 [-DryRun] [-Distro Ubuntu]
#
# Works in Windows PowerShell 5.1 and PowerShell 7. Run it from Windows, not
# from inside WSL (there, run ./bootstrap.sh).
#
# Parameters:
#   -Distro   WSL distro to use                      (default Ubuntu)
#   -DryRun   print what would happen, change nothing; never calls wsl.exe
#   -Help     print this usage
#
# Environment (all optional, handed to the distro through WSLENV):
#   DOTFILES_TOKEN  token for the private clone (never written to a Windows file)
#   GH_TOKEN        same, as bootstrap.sh also accepts it
#   DOTFILES_SLUG   owner/repo            (default scoizzle/dotfiles)
#   DOTFILES_BRANCH branch                (default main)
#   DOTFILES_DIR    clone destination, a Linux path outside /mnt (default $HOME/dotfiles)
[CmdletBinding()]
param(
    [string]$Distro = 'Ubuntu',
    [switch]$DryRun,
    [switch]$Help
)

function Say([string]$Text) { Write-Host $Text }

function Step([string]$Name) {
    Write-Host ''
    Write-Host "== $Name =="
}

function Die([string]$Text) {
    [Console]::Error.WriteLine("error: $Text")
    exit 1
}

function Have([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Run([string]$Exe, [string[]]$ArgList) {
    if ($DryRun) {
        Say ("would run: $Exe " + ($ArgList -join ' '))
        return
    }
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) {
        Die "$Exe failed with exit code $LASTEXITCODE"
    }
}

# Capture a native command as clean text lines (wsl.exe emits UTF-16, which
# arrives with NUL characters in Windows PowerShell). Sets $script:NativeExit.
function Capture([string]$Exe, [string[]]$ArgList) {
    $raw = & $Exe @ArgList 2>&1
    $script:NativeExit = $LASTEXITCODE
    $lines = @()
    foreach ($item in @($raw)) {
        $line = ("$item" -replace "`0", '').Trim()
        if ($line.Length -gt 0) { $lines += $line }
    }
    return $lines
}

function Get-Distros {
    $names = Capture 'wsl.exe' @('--list', '--quiet')
    if ($script:NativeExit -ne 0) { return @() }
    return $names
}

function Test-DistroPresent {
    foreach ($name in @(Get-Distros)) {
        if ($name -ieq $Distro) { return $true }
    }
    return $false
}

# Run a literal script inside the distro. The text is CR-stripped and sent as
# base64 (ASCII), which sidesteps PS 5.1 stdin encoding and quoting problems.
function Invoke-Guest([string]$Text, [bool]$AsRoot) {
    $clean = $Text -replace "`r", ''
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($clean))
    $wslArgs = @('-d', $Distro)
    if ($AsRoot) { $wslArgs += @('-u', 'root') }
    $wslArgs += @('--', 'bash', '-c', "echo $b64 | base64 -d | bash -s")
    Run 'wsl.exe' $wslArgs
}

if ($Help) {
    Get-Content -LiteralPath $PSCommandPath | Select-Object -First 25 | ForEach-Object { Write-Host $_ }
    exit 0
}

# ---------------------------------------------------------------------------
# Guards. The WSL check comes first: Linux pwsh inside WSL has no OS variable.
# ---------------------------------------------------------------------------
if ($env:WSL_DISTRO_NAME -or $env:WSL_INTEROP) {
    Die "running inside WSL ($($env:WSL_DISTRO_NAME)); run ./bootstrap.sh there instead. This script is the Windows cold start."
}

if ($env:OS -ne 'Windows_NT' -and -not $DryRun) {
    Die 'this is the Windows cold start; on Linux or macOS run ./bootstrap.sh'
}

if ([string]::IsNullOrWhiteSpace($Distro)) {
    Die '-Distro must name a WSL distro (default Ubuntu)'
}

if ($env:USERPROFILE) {
    $wslConfigPath = Join-Path $env:USERPROFILE '.wslconfig'
} else {
    # only reachable under -DryRun on a non-Windows host, for a readable plan
    $wslConfigPath = '%UserProfile%\.wslconfig'
}

$wslConfigText = @'
[wsl2]
# Windows-side memory cap for every WSL2 distro; raise it if a build needs more.
memory=8GB
'@

# ---------------------------------------------------------------------------
# Environment handoff, built before any wsl call. The list is explicit and
# flag-free on purpose: no /p or /u flag is ever used, so a token is never
# treated as a path. This overwrites the process WSLENV deliberately.
# ---------------------------------------------------------------------------
$forward = @()
foreach ($name in @('DOTFILES_TOKEN', 'GH_TOKEN', 'DOTFILES_SLUG', 'DOTFILES_BRANCH')) {
    if (Test-Path -LiteralPath "Env:$name") {
        if ((Get-Item -LiteralPath "Env:$name").Value) { $forward += $name }
    }
}
$dirValue = $env:DOTFILES_DIR
if ($dirValue) {
    # /mnt, //mnt, /mnt/c and any .. segment are refused here; the guest script
    # resolves the path again with readlink -f before it clones.
    if ($dirValue -match '^/' -and $dirValue -notmatch '^/+mnt(/|$)' -and
        $dirValue -notmatch ':' -and $dirValue -notmatch '(^|/)\.\.(/|$)') {
        $forward += 'DOTFILES_DIR'
    } else {
        Say "ignoring DOTFILES_DIR=$dirValue (not a Linux path outside /mnt)"
    }
}
if (-not $DryRun) {
    $env:WSLENV = ($forward -join ':')
}

$guestConfig = @'
set -eu

conf=/etc/wsl.conf
if [ -f "$conf" ] && grep -Eq '^[[:space:]]*systemd[[:space:]]*=[[:space:]]*true' "$conf"; then
    echo "  ok      systemd already enabled in $conf"
elif [ ! -f "$conf" ]; then
    printf '[boot]\nsystemd=true\n' > "$conf"
    echo "  set     systemd=true (created $conf)"
elif grep -Eq '^[[:space:]]*systemd[[:space:]]*=' "$conf"; then
    sed -i -E 's/^[[:space:]]*systemd[[:space:]]*=.*/systemd=true/' "$conf"
    echo "  set     systemd=true in $conf"
elif grep -Eq '^[[:space:]]*\[boot\]' "$conf"; then
    sed -i -E '/^[[:space:]]*\[boot\]/a systemd=true' "$conf"
    echo "  set     systemd=true under [boot] in $conf"
else
    printf '\n[boot]\nsystemd=true\n' >> "$conf"
    echo "  set     systemd=true (appended [boot] to $conf)"
fi

want='fs.inotify.max_user_watches=524288'
file=/etc/sysctl.d/99-dotfiles-inotify.conf
if [ -f "$file" ] && [ "$(cat "$file")" = "$want" ]; then
    echo "  ok      $file already has $want"
else
    printf '%s\n' "$want" > "$file"
    echo "  set     $file ($want)"
fi
sysctl -q -p "$file" 2>/dev/null || sysctl -w fs.inotify.max_user_watches=524288 >/dev/null 2>&1 || true
now=$(cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || echo unknown)
if [ "$now" = "524288" ]; then
    echo "  ok      fs.inotify.max_user_watches=$now"
else
    echo "  warn    fs.inotify.max_user_watches=$now (wanted 524288; $file applies it on the next boot)"
fi
'@

$guestBootstrap = @'
set -euo pipefail
cd "$HOME"

# Resolve before testing: //mnt/c, /mnt, and /home/u/../.. all normalize away.
norm() {
    readlink -f -- "$1" 2>/dev/null || printf '%s\n' "$1"
}
canon() {
    norm "$1" | sed 's|^/*|/|'
}

home=$(canon "$HOME")
case "$home" in
    /mnt | /mnt/*) echo "error: Linux home is on the Windows filesystem ($home); refusing" >&2; exit 1 ;;
esac

dest=$(canon "${DOTFILES_DIR:-$HOME/dotfiles}")
case "$dest" in
    /mnt | /mnt/*) echo "error: clone destination is on the Windows filesystem ($dest); refusing" >&2; exit 1 ;;
esac

if [ -d "$dest/.git" ]; then
    echo "  exists  $dest already has a git checkout; leaving it alone"
    exec "$dest/bootstrap.sh"
fi

tok="${DOTFILES_TOKEN:-${GH_TOKEN:-}}"
if [ -z "$tok" ]; then
    echo ""
    echo "  This repo is private, so a bare machine cannot clone it anonymously."
    echo "  Do one of these and re-run:"
    echo "    DOTFILES_TOKEN=<token>   # github.com/settings/tokens, 'repo' scope"
    echo "    gh auth login            # if the gh CLI is available"
    echo ""
    echo "  Or make the repo public and this needs nothing."
    exit 1
fi

url="https://raw.githubusercontent.com/${DOTFILES_SLUG:-scoizzle/dotfiles}/${DOTFILES_BRANCH:-main}/bootstrap.sh"
if command -v curl >/dev/null 2>&1; then
    curl -fsSL -H "Authorization: Bearer $tok" "$url" | sh
elif command -v wget >/dev/null 2>&1; then
    wget --header="Authorization: Bearer $tok" -qO- "$url" | sh
else
    echo "error: need curl or wget in the distro" >&2
    exit 1
fi
'@

# ---------------------------------------------------------------------------
# Dry run: print the whole plan, call nothing, write nothing.
# ---------------------------------------------------------------------------
if ($DryRun) {
    Step 'wsl2'
    if (Have 'wsl.exe') { Say '  wsl.exe found' } else { Say '  wsl.exe not found (a real run would stop: run `wsl --install` elevated, reboot, re-run)' }
    Say 'would run: wsl.exe --status (and wsl.exe --set-default-version 2 if the default version is 1)'

    Step 'distro'
    Say "would check that $Distro is installed; if missing, run: wsl.exe --install -d $Distro"
    Say "would refuse a WSL1 $Distro (fix: wsl --set-version $Distro 2) and a distro with no default user yet"

    Step 'wslconfig'
    Say "would create: $wslConfigPath (only if absent; an existing file is never touched)"
    foreach ($line in ($wslConfigText -split "`r?`n")) { Say "    $line" }

    Step 'guest config'
    Say "would run in $Distro (as root): enable systemd and inotify"
    Say 'would print: `wsl --shutdown` is required before the next boot (it restarts every distro, so it is not run here)'
    Say 'would print: systemd needs WSL 0.67.6 or newer (`wsl --version` reports it)'

    Step 'bootstrap'
    if ($forward.Count -gt 0) { Say ('would forward through WSLENV: ' + ($forward -join ' ')) } else { Say 'would forward no environment variables' }
    Say "would run in $Distro (as the default user): clone to `$HOME/dotfiles via bootstrap.sh, then setup.sh"
    Say '  skips when the checkout exists; refuses any path under /mnt; never clones from PowerShell'

    Step 'logins'
    Say '  1. opencode auth login     # opencode providers'
    Say '  2. claude auth login       # Claude Agent integration'
    Say '  3. opencode auth login     # choose xAI - the auth used for xai/grok-4.7'
    Say 'These are run later, in the distro, by you; this script performs none of them.'
    exit 0
}

# ---------------------------------------------------------------------------
Step 'wsl2'

if (-not (Have 'wsl.exe')) {
    Die 'WSL is missing; run `wsl --install` in an elevated terminal, reboot, then re-run this script.'
}

# Capture can return a single line as a bare string; @() keeps .Count and
# indexing correct, which matters for the root check below.
$status = @(Capture 'wsl.exe' @('--status'))
$statusText = $status -join "`n"
if ($script:NativeExit -eq 0 -and $statusText -match 'Default Version:\s*(\d+)') {
    if ($Matches[1] -eq '1') {
        Say '  default version is 1; setting 2 (affects new distros only)'
        Run 'wsl.exe' @('--set-default-version', '2')
    } else {
        Say '  ok      default version is 2'
    }
} else {
    Say '  could not read the WSL default version; continuing'
}

# ---------------------------------------------------------------------------
Step 'distro'

if (Test-DistroPresent) {
    Say "  ok      $Distro is installed"
} else {
    Say "  $Distro is missing; installing (first run asks you to create a Linux user)"
    Run 'wsl.exe' @('--install', '-d', $Distro)
    if (-not (Test-DistroPresent)) {
        Die "$Distro is still not listed after install; finish its first-run setup (or reboot), then re-run this script."
    }
    Say "  ok      $Distro is installed"
}

$verbose = @(Capture 'wsl.exe' @('--list', '--verbose'))
foreach ($line in $verbose) {
    $parts = ($line.Trim() -replace '^\*', '').Trim() -split '\s+'
    if ($parts.Count -ge 2 -and $parts[0] -ieq $Distro -and $parts[$parts.Count - 1] -eq '1') {
        Die ("$Distro is a WSL1 distro; run 'wsl --set-version $Distro 2', then re-run this script.")
    }
}

$whoami = @(Capture 'wsl.exe' @('-d', $Distro, '--', 'id', '-un'))
$whoamiExit = $script:NativeExit
if ($whoamiExit -ne 0 -or $whoami.Count -eq 0 -or ($whoami -contains 'root')) {
    Die ("the distro has no default user yet; open it once ('wsl -d $Distro') to create your Linux user, then re-run this script.")
}
Say ("  ok      default user is " + $whoami[$whoami.Count - 1])

# ---------------------------------------------------------------------------
Step 'wslconfig'

if (Test-Path -LiteralPath $wslConfigPath) {
    Say "  exists  $wslConfigPath; leaving it alone"
} else {
    Set-Content -LiteralPath $wslConfigPath -Value $wslConfigText -Encoding ASCII
    Say "  set     $wslConfigPath (memory cap 8GB)"
}

# ---------------------------------------------------------------------------
Step 'guest config'

Invoke-Guest $guestConfig $true
Say ''
Say '  `wsl --shutdown` is required before the next boot so systemd and the inotify'
Say '  setting take effect. It restarts every distro, so this script does not run it.'
Say '  systemd needs WSL 0.67.6 or newer; `wsl --version` reports it (inbox Windows 10 builds are older).'
Say '  T3 stays on the Linux side, inside the distro.'

# ---------------------------------------------------------------------------
Step 'bootstrap'

Invoke-Guest $guestBootstrap $false

# ---------------------------------------------------------------------------
Step 'logins'

Say '  1. opencode auth login     # opencode providers'
Say '  2. claude auth login       # Claude Agent integration'
Say '  3. opencode auth login     # choose xAI - the auth used for xai/grok-4.7'
Say 'These are run later, in the distro, by you; this script performs none of them.'
exit 0
