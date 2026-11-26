#!/usr/bin/env python3
"""Starts a package: a folder with everything a beginner needs, ready to run.

    python tools/new_plugin.py <id> [--kind plugin|integration] [--no-service] [--login none|password|oauth] [--name "My plugin"] [--out <folder of your source>]

* ``--kind integration`` (no code): a page with entries and a reminder - only a ``plugin.json``.
* ``--kind plugin`` (the default): a plugin WITH a service - a small program that logs in somewhere (``--login password``, the default; ``--login oauth`` for a provider that logs people in with OAuth 2.0), fetches what the car
  knows and sends it to Car Assistant, with the helper library ``carassistant_sdk.py`` next to it. ``--no-service`` makes a plugin without a program (settings
  and a device that calls the Plugin API itself).

The folder lands in ``<out>/plugins/<id>/`` (or ``integrations/<id>/``); ``--out`` is the folder of your source (default: the current folder).
The list of the source (``<kind>/index.json``) gets its line, too - a line that is there is never changed. Then:

    python tools/plugin_dev.py <the folder>                   # a real Car Assistant on your computer with the package installed, approved and running
    python tools/check_plugin.py <the folder>                 # the check the app does when it reads the package (before the zip is built it names it)
    python tools/build_plugin_package.py <your source> <id>   # a plugin with a service: the zip and its checksum for the list
    python tools/check_source.py <your source>                # the whole source, the way the app reads it

docs/start-here.md walks through all of it."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "docs" / "examples" / "sdk" / "carassistant_sdk.py"
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")

SERVICE = '''"""{name} - the service of the plugin: a small program that runs inside Car Assistant.

