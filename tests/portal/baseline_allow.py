"""Reviewed allowlists of front-side outcome changes against a pre-change baseline (TASK-201).

rimtrap.py / embed.py compare their outcomes case by case with a baseline recorded from the code BEFORE a change
(TASK-271: rimtrap / embed: tests/portal/baselines/{rimtrap,embed}_head_3bcf7b3.json, the TASK-270 elastic contact
model, allowlists tests/portal/allow/*_task271.json; before: *_head_4deacfa.json with *_task201.json). A changed
case passes the gate only when it is listed in the allowlist with exactly that baseline outcome and exactly that
new outcome (both pinned by hash), so any further change, any new changed case and any change of the baseline
fail again. Entries are produced by tests/portal/baseline_diverge.py, which replays each changed case in the
pre-change tree and in the current tree and records where they first diverge; only cases whose first divergent
step is in the ball's contact resolution (ball.physics()/move(), not portalStep(): the portal rules gave the same
answer on the same input) while the ball touches a wall-portal host line are listed ('host-contact-physics'), plus refused-exit bounces that
differ only by the contact model's energy cap ('blocked-bounce-energy-cap', same portalStep() decisions).

File format (compact JSON): {suite, baseline, baselineSha256, tree, why: {code: text}, cases: {key: [baseHash,
newHash, why, frame, step]}}; key = rimtrap 'orient|s|angle|speed', embed caseId.
"""
import hashlib
import json
import os


def outcome_hash(o):
    return hashlib.sha256(json.dumps(o, separators=(',', ':'), sort_keys=True).encode()).hexdigest()[:16]


def file_sha256(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load(path, baseline_path):
    """The allowlist at path ({} when path is empty); raises when it was made for another baseline file."""
    if not path:
        return None
    with open(path) as fh:
        al = json.load(fh)
    if al['baselineSha256'] != file_sha256(baseline_path):
        raise SystemExit('allowlist %s was made for another baseline (sha256 %s, %s has %s)'
                         % (path, al['baselineSha256'][:16], baseline_path, file_sha256(baseline_path)[:16]))
    return al


def accepted(al, key, base_outcome, new_outcome):
    """True when the change base -> new of case key is an allowlisted one."""
    if al is None:
        return False
    e = al['cases'].get(key)
    return e is not None and e[0] == outcome_hash(base_outcome) and e[1] == outcome_hash(new_outcome)


def rel(path, root):
    return os.path.relpath(path, root) if path else path
