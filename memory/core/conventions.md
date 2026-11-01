# Conventions

Short rules for this opencode setup. Agents read this file. They do not edit it.

Tiers, evidence, and review gates are defined in `~/.config/opencode/AGENTS.md`. Name the tier before the first edit. The parent owns the checks. Reviewers read the bundle and do not rebuild.

This repo has no solution file. `install.cs` is a file-based app. In a repository that has a `*.sln` or `*.slnx`, open that solution and use Roslynk for C# navigation and edits.

Read `memory/INDEX.md` first. Load another memory file only when its blurb matches the task. Append lessons under `memory/learnings/`. Leave `memory/core/` unchanged.
