#!/usr/bin/env python3
"""Check the relay tap's per-game-key split (/var/lib/ga-tap/events-<key>-<UTC day>.jsonl).

Sends one HMAC-signed GameAnalytics init (build 'test-split', unique user_id per run) for ball-physics
(/root/credentials/ball-physics/gameanalytics.json) and one for grapnelninja
(/root/credentials/grapnelninja/credentials.env) through https://stats.playdiplomacy.online, then checks each
landed in its own game's tap file and not in the other's. Writes compact JSON to --out (default stdout).
Needs network and read access to the tap dir (run on the relay host). Exit 0 = all checks pass.
The tap names a file by its own UTC write time, so the files of the start day and of the day after are both searched
(a run that crosses UTC midnight lands in the next day's file, TASK-230).
"""
import argparse, base64, datetime, hashlib, hmac, json, os, subprocess, sys, time, urllib.request, uuid

RELAY = 'https://stats.playdiplomacy.online'


def keys():
    bp = json.load(open('/root/credentials/ball-physics/gameanalytics.json'))
    env = {}
    for line in open('/root/credentials/grapnelninja/credentials.env'):
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.strip().split('=', 1)
            env[k] = v.strip().strip('"\'')
    return {'ball-physics': (bp['gameKey'], bp['secretKey']), 'grapnelninja': (env['GA_GAME_KEY'], env['GA_SECRET_KEY'])}


def signed_init(game_key, secret, user_id, build):
    body = json.dumps({'platform': 'webgl', 'os_version': 'webgl 0.0.0', 'sdk_version': 'rest api v2',
                       'build': build, 'user_id': user_id, 'random_salt': int(time.time())}).encode()
    auth = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    req = urllib.request.Request('%s/v2/%s/init' % (RELAY, game_key), data=body, method='POST',
                                 headers={'Content-Type': 'application/json', 'Authorization': auth,
                                          'User-Agent': 'ball-physics tap_split_check'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def hits(path, user_id):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            if user_id in line:
                b = json.loads(line).get('body')
                if isinstance(b, dict) and b.get('user_id') == user_id:
                    n += 1
    return n


def hits_all(paths, user_id):
    return sum(hits(p, user_id) for p in paths)


def size(path):
    return os.path.getsize(path) if os.path.exists(path) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out')
    ap.add_argument('--tap-dir', default='/var/lib/ga-tap')
    ap.add_argument('--build', default='test-split')
    a = ap.parse_args()
    start = datetime.datetime.utcnow()
    days = [(start + datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in (0, 1)]
    res = {'ts': datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z', 'build': a.build}
    active = subprocess.run(['systemctl', 'is-active', 'ga-tap'], capture_output=True, text=True).stdout.strip()
    res['ga_tap_active'] = active
    with urllib.request.urlopen(RELAY + '/health', timeout=30) as r:
        res['health'] = r.read().decode().strip()
    ks = keys()
    files = {g: [os.path.join(a.tap_dir, 'events-%s-%s.jsonl' % (k, day)) for day in days] for g, (k, _) in ks.items()}
    combined = [os.path.join(a.tap_dir, 'events-%s.jsonl' % day) for day in days]
    comb_before = [size(p) for p in combined]
    games = {}
    for g, (k, s) in ks.items():
        uid = 'tap-split-%s-%s' % (g, uuid.uuid4().hex[:12])
        games[g] = {'key': k, 'user_id': uid, 'status': signed_init(k, s, uid, a.build), 'file': files[g]}
    time.sleep(1)
    other = {'ball-physics': 'grapnelninja', 'grapnelninja': 'ball-physics'}
    for g, d in games.items():
        d['in_own_file'] = hits_all(files[g], d['user_id'])
        d['in_other_file'] = hits_all(files[other[g]], d['user_id'])
        d['in_combined_file'] = hits_all(combined, d['user_id'])
    res['games'] = games
    res['combined_file'] = {'path': combined, 'size_before': comb_before,
                            'size_after': [size(p) for p in combined]}
    checks = {'active': active == 'active', 'health_ok': res['health'] == 'ok'}
    for g, d in games.items():
        checks[g + '_200'] = d['status'] == 200
        checks[g + '_in_own_file'] = d['in_own_file'] == 1
        checks[g + '_not_in_other_file'] = d['in_other_file'] == 0
        checks[g + '_not_in_combined'] = d['in_combined_file'] == 0
    checks['combined_unchanged'] = res['combined_file']['size_before'] == res['combined_file']['size_after']
    res['checks'] = checks
    res['pass'] = all(checks.values())
    out = json.dumps(res, separators=(',', ':'))
    if a.out:
        open(a.out, 'w').write(out + '\n')
    print(out)
    return 0 if res['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
