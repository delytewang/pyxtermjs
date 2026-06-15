# pyxtermjs Login Authentication Design

## Summary

Add mandatory password-based login to pyxtermjs. The application will not start without an authentication JSON file. The JSON file stores one username and one password hash. After a successful login, Flask session state allows access to the terminal page and the Socket.IO `/pty` namespace.

This design keeps the feature small: no database, no user management UI, no password reset, and no role system.

## Goals

- Require authentication before any browser terminal can be used.
- Store credentials in a simple JSON file.
- Store only a password hash, not a plaintext password.
- Reject startup when authentication is not configured correctly.
- Protect both HTTP routes and Socket.IO terminal events.
- Keep current terminal behavior unchanged after login.

## Non-Goals

- Multiple users.
- Persistent login tokens.
- Account creation or password change UI.
- OAuth, LDAP, SSO, or external identity providers.
- Public-internet hardening beyond basic session authentication.

## Configuration

Startup requires an `--auth-file` argument:

```bash
pyxtermjs --auth-file auth.json
```

If `--auth-file` is omitted, the process exits before starting the Flask server with a clear error message.

The JSON file must contain:

```json
{
  "username": "admin",
  "password_hash": "scrypt:32768:8:1$...$..."
}
```

Validation rules:

- The path must exist and be readable.
- The file must parse as a JSON object.
- `username` must be a non-empty string.
- `password_hash` must be a non-empty string.
- Any validation failure stops startup.

## Password Hash Generation

Add a helper command:

```bash
pyxtermjs --generate-password-hash
```

This command prompts for a password using `getpass`, generates a hash with Werkzeug, prints the hash, and exits without starting the server.

Implementation will use:

- `werkzeug.security.generate_password_hash`
- `werkzeug.security.check_password_hash`

Werkzeug is appropriate because this project already uses Flask, and Flask commonly ships with Werkzeug in the dependency chain. This avoids adding a new password library for a single-user local tool.

## HTTP Routes

### `GET /login`

Renders a small login form with username and password fields.

If the user is already authenticated, redirect to `/`.

### `POST /login`

Checks the submitted username and password against the loaded auth config.

On success:

- Clear any existing session state.
- Set `session["authenticated"] = True`.
- Redirect to `/`.

On failure:

- Render the login page again.
- Show a generic error such as `Invalid username or password`.
- Do not reveal which field was wrong.

### `GET /logout`

Clears the session and redirects to `/login`.

### `GET /`

Requires an authenticated session.

If unauthenticated, redirect to `/login`.

If authenticated, render the existing terminal page.

## Socket.IO Protection

The terminal process starts from the Socket.IO `/pty` `connect` handler, so Socket.IO must be protected independently from the HTML page.

Protected handlers:

- `connect`
- `pty-input`
- `resize`

Behavior:

- `connect`: if unauthenticated, reject the connection.
- `pty-input`: if unauthenticated, ignore the event.
- `resize`: if unauthenticated, ignore the event.

This prevents a client from bypassing `/login` and connecting directly to `/pty`.

## Frontend

Add `pyxtermjs/login.html` with a minimal form:

- username input
- password input
- submit button
- optional error message

Update `pyxtermjs/index.html` to include a small logout link. The terminal UI and xterm.js setup remain otherwise unchanged.

## Session Secret

The current app uses a hard-coded `SECRET_KEY`. Login sessions need a better default.

Use the following behavior:

- Prefer `PYXTERMJS_SECRET_KEY` environment variable when present.
- If it is absent, generate a random in-memory secret for the current process.

This keeps configuration simple while avoiding a static package-wide session signing key. Sessions will be invalidated on restart unless the environment variable is set.

## Error Handling

Startup failures should be explicit and early:

- Missing `--auth-file`: exit with parser error.
- Missing file: exit with a clear message.
- Invalid JSON: exit with a clear message.
- Missing or empty fields: exit with a clear message.

Runtime login failures should be generic to the browser user:

- `Invalid username or password`

## Testing

Manual checks:

1. `pyxtermjs` without `--auth-file` exits before serving.
2. Invalid auth JSON exits before serving.
3. Valid auth JSON starts the server.
4. `/` redirects to `/login` before login.
5. Wrong credentials stay on `/login` with a generic error.
6. Correct credentials redirect to `/`.
7. `/logout` clears the session.
8. Direct unauthenticated Socket.IO connection to `/pty` is rejected.
9. Authenticated terminal behavior remains unchanged.

Automated tests can be added later around Flask route behavior and auth config loading. The first implementation should at minimum run Python syntax checks after edits.

## Implementation Scope

Expected file changes:

- `pyxtermjs/app.py`
- `pyxtermjs/index.html`
- `pyxtermjs/login.html`
- `README.md`

No package dependency changes are expected.
