"""API REST + dashboard — Passos 13/14 do roteiro.

Rodar (durante o desenvolvimento, so em 127.0.0.1):
    source config/camera.env
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

Abertura para a rede (http://<IP_AIBOX>:8000) so na validacao final com o professor.
"""

import time

import cv2
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from . import config, db
from .camera import pipeline

app = FastAPI(title="EduVision", version="1.0")


@app.on_event("startup")
def _startup():
    db.init_db()
    pipeline.start()


# ---- Stream MJPEG ----------------------------------------------------------
def _mjpeg():
    while True:
        with pipeline.lock:
            frame = None if pipeline.frame is None else pipeline.frame.copy()
        if frame is None:
            time.sleep(0.05)
            continue
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
               + buf.tobytes() + b"\r\n")


@app.get("/video")
def video():
    return StreamingResponse(
        _mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---- API (roteiro) ---------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "online" if pipeline.camera_online else "camera_offline"}


@app.get("/api/v1/classroom/status")
def classroom_status():
    return JSONResponse(pipeline.status())


@app.get("/api/v1/present")
def present():
    """Quem do grupo esta presente agora (confirmado)."""
    return {"room_id": config.ROOM_ID, "present": pipeline.present_people()}


@app.get("/api/v1/attendance")
def attendance():
    """Presencas registradas hoje (persistidas no SQLite)."""
    return {"date": time.strftime("%Y-%m-%d"), "attendance": db.today_attendance()}


# ---- Dashboard -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard():
    return f"""<!DOCTYPE html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>EduVision — {config.GROUP_ID}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#0C0D0E; color:#E4E6E8;
         font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif; }}
  header {{ padding:16px 24px; border-bottom:1px solid #2F3337;
            display:flex; align-items:center; gap:12px; }}
  header h1 {{ font-size:18px; margin:0; color:#00ff88; letter-spacing:.5px; }}
  header .tag {{ font-size:12px; color:#9199A1; }}
  .wrap {{ display:grid; grid-template-columns: 1fr 320px; gap:16px; padding:16px; }}
  @media (max-width:820px) {{ .wrap {{ grid-template-columns:1fr; }} }}
  .cam {{ background:#000; border:1px solid #2F3337; border-radius:10px; overflow:hidden; }}
  .cam img {{ width:100%; display:block; }}
  .panel {{ background:#161819; border:1px solid #2F3337; border-radius:10px; padding:16px; }}
  .panel h2 {{ font-size:13px; text-transform:uppercase; color:#9199A1;
               margin:0 0 12px; letter-spacing:.5px; }}
  .kpis {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:16px; }}
  .kpi {{ background:#0C0D0E; border:1px solid #2F3337; border-radius:8px; padding:10px; }}
  .kpi b {{ display:block; font-size:22px; color:#fff; }}
  .kpi span {{ font-size:11px; color:#9199A1; }}
  ul {{ list-style:none; margin:0; padding:0; }}
  li {{ display:flex; justify-content:space-between; padding:9px 10px; border-radius:8px;
        margin-bottom:6px; background:#0C0D0E; border:1px solid #2F3337; }}
  li .n {{ font-weight:600; }} li .s {{ color:#2F9E44; font-size:12px; }}
  .dot {{ width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px; }}
  .on {{ background:#2F9E44; }} .off {{ background:#DE535E; }}
</style></head><body>
<header>
  <h1>EDUVISION</h1>
  <span class="tag">Grupo {config.GROUP_ID} · Auditix AI · DATEN × FIAP</span>
  <span class="tag" id="cam-state">●</span>
</header>
<div class="wrap">
  <div class="cam"><img src="/video" alt="stream"></div>
  <div class="panel">
    <div class="kpis">
      <div class="kpi"><b id="k-present">0</b><span>presentes</span></div>
      <div class="kpi"><b id="k-enrolled">0</b><span>cadastrados</span></div>
      <div class="kpi"><b id="k-fps">0</b><span>fps</span></div>
      <div class="kpi"><b id="k-frames">0</b><span>frames</span></div>
    </div>
    <h2>Presentes agora</h2>
    <ul id="present-list"><li><span class="n">—</span></li></ul>
  </div>
</div>
<script>
async function tick() {{
  try {{
    const st = await (await fetch('/api/v1/classroom/status')).json();
    document.getElementById('k-present').textContent = st.presentes;
    document.getElementById('k-enrolled').textContent = st.cadastrados;
    document.getElementById('k-fps').textContent = st.fps;
    document.getElementById('k-frames').textContent = st.frames_processados;
    const cs = document.getElementById('cam-state');
    cs.innerHTML = '<span class="dot ' + (st.camera_online?'on':'off') +
                   '"></span>' + (st.camera_online?'câmera online':'câmera offline');
    const pr = await (await fetch('/api/v1/present')).json();
    const ul = document.getElementById('present-list');
    ul.innerHTML = pr.present.length ? pr.present.map(p =>
      '<li><span class="n">'+p.name+'</span><span class="s">✓ '+
      (p.confidence*100).toFixed(0)+'% · '+p.since+'</span></li>').join('')
      : '<li><span class="n" style="color:#9199A1">ninguém reconhecido ainda</span></li>';
  }} catch (e) {{}}
}}
setInterval(tick, 1500); tick();
</script>
</body></html>"""
