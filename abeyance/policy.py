"""Which steps a run may not take alone.

Deterministic, shell-aware classifier. No model calls, no network, standard library only.
A step is HELD when it changes something outside the machine (publish, push, merge, deploy,
pay, send, delete in the cloud, write a database) or destroys local work. Held steps park in
unattended runs and go to Hermes's own approval gate in live sessions.
"""
from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import shlex
from dataclasses import dataclass, field

from . import faults

CLASSES = {
    "PUSH": "changes a shared git remote",
    "MERGE": "merges a pull or merge request",
    "PUBLISH": "publishes a package, image or release",
    "DEPLOY": "changes a running service or infrastructure",
    "CLOUD_DELETE": "deletes or terminates a cloud resource",
    "MONEY": "moves or refunds money",
    "HTTP_WRITE": "writes to a remote API",
    "DB_WRITE": "writes to a database",
    "MESSAGE": "sends a message to a person",
    "DESTROY_LOCAL": "destroys local work",
    "WRITE_OUTSIDE": "writes a file outside the job's folder",
}

_WRAPPERS = {"sudo", "doas", "nohup", "time", "nice", "ionice", "stdbuf", "command", "exec", "builtin"}
_DESTROY_CMDS = frozenset({"dd", "mkfs", "shred", "truncate"})
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
_SHELL_C = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
_WRAPPER_VALUE_FLAGS = {"sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-T", "-U"}, "doas": {"-u", "-C"},
                        "nice": {"-n"}, "ionice": {"-c", "-n", "-p"}, "time": {"-f", "-o"}}
_GIT_GLOBAL_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
_LOOPBACK = re.compile(r"https?://(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:\d+)?(/|$)", re.I)
_MONEY_HOSTS = re.compile(r"api\.(stripe\.com|paypal\.com|sandbox\.paypal\.com|squareup\.com|paystack\.co|flutterwave\.com)", re.I)
_SQL_WRITE = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|replace)\b", re.I)
# MCP and plugin tool names are split into words (snake, kebab or camel case) and read word by word.
_TOOL_STRICT = {"send", "post", "publish", "tweet", "merge", "delete", "remove", "destroy", "refund", "payout", "deploy",
                "update", "put", "write", "upsert", "insert", "modify", "push", "submit", "trigger", "cancel", "approve",
                "grant", "revoke", "close", "drop", "terminate", "kill", "reset", "create", "execute"}
_TOOL_SOFT = {"email", "mail", "message", "reply", "comment", "pay", "charge", "transfer", "invoice", "release", "archive"}
_TOOL_READ_FIRST = {"get", "list", "read", "search", "fetch", "query", "find", "describe", "view", "show", "status", "check", "count", "lookup"}
_MONEY_WORDS = {"pay", "charge", "refund", "transfer", "payout", "invoice"}
_PY_WORLD = re.compile(
    r"(requests|httpx|aiohttp|urllib3?)\.(post|put|patch|delete|request)|smtplib|"
    r"subprocess\.|os\.system|os\.popen|shutil\.rmtree", re.I)
_PY_URLLIB_WRITE = re.compile(r"urllib\.request\.(urlopen|Request)\([^)]*(data\s*=|method\s*=\s*['\"](POST|PUT|PATCH|DELETE))", re.I | re.S)


def _tool_words(verb):
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", verb)
    return [w for w in re.split(r"[_\-\s.]+", spaced.lower()) if w]


def _word_in(words, vocab):
    out = []
    for w in words:
        stem = w[:-1] if w.endswith("s") and len(w) > 3 else w
        if w in vocab or stem in vocab:
            out.append(stem if stem in vocab else w)
    return out


@dataclass
class Decision:
    hold: bool
    classes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    segments: list[str] = field(default_factory=list)

    def label(self) -> str:
        return ", ".join(self.classes) if self.classes else "ALLOWED"


