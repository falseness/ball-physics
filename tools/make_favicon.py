#!/usr/bin/env python3
"""Generate the game's favicons: img/favicon-32.png and img/favicon-16.png.

Draws the '1-ball' concept at 512x512 with Canvas2D in headless Chromium (Playwright, the
same approach as tests/visual), then downsamples by stepwise halving with
imageSmoothingQuality 'high' (512 -> 256 -> ... -> 32 / 16). The RGBA pixels are read back
with getImageData and written as PNG by Python's zlib, so repeated runs are byte-identical.

The 16 px variant drops the grid and uses a thicker ring and hatch so the ball stays
legible after a 32x reduction.

Usage: python3 tools/make_favicon.py
"""
import os
import struct
import sys
import zlib

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = {32: os.path.join(ROOT, 'img', 'favicon-32.png'),
       16: os.path.join(ROOT, 'img', 'favicon-16.png')}

# Per-size drawing parameters (512 px master). 32 px follows the concept exactly.
VARIANTS = {
    32: {'corner': 96, 'grid': True, 'ring': 0.16, 'glow': 0.6, 'hatchW': 0.07, 'hatchGap': 0.28},
    16: {'corner': 112, 'grid': False, 'ring': 0.24, 'glow': 0.4, 'hatchW': 0.10, 'hatchGap': 0.32},
}

DRAW_JS = r"""
([size, v]) => {
  const S = 512;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const g = c.getContext('2d');
  // rounded square, radius 96
  const R = v.corner;
  const rr = () => { g.beginPath(); g.moveTo(R, 0); g.arcTo(S, 0, S, S, R); g.arcTo(S, S, 0, S, R);
                     g.arcTo(0, S, 0, 0, R); g.arcTo(0, 0, S, 0, R); g.closePath(); };
  rr();
  const bg = g.createLinearGradient(0, 0, S, S);
  bg.addColorStop(0, '#071a30'); bg.addColorStop(0.5, '#0b2747'); bg.addColorStop(1, '#040f1e');
  g.fillStyle = bg; g.fill();
  g.save(); rr(); g.clip();
  if (v.grid) {
    g.strokeStyle = 'rgba(92,200,255,0.16)'; g.lineWidth = 3;
    g.beginPath();
    for (let k = 128; k < S; k += 128) { g.moveTo(k, 0); g.lineTo(k, S); g.moveTo(0, k); g.lineTo(S, k); }
    g.stroke();
  }
  // ball
  const cx = S / 2, cy = S / 2, r = 150;
  g.beginPath(); g.arc(cx, cy, r, 0, 2 * Math.PI); g.fillStyle = '#0b2747'; g.fill();
  // hatch: inside the ring, lower-right half only (below the 45 deg diagonal x + y = cx + cy)
  g.save();
  g.beginPath(); g.arc(cx, cy, r, 0, 2 * Math.PI); g.clip();
  g.beginPath(); g.moveTo(cx + 2 * r, cy - 2 * r); g.lineTo(cx + 2 * r, cy + 2 * r);
  g.lineTo(cx - 2 * r, cy + 2 * r); g.closePath(); g.clip();
  g.strokeStyle = 'rgba(233,246,255,0.55)'; g.lineWidth = r * v.hatchW; g.lineCap = 'butt';
  g.beginPath();
  const gap = r * v.hatchGap;
  // strokes parallel to x - y = const ('/' direction, 45 deg), offset along the diagonal
  for (let d = gap * 0.5; d < 2 * r; d += gap) {
    // line through point (cx, cy) + d * (1/sqrt2, 1/sqrt2), direction (1, -1)
    const px = cx + d / Math.SQRT2, py = cy + d / Math.SQRT2;
    g.moveTo(px - 2 * r, py + 2 * r); g.lineTo(px + 2 * r, py - 2 * r);
  }
  g.stroke();
  g.restore();
  // ring with glow
  g.save();
  g.shadowColor = 'rgba(190,230,255,0.8)'; g.shadowBlur = r * v.glow;
  g.strokeStyle = '#e9f6ff'; g.lineWidth = r * v.ring;
  g.beginPath(); g.arc(cx, cy, r, 0, 2 * Math.PI); g.stroke();
  g.restore();
  g.restore();
  // stepwise halving with high-quality smoothing
  let cur = c;
  while (cur.width > size) {
    const n = document.createElement('canvas');
    n.width = n.height = cur.width / 2;
    const h = n.getContext('2d');
    h.imageSmoothingEnabled = true; h.imageSmoothingQuality = 'high';
    h.drawImage(cur, 0, 0, n.width, n.height);
    cur = n;
  }
  // re-cut the rounded square at the final size so the halving filter's bleed leaves the corners clear
  const f = cur.getContext('2d'), k = cur.width / S, Rf = v.corner * k, Sf = cur.width;
  f.globalCompositeOperation = 'destination-in';
  f.beginPath(); f.moveTo(Rf, 0); f.arcTo(Sf, 0, Sf, Sf, Rf); f.arcTo(Sf, Sf, 0, Sf, Rf);
  f.arcTo(0, Sf, 0, 0, Rf); f.arcTo(0, 0, Sf, 0, Rf); f.closePath();
  f.fillStyle = '#000'; f.fill();
  f.globalCompositeOperation = 'source-over';
  return Array.from(cur.getContext('2d').getImageData(0, 0, size, size).data);
}
"""


def png_bytes(w, h, rgba):
    raw = b''.join(b'\x00' + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content('<html><body></body></html>')
        for size, v in VARIANTS.items():
            px = page.evaluate(DRAW_JS, [size, v])
            with open(OUT[size], 'wb') as f:
                f.write(png_bytes(size, size, px))
            print('wrote', os.path.relpath(OUT[size], ROOT))
        browser.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
