#!/usr/bin/env python3
import argparse
import getpass
import hmac
import json
from flask import Flask, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO
import pty
import os
import subprocess
import select
import termios
import struct
import fcntl
import shlex
import logging
import sys
from werkzeug.security import check_password_hash, generate_password_hash

logging.getLogger("werkzeug").setLevel(logging.ERROR)

__version__ = "0.5.0.2"

app = Flask(__name__, template_folder=".", static_folder=".", static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("PYXTERMJS_SECRET_KEY") or os.urandom(32)
app.config["fd"] = None
app.config["child_pid"] = None
app.config["auth"] = None
socketio = SocketIO(app)


def load_auth_config(auth_file):
    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            auth = json.load(f)
    except OSError as e:
        raise ValueError(f"could not read auth file: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"auth file is not valid JSON: {e}") from e

    if not isinstance(auth, dict):
        raise ValueError("auth file must contain a JSON object")

    username = auth.get("username")
    password_hash = auth.get("password_hash")
    if not isinstance(username, str) or not username:
        raise ValueError("auth file must include a non-empty username string")
    if not isinstance(password_hash, str) or not password_hash:
        raise ValueError("auth file must include a non-empty password_hash string")

    return {"username": username, "password_hash": password_hash}


def is_authenticated():
    return bool(session.get("authenticated"))


def authenticate(username, password):
    auth = app.config["auth"]
    username_matches = hmac.compare_digest(username, auth["username"])
    password_matches = check_password_hash(auth["password_hash"], password)
    return username_matches and password_matches


def generate_password_hash_command():
    password = getpass.getpass("Password: ")
    confirm_password = getpass.getpass("Confirm password: ")
    if password != confirm_password:
        print("passwords do not match", file=sys.stderr)
        return 1
    print(generate_password_hash(password))
    return 0


@app.before_request
def protect_static_html_templates():
    if request.endpoint == "static" and request.path in ("/index.html", "/login.html"):
        if is_authenticated():
            return redirect(url_for("index"))
        return redirect(url_for("login"))


def set_winsize(fd, row, col, xpix=0, ypix=0):
    logging.debug("setting window size with termios")
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def read_and_forward_pty_output():
    max_read_bytes = 1024 * 20
    while True:
        socketio.sleep(0.01)
        if app.config["fd"]:
            timeout_sec = 0
            (data_ready, _, _) = select.select([app.config["fd"]], [], [], timeout_sec)
            if data_ready:
                output = os.read(app.config["fd"], max_read_bytes).decode(
                    errors="ignore"
                )
                socketio.emit("pty-output", {"output": output}, namespace="/pty")


@app.route("/")
def index():
    if not is_authenticated():
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if is_authenticated():
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if authenticate(username, password):
            session.clear()
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Invalid username or password"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@socketio.on("pty-input", namespace="/pty")
def pty_input(data):
    """write to the child pty. The pty sees this as if you are typing in a real
    terminal.
    """
    if not is_authenticated():
        return
    if app.config["fd"]:
        logging.debug("received input from browser: %s" % data["input"])
        os.write(app.config["fd"], data["input"].encode())


@socketio.on("resize", namespace="/pty")
def resize(data):
    if not is_authenticated():
        return
    if app.config["fd"]:
        logging.debug(f"Resizing window to {data['rows']}x{data['cols']}")
        set_winsize(app.config["fd"], data["rows"], data["cols"])


@socketio.on("connect", namespace="/pty")
def connect():
    """new client connected"""
    if not is_authenticated():
        return False

    logging.info("new client connected")
    if app.config["child_pid"]:
        # already started child process, don't start another
        return

    # create child process attached to a pty we can read from and write to
    (child_pid, fd) = pty.fork()
    if child_pid == 0:
        # this is the child process fork.
        # anything printed here will show up in the pty, including the output
        # of this subprocess
        subprocess.run(app.config["cmd"])
    else:
        # this is the parent process fork.
        # store child fd and pid
        app.config["fd"] = fd
        app.config["child_pid"] = child_pid
        set_winsize(fd, 50, 50)
        cmd = " ".join(shlex.quote(c) for c in app.config["cmd"])
        # logging/print statements must go after this because... I have no idea why
        # but if they come before the background task never starts
        socketio.start_background_task(target=read_and_forward_pty_output)

        logging.info(f"child pid is {child_pid}")
        logging.info(
            f"starting background task with command `{cmd}` to continously read "
            "and forward pty output to client"
        )
        logging.info("task started")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "A fully functional terminal in your browser. "
            "https://github.com/cs01/pyxterm.js"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-p", "--port", default=5000, help="port to run server on", type=int
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host to run server on (use 0.0.0.0 to allow access from other hosts)",
    )
    parser.add_argument("--debug", action="store_true", help="debug the server")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_argument(
        "--auth-file",
        help="JSON file containing username and password_hash for login",
    )
    parser.add_argument(
        "--generate-password-hash",
        action="store_true",
        help="prompt for a password, print its hash, and exit",
    )
    parser.add_argument(
        "--command", default="bash", help="Command to run in the terminal"
    )
    parser.add_argument(
        "--cmd-args",
        default="",
        help="arguments to pass to command (i.e. --cmd-args='arg1 arg2 --flag')",
    )
    args = parser.parse_args()
    if args.version:
        print(__version__)
        return 0
    if args.generate_password_hash:
        return generate_password_hash_command()
    if not args.auth_file:
        parser.error("--auth-file is required")

    try:
        app.config["auth"] = load_auth_config(args.auth_file)
    except ValueError as e:
        parser.error(str(e))

    app.config["cmd"] = [args.command] + shlex.split(args.cmd_args)
    green = "\033[92m"
    end = "\033[0m"
    log_format = (
        green
        + "pyxtermjs > "
        + end
        + "%(levelname)s (%(funcName)s:%(lineno)s) %(message)s"
    )
    logging.basicConfig(
        format=log_format,
        stream=sys.stdout,
        level=logging.DEBUG if args.debug else logging.INFO,
    )
    logging.info(f"serving on http://{args.host}:{args.port}")
    socketio.run(app, debug=args.debug, port=args.port, host=args.host)
    return 0


if __name__ == "__main__":
    main()