@dataclass
class PolicyConfig:
    hold_patterns: list[str] = field(default_factory=list)    # fnmatch on command text or tool name
    allow_patterns: list[str] = field(default_factory=list)   # override built-in classes (never DESTROY_LOCAL)
    workdir: str | None = None                                # writes outside it are held

    @classmethod
    def from_settings(cls, settings: dict | None) -> "PolicyConfig":
        s = settings or {}
        return cls(list(s.get("hold") or []), list(s.get("allow") or []), s.get("workdir") or None)


def _split_segments(command: str) -> list[list[str]]:
    """Split a shell line into simple-command argv lists, recursing into -c strings and $(...)."""
    out: list[list[str]] = []
    for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", command):
        text = inner[0] or inner[1]
        if text.strip():
            out.extend(_split_segments(text))
    command = command.replace("\r", "").replace("\n", " ; ")       # a new line ends a command, like ';'
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lex.whitespace_split = True
        lex.commenters = "#"
        tokens = list(lex)
    except ValueError:
        tokens = command.split()
    current: list[str] = []
    for tok in tokens:
        if tok and set(tok) <= set(";&|") :
            if current:
                out.append(current)
            current = []
        elif tok == "\n":
            continue
        else:
            current.append(tok)
    if current:
        out.append(current)
    expanded: list[list[str]] = []
    for argv in out:
        expanded.extend(_unwrap(argv))
    return expanded


def _unwrap(argv: list[str]) -> list[list[str]]:
    """Strip wrappers (sudo, env, timeout, xargs) and recurse into `bash -c` / `eval` payloads."""
    i = 0
    while i < len(argv):
        tok = argv[i]
        base = tok.rsplit("/", 1)[-1]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tok):
            i += 1
        elif base in _WRAPPERS:
            i += 1
            takes_value = _WRAPPER_VALUE_FLAGS.get(base, set())
            while i < len(argv) and argv[i].startswith("-"):
                i += 2 if argv[i] in takes_value else 1
        elif base == "env":
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or "=" in argv[i]):
                i += 1
        elif base in {"timeout", "watch"}:
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or re.fullmatch(r"\d+[smhd]?", argv[i])):
                i += 1
        elif base == "xargs":
            i += 1
            while i < len(argv) and argv[i].startswith("-"):
                i += 2 if argv[i] in {"-I", "-n", "-P", "-d", "-L", "-s"} else 1
        elif base in _SHELLS and any(_SHELL_C.match(a) for a in argv[i + 1:]):
            j = next(k for k in range(i + 1, len(argv)) if _SHELL_C.match(argv[k]))
            return _split_segments(argv[j + 1]) if j + 1 < len(argv) else []
        elif base in {"python", "python3", "py"} and argv[i + 1:i + 2] == ["-m"] and len(argv) > i + 2:
            i += 2                                  # `python -m twine upload` is `twine upload`
            break
        elif base in {"npx", "bunx", "pnpx", "uvx", "pipx"}:
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or argv[i] == "run"):
                i += 1
        elif base == "eval":
            return _split_segments(" ".join(argv[i + 1:]))
        else:
            break
    rest = argv[i:]
    return [rest] if rest else []


