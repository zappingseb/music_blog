"""Local Flask app for choosing the header crop.

Phone photos are 4080x3072 while the header is a 830x194 letterbox strip, so a
centre crop is almost never the right framing. This serves a single page with an
aspect-locked crop box and live previews of both header variants, then hands the
chosen rectangle (in original-image coordinates) back to the CLI.
"""

from __future__ import annotations

import io
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file
from PIL import Image
from werkzeug.serving import make_server

from .config import GreenDuotone
from . import images

PREVIEW_MAX = 1600


class CropCancelled(RuntimeError):
    """The crop window was closed or cancelled without a selection."""


def _jpeg_response(image: Image.Image, quality: int = 88):
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    return send_file(buffer, mimetype="image/jpeg")


def build_app(
    source: Image.Image,
    target: tuple[int, int],
    green: GreenDuotone,
    state: dict,
    done: threading.Event,
    title: str,
    initial: images.Box | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    preview = source.copy()
    preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX), Image.LANCZOS)
    default_box = (
        images.clamp_box(initial, source.size)
        if initial
        else images.default_crop_box(source.size, target[0] / target[1])
    )

    def requested_box() -> images.Box:
        try:
            left = float(request.args["x"])
            top = float(request.args["y"])
            width = float(request.args["w"])
            height = float(request.args["h"])
        except (KeyError, ValueError):
            abort(400, "expected numeric x, y, w, h")
        return images.clamp_box((left, top, left + width, top + height), source.size)

    @app.get("/")
    def index() -> str:
        return _PAGE.format(
            title=title,
            preview_w=preview.width,
            preview_h=preview.height,
            source_w=source.width,
            source_h=source.height,
            target_w=target[0],
            target_h=target[1],
            box=list(default_box),
        )

    @app.get("/preview.jpg")
    def preview_jpg():
        return _jpeg_response(preview)

    @app.get("/out.jpg")
    def out_jpg():
        header = images.crop_and_resize(source, requested_box(), target)
        if request.args.get("green") == "1":
            header = images.green_duotone(header, green)
        return _jpeg_response(header)

    @app.post("/confirm")
    def confirm():
        payload = request.get_json(silent=True) or {}
        try:
            box = images.clamp_box(
                (
                    float(payload["x"]),
                    float(payload["y"]),
                    float(payload["x"]) + float(payload["w"]),
                    float(payload["y"]) + float(payload["h"]),
                ),
                source.size,
            )
        except (KeyError, TypeError, ValueError):
            return jsonify(ok=False, error="expected x, y, w, h"), 400
        state["box"] = box
        done.set()
        return jsonify(ok=True, box=list(box))

    @app.post("/cancel")
    def cancel():
        done.set()
        return jsonify(ok=True)

    return app


def choose_crop(
    image_path: Path,
    target: tuple[int, int],
    *,
    green: GreenDuotone | None = None,
    open_browser: bool = True,
    label: str | None = None,
    initial: images.Box | None = None,
) -> images.Box:
    """Open the crop UI and block until a rectangle is confirmed.

    Returns the box in original-image coordinates; raises :class:`CropCancelled`
    if the user cancels.
    """
    source = images.load_rgb(image_path)
    state: dict = {}
    done = threading.Event()
    app = build_app(
        source, target, green or GreenDuotone(), state, done,
        label or image_path.name, initial=initial,
    )

    server = make_server("127.0.0.1", 0, app, threaded=True)
    url = f"http://127.0.0.1:{server.server_port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"    crop this header at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        while not done.wait(0.2):
            pass
    except KeyboardInterrupt:
        raise CropCancelled("interrupted") from None
    finally:
        server.shutdown()
        thread.join(timeout=5)

    if "box" not in state:
        raise CropCancelled("no crop selected")
    return state["box"]


_PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<title>Header zuschneiden - {title}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #14161a; color: #e8eaed;
         font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  header {{ padding: 14px 20px; border-bottom: 1px solid #2a2e36; display: flex;
            align-items: baseline; gap: 14px; flex-wrap: wrap; }}
  h1 {{ font-size: 15px; margin: 0; font-weight: 600; }}
  .muted {{ color: #9aa0a6; font-size: 12px; }}
  main {{ padding: 20px; max-width: 1240px; margin: 0 auto; }}
  #stage {{ position: relative; display: inline-block; line-height: 0;
            user-select: none; touch-action: none; }}
  #stage img {{ display: block; max-width: 100%; height: auto; }}
  #shade {{ position: absolute; inset: 0; pointer-events: none;
            box-shadow: inset 0 0 0 9999px rgba(10,12,15,.62); }}
  #box {{ position: absolute; cursor: move; outline: 1px solid rgba(255,255,255,.95);
          box-shadow: 0 0 0 9999px rgba(10,12,15,.62); }}
  #box::after {{ content: ""; position: absolute; inset: 0; pointer-events: none;
          background: linear-gradient(to right, rgba(255,255,255,.2) 1px, transparent 1px) 33.33% 0/33.33% 100%,
                      linear-gradient(rgba(255,255,255,.2) 1px, transparent 1px) 0 50%/100% 50%; }}
  .h {{ position: absolute; width: 16px; height: 16px; background: #fff; border-radius: 50%;
        border: 2px solid #14161a; }}
  .h[data-c="nw"] {{ left: -8px; top: -8px; cursor: nwse-resize; }}
  .h[data-c="ne"] {{ right: -8px; top: -8px; cursor: nesw-resize; }}
  .h[data-c="sw"] {{ left: -8px; bottom: -8px; cursor: nesw-resize; }}
  .h[data-c="se"] {{ right: -8px; bottom: -8px; cursor: nwse-resize; }}
  .previews {{ display: flex; gap: 18px; flex-wrap: wrap; margin-top: 22px; }}
  .previews figure {{ margin: 0; }}
  .previews figcaption {{ font-size: 12px; color: #9aa0a6; margin-bottom: 6px; }}
  .previews img {{ display: block; max-width: 100%; border: 1px solid #2a2e36; background: #000; }}
  footer {{ position: sticky; bottom: 0; margin-top: 24px; padding: 14px 20px;
            background: #191c21; border-top: 1px solid #2a2e36; display: flex;
            gap: 10px; align-items: center; flex-wrap: wrap; }}
  button {{ font: inherit; padding: 8px 16px; border-radius: 6px; border: 1px solid #3a3f48;
            background: #23272e; color: #e8eaed; cursor: pointer; }}
  button:hover {{ background: #2c313a; }}
  button.primary {{ background: #2f7d4f; border-color: #2f7d4f; font-weight: 600; }}
  button.primary:hover {{ background: #37945d; }}
  code {{ color: #9aa0a6; font-size: 12px; }}
</style></head>
<body>
<header>
  <h1>Header zuschneiden</h1>
  <span class="muted">{title} &middot; {source_w}&times;{source_h} &rarr; {target_w}&times;{target_h}</span>
  <span class="muted">Ziehen zum Verschieben, Ecken zum Skalieren, Pfeiltasten fein (Shift = Breite)</span>
</header>
<main>
  <div id="stage">
    <img id="photo" src="/preview.jpg" alt="" draggable="false">
    <div id="box"><span class="h" data-c="nw"></span><span class="h" data-c="ne"></span>
                  <span class="h" data-c="sw"></span><span class="h" data-c="se"></span></div>
  </div>
  <div class="previews">
    <figure><figcaption>&lt;post_id&gt;.jpg</figcaption><img id="p1" alt=""></figure>
    <figure><figcaption>&lt;post_id&gt;_g.jpg (gr&uuml;n)</figcaption><img id="p2" alt=""></figure>
  </div>
</main>
<footer>
  <button class="primary" id="ok">Diesen Ausschnitt verwenden</button>
  <button id="reset">Zur&uuml;cksetzen</button>
  <button id="cancel">Abbrechen</button>
  <code id="readout"></code>
</footer>
<script>
const SRC = {{w: {source_w}, h: {source_h}}};
const PRE = {{w: {preview_w}, h: {preview_h}}};
const ASPECT = {target_w} / {target_h};
const DEFAULT = {box};
const stage = document.getElementById('stage');
const boxEl = document.getElementById('box');
const readout = document.getElementById('readout');
let box = {{x: DEFAULT[0], y: DEFAULT[1], w: DEFAULT[2] - DEFAULT[0], h: DEFAULT[3] - DEFAULT[1]}};

/* Displayed size differs from the preview's natural size on narrow screens. */
const shown = () => ({{w: stage.clientWidth || PRE.w, h: stage.clientHeight || PRE.h}});
const toView = v => v * (shown().w / SRC.w);
const toSrc  = v => v * (SRC.w / shown().w);

function clamp() {{
  box.w = Math.min(Math.max(box.w, 40), SRC.w);
  box.h = box.w / ASPECT;
  if (box.h > SRC.h) {{ box.h = SRC.h; box.w = box.h * ASPECT; }}
  box.x = Math.min(Math.max(0, box.x), SRC.w - box.w);
  box.y = Math.min(Math.max(0, box.y), SRC.h - box.h);
}}

let timer = null;
function draw() {{
  clamp();
  boxEl.style.left = toView(box.x) + 'px';
  boxEl.style.top = toView(box.y) + 'px';
  boxEl.style.width = toView(box.w) + 'px';
  boxEl.style.height = toView(box.h) + 'px';
  const q = `x=${{Math.round(box.x)}}&y=${{Math.round(box.y)}}&w=${{Math.round(box.w)}}&h=${{Math.round(box.h)}}`;
  readout.textContent = q.replace(/&/g, '  ');
  clearTimeout(timer);
  timer = setTimeout(() => {{
    document.getElementById('p1').src = '/out.jpg?' + q;
    document.getElementById('p2').src = '/out.jpg?' + q + '&green=1';
  }}, 150);
}}

let drag = null;
function start(ev, corner) {{
  ev.preventDefault();
  drag = {{corner, px: ev.clientX, py: ev.clientY, start: {{...box}}}};
  stage.setPointerCapture?.(ev.pointerId);
}}
boxEl.addEventListener('pointerdown', ev => {{
  if (!ev.target.dataset.c) start(ev, null);
}});
for (const handle of boxEl.querySelectorAll('.h')) {{
  handle.addEventListener('pointerdown', ev => {{ ev.stopPropagation(); start(ev, handle.dataset.c); }});
}}
window.addEventListener('pointermove', ev => {{
  if (!drag) return;
  const dx = toSrc(ev.clientX - drag.px), dy = toSrc(ev.clientY - drag.py);
  const s = drag.start;
  if (!drag.corner) {{
    box.x = s.x + dx; box.y = s.y + dy;
  }} else {{
    /* Width drives height so the ratio is always exact; the opposite edge stays put. */
    const west = drag.corner.includes('w');
    const north = drag.corner.includes('n');
    const right = s.x + s.w, bottom = s.y + s.h;
    let w = west ? s.w - dx : s.w + dx;
    w = Math.min(Math.max(w, 40), SRC.w);
    let h = w / ASPECT;
    if (h > SRC.h) {{ h = SRC.h; w = h * ASPECT; }}
    box.w = w; box.h = h;
    box.x = west ? right - w : s.x;
    box.y = north ? bottom - h : s.y;
  }}
  draw();
}});
window.addEventListener('pointerup', () => {{ drag = null; }});
window.addEventListener('keydown', ev => {{
  const step = ev.altKey ? 1 : 12;
  if (ev.key === 'ArrowLeft')  {{ ev.shiftKey ? box.w -= step : box.x -= step; }}
  else if (ev.key === 'ArrowRight') {{ ev.shiftKey ? box.w += step : box.x += step; }}
  else if (ev.key === 'ArrowUp')    {{ box.y -= step; }}
  else if (ev.key === 'ArrowDown')  {{ box.y += step; }}
  else if (ev.key === 'Enter') {{ confirm_(); return; }}
  else return;
  ev.preventDefault(); draw();
}});
window.addEventListener('resize', draw);

async function confirm_() {{
  const button = document.getElementById('ok');
  button.disabled = true; button.textContent = 'wird &uuml;bernommen...';
  await fetch('/confirm', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{x: Math.round(box.x), y: Math.round(box.y),
                          w: Math.round(box.w), h: Math.round(box.h)}})}});
  document.body.innerHTML = '<main><h1>Ausschnitt &uuml;bernommen</h1>' +
    '<p class="muted">Das Fenster kann geschlossen werden - das Skript l&auml;uft weiter.</p></main>';
}}
document.getElementById('ok').addEventListener('click', confirm_);
document.getElementById('reset').addEventListener('click', () => {{
  box = {{x: DEFAULT[0], y: DEFAULT[1], w: DEFAULT[2] - DEFAULT[0], h: DEFAULT[3] - DEFAULT[1]}};
  draw();
}});
document.getElementById('cancel').addEventListener('click', async () => {{
  await fetch('/cancel', {{method: 'POST'}});
  document.body.innerHTML = '<main><h1>Abgebrochen</h1></main>';
}});
document.getElementById('photo').addEventListener('load', draw);
draw();
</script>
</body></html>
"""
