import json, pathlib, pytest
from abeyance.policy import classify, PolicyConfig

HELD = [
    ("git push origin main", "PUSH"), ("gh pr merge 42 --squash", "MERGE"), ("npm publish", "PUBLISH"),
    ("twine upload dist/*", "PUBLISH"), ("docker push ghcr.io/acme/app:latest", "PUBLISH"),
    ("terraform apply -auto-approve", "DEPLOY"), ("terraform destroy", "CLOUD_DELETE"),
    ("kubectl delete deployment web", "DEPLOY"), ("vercel --prod", "DEPLOY"),
    ("aws ec2 terminate-instances --instance-ids i-1", "CLOUD_DELETE"), ("stripe refunds create --charge ch_1", "MONEY"),
    ("curl -X POST https://api.stripe.com/v1/invoices/in_1/send", "MONEY"),
    ("curl -X DELETE https://api.github.com/repos/acme/app", "HTTP_WRITE"),
    ("psql $DATABASE_URL -c 'DELETE FROM invoices'", "DB_WRITE"), ("sendmail client@example.com < invoice.txt", "MESSAGE"),
    ("ssh prod 'systemctl restart app'", "DEPLOY"), ("rm -rf build", "DESTROY_LOCAL"),
    # disguises
    ("bash -c 'git push --force origin main'", "PUSH"), ("sudo -E env FOO=1 npm publish", "PUBLISH"),
    ("cd app && npm test && npm publish", "PUBLISH"), ("echo $(git push origin HEAD)", "PUSH"),
    ("timeout 60 fly deploy", "DEPLOY"), ("ls | xargs -I{} gh pr merge {}", "MERGE"), ("eval 'npm publish'", "PUBLISH"),
]
ALLOWED = ["git status", "git commit -m 'git push later'", "npm test", "npm ci", "curl https://api.github.com/repos/x",
           "curl -X POST http://localhost:8080/test", "docker build -t app .", "terraform plan", "kubectl get pods",
           "gh pr view 42", "psql -c 'SELECT 1'", "echo 'npm publish'", "aws s3 ls", "git log --oneline"]

@pytest.mark.parametrize("cmd,cls", HELD)
def test_held(cmd, cls):
    d = classify("terminal", {"command": cmd})
    assert d.hold and cls in d.classes, (cmd, d)

@pytest.mark.parametrize("cmd", ALLOWED)
def test_allowed(cmd):
    d = classify("terminal", {"command": cmd})
    assert not d.hold, (cmd, d)

def test_tools():
    assert classify("send_message", {"target": "telegram", "message": "hi"}).hold
    assert classify("mcp__stripe__create_refund", {}).classes == ["MONEY"]
    assert not classify("mcp__linear__list_issues", {}).hold
    assert classify("execute_code", {"code": "import subprocess\nsubprocess.run(['npm','publish'])"}).hold
    assert classify("write_file", {"path": "/etc/hosts"}, PolicyConfig(workdir="/srv/app")).hold
    assert not classify("write_file", {"path": "/srv/app/x.py"}, PolicyConfig(workdir="/srv/app")).hold

def test_config_rules():
    assert classify("terminal", {"command": "make release"}, PolicyConfig(hold_patterns=["make release*"])).hold
    assert not classify("terminal", {"command": "git push origin feature/x"}, PolicyConfig(allow_patterns=["git push origin feature/*"])).hold
    assert classify("terminal", {"command": "rm -rf build"}, PolicyConfig(allow_patterns=["rm -rf build"])).hold

def test_covers_every_world_command_hermes_missed():
    """The Phase 0 finding: every world-changing command Hermes's detector let through is held here."""
    probe = json.loads((pathlib.Path(__file__).parents[1] / "docs" / "detector_probe_2026-11-10.json").read_text())
    missed = [r["command"] for r in probe["world"] if not (r["dangerous"] or r["hardline"])]
    not_held = [c for c in missed if not classify("terminal", {"command": c}).hold]
    assert not not_held, not_held