def _classify_argv(argv: list[str], cfg: PolicyConfig) -> list[tuple[str, str]]:
    if not argv:
        return []
    cmd = argv[0].rsplit("/", 1)[-1].lower()
    if cmd == "git":                                # `git -C dir push` is `git push`
        k = 1
        while k < len(argv) and argv[k].startswith("-"):
            k += 2 if argv[k] in _GIT_GLOBAL_VALUE_FLAGS else 1
        argv = [argv[0]] + argv[k:]
    args = [a.lower() for a in argv[1:]]
    joined = " ".join(argv)
    sub = args[0] if args else ""
    hits: list[tuple[str, str]] = []

    def hit(cls: str, why: str) -> None:
        hits.append((cls, why))

    if cmd == "git":
        if sub == "push":
            hit("PUSH", "git push")
        elif sub == "reset" and "--hard" in args:
            hit("DESTROY_LOCAL", "git reset --hard")
        elif sub == "clean" and any(a.startswith("-") and "f" in a for a in args[1:]):
            hit("DESTROY_LOCAL", "git clean -f")
        elif sub == "branch" and any(a in {"-d", "-D", "--delete"} for a in argv[2:]):
            hit("DESTROY_LOCAL", "git branch delete")
    elif cmd in {"gh", "glab"}:
        if sub in {"pr", "mr"} and len(args) > 1 and args[1] in {"merge", "close"}:
            hit("MERGE", f"{cmd} {sub} {args[1]}")
        elif sub == "release" and len(args) > 1 and args[1] in {"create", "upload", "delete", "edit"}:
            hit("PUBLISH", f"{cmd} release {args[1]}")
        elif sub in {"issue", "repo", "pr", "mr"} and len(args) > 1 and args[1] in {"close", "delete", "create", "edit", "archive", "transfer", "comment", "reopen", "lock"} \
                and not (args[1] == "create" and "--draft" in args):
            hit("HTTP_WRITE", f"{cmd} {sub} {args[1]}")
        elif sub == "api":
            method = ""
            for n, a in enumerate(args):
                if a in {"-x", "--method"} and n + 1 < len(args):
                    method = args[n + 1].upper()
                elif a.startswith("--method="):
                    method = a.split("=", 1)[1].upper()
            fields = any(a in {"-f", "-F", "--field", "--raw-field", "--input"} or a.startswith(("--field=", "--raw-field=", "--input=")) for a in args)
            if method in {"POST", "PUT", "PATCH", "DELETE"} or (fields and method in {"", "POST"}):
                hit("HTTP_WRITE", "gh api write")
    elif cmd in {"npm", "pnpm", "yarn", "bun"} and "publish" in [a for a in args if not a.startswith("-")][:2]:
        hit("PUBLISH", f"{cmd} publish")
    elif cmd in {"twine"} and sub == "upload" or cmd in {"cargo", "poetry", "uv", "hatch", "flit"} and sub == "publish" or cmd == "gem" and sub == "push":
        hit("PUBLISH", f"{cmd} {sub}")
    elif cmd in {"docker", "podman", "buildah"} and (sub == "push" or sub in {"image", "manifest"} and len(args) > 1 and args[1] == "push"):
        hit("PUBLISH", f"{cmd} push")
    elif cmd == "vercel" and ("--prod" in args or "--production" in args or sub == "promote"):
        hit("DEPLOY", "vercel production")
    elif cmd == "netlify" and sub == "deploy" and "--prod" in args:
        hit("DEPLOY", "netlify production")
    elif cmd in {"fly", "flyctl"} and sub in {"deploy", "scale", "destroy", "apps"}:
        hit("DEPLOY", f"{cmd} {sub}")
    elif cmd == "firebase" and sub == "deploy" or cmd in {"serverless", "sls"} and sub in {"deploy", "remove"}:
        hit("DEPLOY", f"{cmd} {sub}")
    elif cmd in {"kubectl", "oc"} and sub in {"apply", "delete", "rollout", "scale", "replace", "patch", "create", "edit", "drain", "cordon", "set", "annotate", "label"}:
        hit("DEPLOY", f"{cmd} {sub}")
    elif cmd == "helm" and sub in {"install", "upgrade", "uninstall", "delete", "rollback"}:
        hit("DEPLOY", f"helm {sub}")
    elif cmd == "helm" and sub == "push":
        hit("PUBLISH", "helm push")
    elif cmd == "heroku" and re.match(r"(releases:rollback|ps:(scale|restart|stop|kill)|apps:destroy|config:(set|unset)|pg:reset|maintenance:on|addons:destroy|run)", sub):
        hit("DEPLOY", f"heroku {sub}")
    elif cmd in {"terraform", "tofu"} and sub in {"apply", "destroy", "import", "taint"}:
        hit("CLOUD_DELETE" if sub == "destroy" else "DEPLOY", f"{cmd} {sub}")
    elif cmd == "pulumi" and sub in {"up", "destroy", "update"} or cmd == "cdk" and sub in {"deploy", "destroy"}:
        hit("DEPLOY", f"{cmd} {sub}")
    elif cmd == "ansible-playbook":
        hit("DEPLOY", "ansible-playbook")
    elif cmd in {"aws", "gcloud", "az", "doctl"}:
        verbs = [a for a in args if not a.startswith("-")]
        if any(re.search(r"^(delete|terminate|rm|remove|purge|deregister|destroy)", v) or "delete-" in v or "terminate-" in v for v in verbs):
            hit("CLOUD_DELETE", f"{cmd} delete or terminate")
        elif any(v in {"deploy", "create", "update", "put-object", "cp", "sync", "mv", "run-instances", "start", "stop"} or v.startswith(("create-", "update-", "put-")) for v in verbs):
            hit("DEPLOY", f"{cmd} change")
    elif cmd == "stripe":
        if sub in {"refunds", "charges", "payouts", "transfers", "payment_intents", "invoices", "subscriptions", "customers", "products", "prices"} and len(args) > 1 and args[1] in {"create", "update", "delete", "pay", "send", "cancel", "finalize", "capture", "confirm", "void"}:
            hit("MONEY", f"stripe {sub} {args[1]}")
        elif sub in {"post", "delete"}:
            hit("MONEY", f"stripe {sub}")
    elif cmd in {"curl", "wget", "http", "https", "xh"}:
        urls = [a for a in argv[1:] if re.match(r"https?://", a, re.I)] or [a for a in argv[1:] if re.match(r"[\w.-]+\.[a-z]{2,}/", a, re.I)]
        write = (re.search(r"(?i)(^|\s)(-X|--request|--method)\s*(POST|PUT|PATCH|DELETE)\b|-X(POST|PUT|PATCH|DELETE)\b", joined)
                 or any(a in {"-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "-F", "--form", "--json", "-T", "--upload-file", "--post-data", "--post-file"} or a.startswith(("--data", "--post")) for a in argv[1:])
                 or cmd in {"http", "https", "xh"} and len(argv) > 1 and argv[1].upper() in {"POST", "PUT", "PATCH", "DELETE"})
        remote = [u for u in urls if not _LOOPBACK.match(u)]
        if write and remote:
            hit("MONEY" if any(_MONEY_HOSTS.search(u) for u in remote) else "HTTP_WRITE", f"{cmd} write to {remote[0][:60]}")
    elif cmd in {"psql", "mysql", "mariadb", "sqlite3", "mongosh", "mongo", "cockroach", "clickhouse-client"}:
        if _SQL_WRITE.search(joined) or re.search(r"\.(drop|delete|update|insert|remove)\w*\(", joined):
            hit("DB_WRITE", f"{cmd} write statement")
    elif cmd == "redis-cli" and re.search(r"(?i)\b(flushall|flushdb|del|set|hset|expire|unlink)\b", joined):
        hit("DB_WRITE", "redis write")
    elif cmd in {"sendmail", "mail", "mailx", "mutt", "msmtp", "swaks"}:
        hit("MESSAGE", f"{cmd} sends email")
    elif cmd == "ssh":
        positional = [a for a in argv[1:] if not a.startswith("-")]
        if len(positional) >= 2:
            hit("DEPLOY", "remote command over ssh")
    elif cmd in {"scp", "rsync"} and any(re.match(r"^[\w.@-]+:", a) for a in argv[1:] if not a.startswith("-")):
        hit("DEPLOY", f"{cmd} to a remote host")
    elif cmd == "rm" and any(a.startswith("-") and ("r" in a or "f" in a) or a in {"--recursive", "--force"} for a in args):
        hit("DESTROY_LOCAL", "rm -r or -f")
    elif cmd == "find" and "-delete" in args:
        hit("DESTROY_LOCAL", "find -delete")
    elif cmd.split(".")[0] in _DESTROY_CMDS:
        hit("DESTROY_LOCAL", cmd)

    for pat in cfg.hold_patterns:
        if fnmatch.fnmatch(joined, pat) or fnmatch.fnmatch(cmd, pat):
            hits.append(("CUSTOM", f"matches hold rule {pat!r}"))
    if any(fnmatch.fnmatch(joined, pat) for pat in cfg.allow_patterns):
        hits = [h for h in hits if h[0] == "DESTROY_LOCAL"]
    return hits


def classify(tool_name: str, args: dict | None, cfg: PolicyConfig | None = None) -> Decision:
    """Return the hold decision for one tool call."""
    faults.check("policy")
    cfg = cfg or PolicyConfig()
    args = args or {}
    hits: list[tuple[str, str]] = []
    segments: list[str] = []
    name = (tool_name or "").lower()

    if name in {"terminal", "shell", "bash", "run_command", "process_manage"}:
        command = str(args.get("command") or args.get("cmd") or "")
        for argv in _split_segments(command):
            segments.append(" ".join(argv))
            hits.extend(_classify_argv(argv, cfg))
    elif name == "execute_code":
        code = str(args.get("code") or "")
        for m in re.finditer(r"""(?:run|call|check_output|check_call|Popen|system|popen)\(\s*(\[[^\]]*\]|f?["'][^"']*["'])""", code):
            raw = m.group(1)
            try:
                text = " ".join(json.loads(raw.replace("'", '"'))) if raw.startswith("[") else raw.strip("f\"'")
            except ValueError:
                text = raw
            for argv in _split_segments(text):
                segments.append(" ".join(argv))
                hits.extend(_classify_argv(argv, cfg))
        if re.search(r"(requests|httpx|aiohttp)\.(post|put|patch|delete)", code) or _PY_URLLIB_WRITE.search(code) \
                or re.search(r"\.request\(\s*['\"](post|put|patch|delete)['\"]", code, re.I):
            hits.append(("HTTP_WRITE", "code writes to a remote API"))
        if "smtplib" in code:
            hits.append(("MESSAGE", "code sends email"))
        if "shutil.rmtree" in code:
            hits.append(("DESTROY_LOCAL", "code deletes a folder tree"))
    elif name in {"write_file", "patch", "edit_file", "file_edit"} and cfg.workdir:
        path = str(args.get("path") or args.get("file_path") or "").replace("\\", "/")
        base = posixpath.normpath(cfg.workdir.replace("\\", "/"))
        norm = posixpath.normpath(path) if path else ""
        absolute = norm.startswith("/") or re.match(r"^[A-Za-z]:/", norm)
        if norm and absolute and not (norm + "/").startswith(base.rstrip("/") + "/"):
            hits.append(("WRITE_OUTSIDE", f"writes {path} outside {cfg.workdir}"))
    elif name == "send_message":
        hits.append(("MESSAGE", "send_message to a chat"))
    elif name.startswith("mcp__") or "__" in name:
        words = _tool_words(tool_name.split("__")[-1])
        strict, soft = _word_in(words, _TOOL_STRICT), _word_in(words, _TOOL_SOFT)
        read_first = bool(words) and words[0] in _TOOL_READ_FIRST
        if strict or (soft and not read_first):
            money = _word_in(words, _MONEY_WORDS)
            hits.append(("MONEY" if money else "HTTP_WRITE", f"tool {tool_name}"))
    for pat in cfg.hold_patterns:
        if fnmatch.fnmatch(name, pat):
            hits.append(("CUSTOM", f"matches hold rule {pat!r}"))

    classes: list[str] = []
    reasons: list[str] = []
    for cls, why in hits:
        if cls not in classes:
            classes.append(cls)
        reasons.append(why)
    return Decision(bool(classes), classes, reasons, segments)
