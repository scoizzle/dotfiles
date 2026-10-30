# dotnetup — verified surface (P0 spike)

Machine: macOS, arm64. dotnetup `0.3.0-preview.1.26511.1+ea84ffbcebadd4653918c4ee0874a23001182874`.
Recorded verbatim from `--help` and live runs. Re-run the spike after any dotnetup update;
it is a preview product and this file is the contract `setup.sh` and `install.cs` are
written against.

## Install

```sh
curl -fsSL https://aka.ms/dotnetup/get-dotnetup.sh | bash
```

Script options: `--install-dir DIR`, `--quality preview|daily`, `--runtime-id RID`.
Default install dir `~/.dotnetup`. Downloads
`https://ci.dot.net/public/dotnetup/<ver>/dotnetup-<rid>` and verifies SHA-512 itself.
Binary is ~76 MB.

## Facts that correct the plan

1. **`dotnetup list --format Json` exists.** (The plan assumed there was no machine-readable
   output and told `install.cs` not to scrape. Wrong — use the JSON, never the text.)

   ```json
   {
     "installSpecs": [
       { "component": "SDK", "versionOrChannel": "10.0", "source": "GlobalJson",
         "globalJsonPath": "<abs>/global.json",
         "installRoot": "~/Library/Application Support/dotnetup/dotnet",
         "architecture": "arm64" }
     ],
     "installations": [
       { "component": "SDK", "version": "10.0.403",
         "installRoot": "...", "architecture": "arm64",
         "isValid": true, "frameworkName": ".NET SDK" }
     ]
   }
   ```

   `installSpecs[].source` is `GlobalJson` or `Explicit`. `installations[].isValid` is the
   cheapest correctness probe available.

2. **`dotnetup env script` exists** and is better than the planned hand-off. It prints an
   eval-able block for the *current* process, so `setup.sh` does not need
   `exec dotnetup dotnet -- run ...`:

   ```sh
   eval "$(dotnetup env script)"
   ```

   Emits `DOTNET_ROOT`, `PATH` (prepending `~/.dotnetup` and the managed root), and
   `rehash` on zsh. Without a configured mode it still emits the defaults.

3. **The managed install root contains spaces:**
   `~/Library/Application Support/dotnetup/dotnet`. Every quoting bug in `setup.sh` and
   `install.cs` will show up here first.

4. **Bare `dotnetup sdk install` does read `global.json`** — verified. With
   `{"sdk":{"version":"10.0.104","rollForward":"latestFeature"}}` in cwd it printed
   "…will be installed since …/global.json specifies that version", installed SDK
   **10.0.403**, and tracked the spec as `versionOrChannel: "10.0"`, `source: GlobalJson`.
   So `latestFeature` → channel `10.0`, confirming the docs' mapping.

5. **`dotnetup dotnet -- <args>` runs without PATH** (verified: `-- --version` → 10.0.403).

## Other verified commands

| command | behaviour |
| --- | --- |
| `dotnetup --version` | version string (+ telemetry notice on stderr) |
| `dotnetup env show` | `No dotnetup env configuration found.` when unset |
| `dotnetup env set <mode>` | `shell` / `everywhere` / `none` |
| `dotnetup sdk install [<channel>...]` | channel optional; `--no-progress`, `--update-global-json`, `--migrate-from-system`, `--untracked` |
| `dotnetup list --format Json` | see above |
| `dotnetup dotnet -- <args>` | run managed dotnet |

## Verified hand-off

```sh
dotnetup dotnet -- run /Users/scoizzle/dotfiles/install.cs --check
# -> exit 0, "nothing to do"
```

So `setup.sh` can end with either that, or `eval "$(dotnetup env script)"` followed by
`./install.cs`. Prefer the `eval` form: it leaves the *rest* of the script (and any later
`dotnet` calls) on the managed toolchain rather than only the one command.

## Linux (Ubuntu 26.04 arm64, Parallels)

Verified on a real guest:

- Detected runtime `linux-arm64`; downloads `dotnetup-linux-arm64`.
- **The SDK root is `~/.local/share/dotnetup/dotnet`, not
  `~/Library/Application Support/dotnetup/dotnet`.** It is platform-specific — never
  hardcode either; ask `dotnetup env script` or `env show`.
- `global.json` is honoured identically: SDK 10.0.403, spec `source: GlobalJson`.
- `dotnetup env set shell` writes a guarded block to `~/.bashrc`:

  ```sh
  # dotnetup: begin
  if [ -x '/home/<user>/.dotnetup/dotnetup' ]; then
      eval "$('/home/<user>/.dotnetup/dotnetup' env script --shell bash --dotnet --dotnetup)"
  fi
  # dotnetup: end
  ```

  It applies to **interactive** shells only — `bash -c` does not source `.bashrc`, so a
  non-interactive script still needs the PATH set. Revert with `dotnetup env clear`.
- `dotnet tool install -g roslynk` under the managed SDK **still installs to
  `~/.dotnet/tools/roslynk`**, and ships a native `ELF 64-bit ... ARM aarch64` apphost
  (roslynk 3.0.0). So the `{env:HOME}/.dotnet/tools/roslynk` MCP path is correct on both
  platforms — the open question in the earlier revision is answered.
- `dotnetup dotnet -- tool install -g roslynk` works with no PATH at all.

## Consequences for the plan

- Drop "never scrape `dotnetup list`" as a constraint — there is JSON. The `--doctor`
  checks should read `installSpecs`/`installations` directly.
- Drop the `exec "$HOME/.dotnetup/dotnetup" dotnet -- run install.cs` hand-off in favour of
  `eval "$(dotnetup env script)"`.
- `DOTNET_ROOT` and the install root are permission-sensitive to spaces; quote everything.
- `dotnetup` itself is on PATH only after `export PATH="$HOME/.dotnetup:$PATH"` (what the
  installer prints, and what `env script` emits).
