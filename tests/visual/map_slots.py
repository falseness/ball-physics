#!/usr/bin/env python3
"""Route map debug render (TASK-179).

Draws the js/routemap.js slot boxes (platform + 50x70 flag box), obstacle boxes, the central wall,
the portal openings, the hops and the menu-icon rect over the concept image, scaled to its size.

Usage: python3 tests/visual/map_slots.py --out OUT.png [--concept PNG] [--routemap PATH]
Boxes come from `node tests/visual/map_check.mjs --boxes`, so the render shows exactly what the
validator checked.
"""
import argparse
import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
CONCEPT = os.path.join(ROOT, 'artifacts', 'concepts', 'routemap', '305-wall-full.png')
COL = {'used': (80, 255, 140), 'spare': (255, 220, 60), 'flag': (120, 200, 255), 'solid': (255, 70, 70),
       'wall': (255, 140, 255), 'portal': (255, 160, 40), 'hop': (255, 255, 255), 'menu': (255, 255, 0)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--concept', default=CONCEPT)
    ap.add_argument('--routemap')
    a = ap.parse_args()
    cmd = ['node', os.path.join(HERE, 'map_check.mjs'), '--boxes']
    if a.routemap:
        cmd += ['--routemap', a.routemap]
    r = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(r.stdout)
    bx = data['boxes']
    img = Image.open(a.concept).convert('RGB')
    k = img.width / 1280.0
    # darken the concept a little so the boxes read
    img = Image.blend(img, Image.new('RGB', img.size, (0, 0, 0)), 0.35)
    d = ImageDraw.Draw(img, 'RGBA')
    try:
        font = ImageFont.truetype('DejaVuSans-Bold.ttf', int(11 * k))
    except OSError:
        font = ImageFont.load_default()
    S = lambda b: [b['x1'] * k, b['y1'] * k, b['x2'] * k, b['y2'] * k]
    P = lambda x, y: (x * k, y * k)
    # hops (straight polylines through the via points; 'gap' breaks the line)
    xy = bx['slotXY']
    for h in bx['hops']:
        pts = [(xy[h['from']][0], xy[h['from']][1] - 10)] + h['via'] + [(xy[h['to']][0], xy[h['to']][1] - 10)]
        for p, q in zip(pts, pts[1:]):
            if p == 'gap' or q == 'gap':
                continue
            d.line([P(*p), P(*q)], fill=COL['hop'] + (110,), width=int(1.5 * k))
        for v in h['via']:
            if v != 'gap':
                d.ellipse([P(v[0] - 3, v[1] - 3), P(v[0] + 3, v[1] + 3)], outline=COL['hop'], width=2)
    for s in bx['solids']:
        c = COL.get(s['kind'], COL['solid'])
        d.rectangle(S(s['box']), outline=c + (255,), fill=c + (50,), width=int(1.5 * k))
    d.rectangle(S(bx['menu']), outline=COL['menu'] + (255,), width=int(1.5 * k))
    for s in bx['slots']:
        c = COL['used'] if s['srcId'] is not None else COL['spare']
        d.rectangle(S(s['flag']), outline=COL['flag'] + (230,), width=int(1 * k))
        d.rectangle(S(s['platform']), outline=c + (255,), fill=c + (70,), width=int(1.5 * k))
        label = s['id'] + (' #%d' % s['srcId'] if s['srcId'] is not None else ' spare')
        d.text((s['flag']['x1'] * k + 3, s['flag']['y1'] * k + 2), label, fill=c + (255,), font=font)
    lines = ['routemap debug: green = used slot (slot id, srcId), yellow = spare, blue = flag box 50x70,',
             'red = obstacle box, magenta = central wall, orange = portal, yellow outline = menu icon, white = hops',
             'pass=%s levels=%d used=%d spare=%d minDist=%.1f overlaps=%d offscreen=%d' % (
                 data['pass'], data['levelCount'], data['slotsUsed'], data['spareSlots'], data['minSlotDistance'],
                 data['obstacleOverlaps'], data['offscreen'])]
    for i, t in enumerate(lines):
        d.text((40 * k, (8 + 12 * i) * k), t, fill=(255, 255, 255, 255), font=font)
    img.save(a.out)
    print(json.dumps({'out': a.out, 'pass': data['pass'], 'size': img.size}))


if __name__ == '__main__':
    main()
