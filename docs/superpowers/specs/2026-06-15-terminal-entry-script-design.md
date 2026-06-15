# Terminal Entry Script Design

## Summary

Add a small shell entry script that runs as the terminal command after a user logs in. The first target use case is automatically attaching to a named tmux session, creating it if it does not exist.

This keeps the Python application simple. pyxtermjs already supports choosing the terminal command with `--command`, so the tmux-specific behavior belongs in a shell script rather than in Flask or Socket.IO code.

## Goals

- Automatically enter a tmux session when the browser terminal starts.
- Avoid running any shell action before authentication succeeds.
- Keep tmux behavior easy to edit without changing Python code.
- Keep the existing login and terminal connection flow intact.
- Use the existing `--command` option instead of adding a new backend feature.

## Non-Goals

- Add tmux management UI.
- Support multiple named sessions from the web UI.
- Run pre-login shell actions.
- Add database-backed user preferences.
- Replace the existing `--command` and `--cmd-args` options.

## Runtime Flow

The current application starts the terminal process from the Socket.IO `/pty` connection handler. Because `/pty` is protected by the login session, the entry script only runs after successful authentication.

Flow:

1. User opens pyxtermjs in the browser.
2. User logs in.
3. Browser loads the terminal page.
4. Browser connects to Socket.IO namespace `/pty`.
5. Backend verifies the authenticated session.
6. Backend starts the configured command inside the pty.
7. The configured command is the terminal entry script.
8. The entry script attaches to tmux or creates the session.

This is intentionally "after login, before interactive terminal use" rather than "before login". Running shell actions before authentication would allow unauthenticated browser traffic to trigger local commands.

## Entry Script

Add `terminal-entry.sh` at the project root:

```bash
#!/usr/bin/env bash
set -e

SESSION_NAME="main"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  exec tmux attach-session -t "$SESSION_NAME"
else
  exec tmux new-session -s "$SESSION_NAME"
fi
```

Use `exec` so tmux replaces the script process. That keeps the pty process tree simple and makes terminal exit behavior predictable.

## Run Script

Update `run.sh` to start pyxtermjs with the entry script as the terminal command:

```bash
#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

.venv/bin/python -m pyxtermjs \
  --auth-file auth.json \
  --host 0.0.0.0 \
  --command ./terminal-entry.sh
```

The `cd "$(dirname "$0")"` line lets `run.sh` work when launched from another directory.

## Configuration

Initial configuration is intentionally inside `terminal-entry.sh`:

```bash
SESSION_NAME="main"
```

Changing the tmux session only requires editing this value. If more flexibility is needed later, `SESSION_NAME` can be read from an environment variable without changing the Python app:

```bash
SESSION_NAME="${PYXTERMJS_TMUX_SESSION:-main}"
```

That extension is optional and not required for the first implementation.

## Error Handling

- If `tmux` is not installed, the entry script fails and the terminal shows the shell error.
- If attaching to an existing session fails, `set -e` stops the script.
- If no session exists, the script creates one with `tmux new-session -s "$SESSION_NAME"`.

This is enough for a small local tool. More detailed error messages can be added later if needed.

## Testing

Manual checks:

1. Ensure `auth.json` exists and login still works.
2. Start the app with `./run.sh`.
3. Log in from the browser.
4. Confirm the terminal attaches to tmux session `main`.
5. Stop the tmux session and reload the browser terminal.
6. Confirm a new `main` session is created.
7. Run `./run.sh` from a different directory and confirm it still finds `.venv`, `auth.json`, and `terminal-entry.sh`.

Syntax checks:

```bash
bash -n run.sh
bash -n terminal-entry.sh
```

## Implementation Scope

Expected file changes:

- `terminal-entry.sh`
- `run.sh`
- `README.md`

No Python changes are needed for the first implementation.