It asks a web service for what the car knows and hands it to Car Assistant with the Plugin API (docs/api.md). Replace the places that say TODO.
Try it on your computer with:  python tools/plugin_dev.py {folder}
"""

import carassistant_sdk as ca

api = ca.Api()  # the Plugin API of Car Assistant, with the token and the car of this service
web = ca.Http()  # a client for web services: JSON, cookies for a session, retries
state = ca.State()  # what the service has to remember (a session, a token it was given)
{login_block}

{fetch_block}

ca.run(poll, every=60)
'''

FETCH = '''def fetch(cfg):
    """TODO: ask the web service for the car and return what you know, under the names of docs/api.md (the table "Send data")."""
    # car = web.get("https://api.example.com/car", headers={{"Authorization": "Bearer " + state.get("token", "")}}).json()
    # return {{"odometer_km": car["km"], "fuel_level_pct": car["fuel"]}}
    return {{"odometer_km": 12345}}  # a made-up value, so that you see something arrive


def poll():
    """Called again and again (every minute here). A poll that raises is noted in the log and tried again after a pause."""
    data = fetch(ca.settings())
    if data:
        api.send(data)
        ca.log("sent " + ", ".join(data))
'''

FETCH_OAUTH = '''def fetch(cfg):
    """TODO: ask the web service for the car with the login of the person and return what you know, under the names of docs/api.md."""
    headers = api.bearer()  # the access token of the login (docs/plugins.md, "Logging in with an account"): the app keeps it fresh
    # car = web.get("https://api.example.com/car", headers=headers).json()
    # return {{"odometer_km": car["km"], "fuel_level_pct": car["fuel"]}}
    return {{"odometer_km": 12345}}  # a made-up value, so that you see something arrive


def poll():
    """Called again and again (every minute here). A poll that raises is noted in the log and tried again after a pause."""
    try:
        data = fetch(ca.settings())
    except ca.ApiError as exc:
        if exc.error not in ("not_connected", "login_required"):
            raise
        ca.log("waiting for the login of the person", "warn")  # nobody has logged in yet, or the login has expired: the tile of the plugin says so
        return
    if data:
        api.send(data)
        ca.log("sent " + ", ".join(data))
'''

LOGIN_BLOCK = '''

def login(cfg):
    """TODO: log in at the web service and remember the session. Raise an exception with a short text when it fails; return a name to show."""
    # answer = web.post("https://api.example.com/login", json={{"user": cfg["user"], "password": cfg["password"]}})
    # state.set("token", answer.json()["token"])
    if not cfg.get("user") or not cfg.get("password"):
        raise ValueError("user name and password are needed")
    return cfg["user"]


@ca.route("POST", "/{route}/check")
def check(request):
    """The step "Check the login" of the set-up (docs/plugins.md, "The set-up flow"): the app asks, with what the person just typed."""
    cfg = {{**ca.settings(), **request.values}}  # what was just typed wins: it is stored only when this answers ok
    try:
        who = login(cfg)
    except Exception as exc:  # shown to the person; never put a password into it
        return {{"ok": False, "message": f"Login failed: {{exc}}"}}
    return {{"ok": True, "message": f"Logged in as {{who}}.", "settings": {{"status": "connected"}}}}

'''


def plugin_json(args, name: str) -> dict:
    base = {"id": args.id, "kind": args.kind, "name": name, "version": "1", "icon": "wrench" if args.kind == "plugin" else "puzzle"}
    base["description"] = "One sentence for the tile: what it does."
    base["author"] = "Your name"
    base["l10n"] = {"de": {"name": name, "description": "Ein Satz für die Kachel: was es tut."}}
    if args.kind == "integration":
        base["nav"] = True
        base["pages"] = [
            {
                "id": "notes",
                "title": "Notes",
                "item": "Note",
                "fields": [
                    {"key": "title", "label": "Title", "type": "text", "required": True, "role": "title"},
                    {"key": "note", "label": "Note", "type": "textarea"},
                    {"key": "done", "label": "Done", "type": "bool"},
                ],
                "l10n": {"de": {"title": "Notizen", "item": "Notiz"}},
            }
        ]
        base["docs"] = "A page of notes. Describe here what your integration is for."
        return base
    settings: list[dict] = []
    if args.service and args.login == "password":
        settings = [
            {"key": "user", "type": "text", "label": "User name", "required": True},
            {"key": "password", "type": "password", "label": "Password", "required": True},
            {"key": "status", "type": "value", "label": "Status", "state": {"ok": ["connected"], "bad": ["error"]}},
        ]
    elif args.service and args.login == "oauth":
        settings = [
            {"key": "client_id", "type": "text", "label": "Client ID", "required": True, "help": "The id of your app at the provider."},
            {"key": "client_secret", "type": "password", "label": "Client secret", "help": "Only when the provider gave you one."},
        ]
    else:
        settings = [{"key": "interval", "type": "number", "label": "How often (minutes)", "min": 1, "max": 60, "default": 5}]
    base["settings"] = settings
    base["interfaces"] = [
        {
            "direction": "sends",
            "name": "Vehicle data",
            "path": "/api/v1/vehicles/<id>/data",
            "fields": ["odometer_km"],
            "note": "every minute",
        }
    ]
    base["docs"] = "Describe here what this plugin reads, where it sends it and what the person has to do."
    if args.service:
        route = args.id
        base["service"] = {
            "entry": "service/main.py",
            "python": ">=3.9",
            "requirements": [],
            "connects": ["api.example.com"],
            "routes": [{"prefix": f"/{route}/", "public": False}],
        }
        if args.login == "oauth":
            base["setup"] = {
                "flow": [
                    {
                        "id": "app",
                        "type": "form",
                        "title": "Your app at the provider",
                        "text": "Register an app at the provider and enter its client id (and its secret, if it has one).",
                        "settings": ["client_id", "client_secret"],
                    },
                    {
                        "id": "connect",
                        "type": "oauth",
                        "title": "Log in with your account",
                        "label": "Log in at login.example.com",
                        "oauth": {
                            "authorize_url": "https://login.example.com/oauth/authorize",
                            "token_url": "https://login.example.com/oauth/token",
                            "scopes": ["offline_access"],
                            "client_id_setting": "client_id",
                            "client_secret_setting": "client_secret",
                            "redirect": "paste",
                            "redirect_uri": "https://localhost/callback",
                        },
                    },
                    {
                        "id": "done",
                        "type": "text",
                        "title": "Done",
                        "text": "Car Assistant keeps the login fresh; the plugin asks the account for the car and shows what it gets.",
                    },
                ]
            }
        if args.login == "password":
            base["setup"] = {
                "flow": [
                    {"id": "intro", "type": "text", "title": "Welcome", "text": "Log in with the account you use for the car."},
                    {
                        "id": "login",
                        "type": "check",
                        "action": f"/{route}/check",
                        "settings": ["user", "password"],
                        "label": "Check the login",
                        "l10n": {"de": {"label": "Anmeldung prüfen"}},
                    },
                    {
                        "id": "done",
                        "type": "text",
                        "title": "Done",
                        "text": "Car Assistant now asks the account for the car and shows what it gets.",
                    },
                ],
                "done_when": [{"key": "status", "equals": "connected"}],
            }
    return base


def add_to_index(out: Path, folder: str, manifest: dict) -> str:
    """The list of the source (``<folder>/index.json``) gets a line for the package, so that the app finds it. A line that is there stays as it is.
    Returns a sentence when the list could not be written to."""
    path = out / folder / "index.json"
    try:
        index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"packages": []}
    except ValueError:
        return f"{path} is not valid JSON - add the package to it yourself"
    entries = index if isinstance(index, list) else index.get("packages")
    if not isinstance(entries, list):
        return f"{path} has no list of packages - add the package to it yourself"
    if not any(isinstance(e, dict) and e.get("id") == manifest["id"] for e in entries):
        entries.append({key: manifest[key] for key in ("id", "name", "version", "description", "icon")})
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Start a package (see the top of this file).")
    parser.add_argument("id")
    parser.add_argument("--kind", choices=("plugin", "integration"), default="plugin")
    parser.add_argument("--no-service", dest="service", action="store_false")
    parser.add_argument("--login", choices=("none", "password", "oauth"), default="password")
    parser.add_argument("--name", default="")
    parser.add_argument("--out", default=".")
    args = parser.parse_args(argv)
    if not ID.match(args.id):
        print("the id: lower-case letters, digits, - and _ (2 to 41 characters)")
        return 2
    name = args.name or args.id.replace("-", " ").replace("_", " ").capitalize()
    folder = Path(args.out) / ("plugins" if args.kind == "plugin" else "integrations") / args.id
    if folder.exists():
        print(f"{folder} exists already - nothing was changed")
        return 1
    (folder).mkdir(parents=True)
    (folder / "plugin.json").write_text(json.dumps(plugin_json(args, name), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.kind == "plugin" and args.service:
        (folder / "service").mkdir()
        login_block = LOGIN_BLOCK.format(route=args.id) if args.login == "password" else ""
        (folder / "service" / "main.py").write_text(
            SERVICE.format(
                name=name, folder=folder, login_block=login_block, fetch_block=(FETCH_OAUTH if args.login == "oauth" else FETCH).format()
            ),
            encoding="utf-8",
        )
        shutil.copyfile(SDK, folder / "service" / "carassistant_sdk.py")
    (folder / "README.md").write_text(
        f"# {name}\n\nA package for Car Assistant. How to try it, check it and publish it: docs/start-here.md of the app.\n",
        encoding="utf-8",
    )
    problem = add_to_index(Path(args.out), folder.parent.name, json.loads((folder / "plugin.json").read_text(encoding="utf-8")))
    print(f"made {folder}")
    if problem:
        print(f"  note:      {problem}")
    print(f"  try it:    python tools/plugin_dev.py {folder}")
    if args.kind == "plugin" and args.service:
        print(f"  publish:   python tools/build_plugin_package.py {args.out} {args.id}   (the zip and its checksum)")
        print(f"             python tools/check_source.py {args.out}")
    else:
        print(f"  publish:   python tools/check_source.py {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
