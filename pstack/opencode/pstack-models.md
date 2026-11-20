# pstack model configuration for opencode. One line per role. Delete a line to fall back to the skill default.
# This file replaces ~/.cursor/rules/pstack-models.mdc in this harness: opencode denies reads of
# ~/.cursor/*, so a pstack skill that names that path reads these values instead.
# Values are this repo's routes, `provider/model#variant`; `inherit-parent` runs on the parent model.
# Code delegates and swarm workers deliberately run at #high on this repo's writer route, not on
# pstack's Opus default: judgment, prose and the three panels keep their real routes.
# Alias entries in a panel list still count toward its fan-out.
# defaults: 3
# budget: large (xhigh)
# managed by bin/sync-pstack from pstack/models.json; edit the JSON, not this file.
feature, refactoring: opencode-go/deepseek-v4.1-flash#high
bug-fix: opencode-go/deepseek-v4.1-flash#high
perf-issue: opencode-go/deepseek-v4.1-flash#high
hillclimb: opencode-go/deepseek-v4.1-flash#high
judgment and prose: claude-agent/opus#xhigh
arena runners: claude-agent/fable#high, claude-agent/opus#high, opencode/gemini-4-neon#xhigh
arena cross-judge pool: claude-agent/opus#high, opencode/gemini-4-neon#xhigh
swarm workers: opencode-go/deepseek-v4.1-flash#high
interrogate reviewers: claude-agent/fable#high, claude-agent/opus#high, opencode/gemini-4-neon#xhigh
