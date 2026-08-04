---
name: wt
description: Cheatsheet for interacting with the work_timer CLI (wtctl). Use whenever you need to read tasks, log time, check velocity, or modify tasks in the database.
---

# Work Timer CLI Reference (`wtctl`)

This skill provides technical reference patterns for interacting with the local task and timelog database via the `wtctl` CLI.

## Tooling Quick Reference & Best Practices

### 1. Querying Tasks
*   **List Active Tasks (Default):** `wtctl ls --depth 3` (By default, `--status` is set to `open`, excluding closed/done tasks).
*   **List Completed or All Tasks:** `wtctl ls --status closed` or `wtctl ls --status all`.
*   **Scope to a Parent Tree:** `wtctl ls --parent <ID> --depth 2`
*   **Read Task Details:** `wtctl show -t <ID>` (Always inspect full details before modifying).

### 2. Querying Time & Velocity
*   **Check Weekly Log/Velocity:** `wtctl timelog --weekly` (or `--since YYYY-MM-DD`).
*   **Check Daily Logs:** `wtctl timelog --today`.

### 3. Modifying Tasks
*   **Create Task:** `wtctl add-task --title "..." --parent <ID> --desc "..." --priority P1`
*   **Update Task:** `wtctl edit-task -t <ID> --parent <NEW_ID> --status done`
*   **Reorder Sibling Tasks:** `wtctl reorder -t <ID> --before <SIBLING_ID>` (or `--after <ID>`, `--top`, `--bottom`, `--up`, `--down`)
*   **Supported Statuses:** `new`, `done`, `wontfix`.
