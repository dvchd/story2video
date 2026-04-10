"""
main.py — FastAPI + Edge TTS + Client-side Video Rendering

Usage:
    pip install fastapi uvicorn edge-tts python-dotenv
    python main.py

Opens at http://localhost:8001
"""

import os, sys, json, uuid, re, asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edge_tts

if sys.platform == "win32":
    _orig = asyncio.get_event_loop_policy()
    def _quiet(loop, ctx):
        if isinstance(ctx.get("exception"), ConnectionResetError): return
        loop.default_exception_handler(ctx)
    class _P(type(_orig)):
        def new_event_loop(self):
            lp = super().new_event_loop(); lp.set_exception_handler(_quiet); return lp
    asyncio.set_event_loop_policy(_P())

PROXY = os.getenv("PROXY", "").strip() or None
PORT = int(os.getenv("PORT", "8001"))
VERSION = os.getenv("VERSION", "v1.2.0")
OUTPUT_DIR = Path("output"); OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Story2Video")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class TTSRequest(BaseModel):
    text: str; voice: str = "vi-VN-HoaiMyNeural"; rate: str = "+0%"; pitch: str = "+0Hz"

def srt_time_to_sec(ts):
    ts = ts.strip().replace(",", ".")
    p = ts.split(":")
    if len(p)==3: h,m,s=p
    elif len(p)==2: h="0"; m,s=p
    else: return 0.0
    return int(h)*3600+int(m)*60+float(s)

def parse_srt(srt):
    entries = []
    for block in re.split(r"\r?\n\s*\r?\n", srt.strip()):
        lines = block.strip().splitlines()
        idx = next((i for i,l in enumerate(lines) if "-->" in l), -1)
        if idx == -1: continue
        p = lines[idx].split("-->")
        if len(p)!=2: continue
        text = " ".join(lines[idx+1:]).strip()
        if text: entries.append({"start":round(srt_time_to_sec(p[0]),3),"end":round(srt_time_to_sec(p[1]),3),"text":text})
    return entries

def srt_to_vtt(srt):
    return "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt)

FEATURED = [
    {"name":"vi-VN-HoaiMyNeural","label":"Hoài My (Nữ)","locale":"vi-VN","gender":"Female"},
    {"name":"vi-VN-NamMinhNeural","label":"Nam Minh (Nam)","locale":"vi-VN","gender":"Male"},
    {"name":"en-US-JennyNeural","label":"Jenny (US F)","locale":"en-US","gender":"Female"},
    {"name":"en-US-GuyNeural","label":"Guy (US M)","locale":"en-US","gender":"Male"},
    {"name":"en-US-AriaNeural","label":"Aria (US F)","locale":"en-US","gender":"Female"},
    {"name":"en-US-DavisNeural","label":"Davis (US M)","locale":"en-US","gender":"Male"},
    {"name":"en-GB-SoniaNeural","label":"Sonia (UK F)","locale":"en-GB","gender":"Female"},
    {"name":"en-GB-RyanNeural","label":"Ryan (UK M)","locale":"en-GB","gender":"Male"},
    {"name":"ja-JP-NanamiNeural","label":"Nanami (JP)","locale":"ja-JP","gender":"Female"},
    {"name":"ja-JP-KeitaNeural","label":"Keita (JP)","locale":"ja-JP","gender":"Male"},
    {"name":"ko-KR-SunHiNeural","label":"Sun-Hi (KR)","locale":"ko-KR","gender":"Female"},
    {"name":"zh-CN-XiaoxiaoNeural","label":"Xiaoxiao (CN)","locale":"zh-CN","gender":"Female"},
    {"name":"zh-CN-YunxiNeural","label":"Yunxi (CN)","locale":"zh-CN","gender":"Male"},
    {"name":"fr-FR-DeniseNeural","label":"Denise (FR)","locale":"fr-FR","gender":"Female"},
    {"name":"de-DE-KatjaNeural","label":"Katja (DE)","locale":"de-DE","gender":"Female"},
    {"name":"es-ES-ElviraNeural","label":"Elvira (ES)","locale":"es-ES","gender":"Female"},
    {"name":"pt-BR-FranciscaNeural","label":"Francisca (BR)","locale":"pt-BR","gender":"Female"},
    {"name":"th-TH-PremwadeeNeural","label":"Premwadee (TH)","locale":"th-TH","gender":"Female"},
    {"name":"hi-IN-SwaraNeural","label":"Swara (IN)","locale":"hi-IN","gender":"Female"},
]

@app.post("/api/tts")
async def generate_tts(req: TTSRequest):
    jid = str(uuid.uuid4())[:8]; jd = OUTPUT_DIR/jid; jd.mkdir(parents=True, exist_ok=True)
    kw = dict(text=req.text, voice=req.voice, rate=req.rate, pitch=req.pitch)
    if PROXY: kw["proxy"] = PROXY
    comm = edge_tts.Communicate(**kw); sm = edge_tts.SubMaker(); ad = bytearray()
    async for c in comm.stream():
        if c["type"]=="audio": ad.extend(c["data"])
        elif c["type"] in ("WordBoundary","SentenceBoundary"): sm.feed(c)
    (jd/"audio.mp3").write_bytes(ad)
    srt = sm.get_srt(); (jd/"subtitles.srt").write_text(srt, encoding="utf-8")
    (jd/"subtitles.vtt").write_text(srt_to_vtt(srt), encoding="utf-8")
    js = parse_srt(srt); (jd/"subtitles.json").write_text(json.dumps(js, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"job_id":jid,"mp3_url":f"/output/{jid}/audio.mp3","srt_url":f"/output/{jid}/subtitles.srt",
            "vtt_url":f"/output/{jid}/subtitles.vtt","json_url":f"/output/{jid}/subtitles.json","subtitles":js}

@app.get("/api/voices")
async def list_voices():
    try:
        v = await edge_tts.list_voices(proxy=PROXY)
        return [{"name":x["ShortName"],"locale":x["Locale"],"gender":x["Gender"]} for x in v]
    except Exception as e:
        print(f"[WARN] list_voices: {e}")
        return [{"name":v["name"],"locale":v["locale"],"gender":v["gender"]} for v in FEATURED]

@app.get("/api/featured-voices")
async def featured_voices(): return FEATURED

@app.get("/output/{job_id}/{filename}")
async def serve_output(job_id: str, filename: str):
    fp = OUTPUT_DIR/job_id/Path(filename).name
    if not fp.exists(): raise HTTPException(404)
    t = {".mp3":"audio/mpeg",".srt":"text/plain",".vtt":"text/vtt",".json":"application/json"}
    return FileResponse(fp, media_type=t.get(fp.suffix,"application/octet-stream"))

FRONTEND_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Story2Video</title>
<style>
:root{--bg:#0f0f13;--sf:#1a1a24;--bd:#2a2a3a;--tx:#e4e4ef;--dm:#888899;--ac:#6c5ce7;--a2:#00cec9;--dn:#ff6b6b;--rd:10px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--tx);min-height:100vh}
.ctn{max-width:1150px;margin:0 auto;padding:24px 20px}
.hdr{display:flex;align-items:baseline;gap:12px;margin-bottom:6px;flex-wrap:wrap}
h1{font-size:1.6rem;font-weight:700} h1 span{color:var(--ac)}
.ver{font-size:.75rem;color:var(--dm);background:var(--sf);border:1px solid var(--bd);padding:2px 10px;border-radius:20px}
.sub{color:var(--dm);font-size:.9rem;margin-bottom:28px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start} /* Added align-items:start for sticky */
@media(max-width:768px){.grid{grid-template-columns:1fr}}

/* Right Panel Sticky */
.right-panel{position:sticky;top:24px;height:fit-content;}

.card{background:var(--sf);border:1px solid var(--bd);border-radius:var(--rd);padding:20px}
.card+.card{margin-top:18px}
.card h2{font-size:1rem;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.card h2 .badge{font-size:.7rem;background:var(--ac);color:#fff;padding:2px 8px;border-radius:20px}
label{display:block;font-size:.82rem;color:var(--dm);margin-bottom:5px;font-weight:500}
textarea{width:100%;min-height:120px;background:var(--bg);color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:12px;font-size:.92rem;resize:vertical;font-family:inherit}
textarea:focus,select:focus,input:focus{outline:none;border-color:var(--ac)}
select,input[type=text],input[type=number]{width:100%;background:var(--bg);color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:9px 12px;font-size:.88rem}
.row{display:flex;gap:12px;margin-top:12px} .row>div{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:11px 22px;border:none;border-radius:8px;font-size:.92rem;font-weight:600;cursor:pointer;transition:all .15s}
.btn-p{background:var(--ac);color:#fff;width:100%;margin-top:18px} .btn-p:hover{opacity:.88} .btn-p:disabled{opacity:.4;cursor:not-allowed}
.btn-e{background:var(--a2);color:#000;width:100%;margin-top:12px} .btn-e:hover{opacity:.88} .btn-e:disabled{opacity:.4;cursor:not-allowed}
.btn-d{background:0 0;border:1px solid var(--bd);color:var(--tx);padding:8px 16px;font-size:.82rem;border-radius:6px;text-decoration:none} .btn-d:hover{border-color:var(--ac)}
.preview-wrap{position:relative;background:#000;border-radius:8px;overflow:hidden}
.preview-wrap canvas{width:100%;display:block}
.progress-bar{width:100%;height:6px;background:var(--bg);border-radius:3px;margin-top:12px;overflow:hidden}
.progress-bar .fill{height:100%;background:linear-gradient(90deg,var(--ac),var(--a2));width:0%;transition:width .3s;border-radius:3px}
.status{font-size:.82rem;color:var(--dm);margin-top:8px;min-height:1.2em} .status.error{color:var(--dn)}
.downloads{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.sgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}
.color-row{display:flex;align-items:center;gap:8px}
.color-row input[type=color]{width:36px;height:36px;border:none;border-radius:6px;cursor:pointer;background:0 0;padding:0}
.color-row input[type=text]{flex:1}
.srt-pre{margin-top:14px;max-height:140px;overflow-y:auto;background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:10px 14px;font-family:'Cascadia Code','Fira Code',monospace;font-size:.78rem;color:var(--dm);white-space:pre-wrap;line-height:1.5}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{padding:5px 12px;border-radius:6px;font-size:.78rem;cursor:pointer;border:1px solid var(--bd);background:0 0;color:var(--dm);transition:all .15s;white-space:nowrap}
.chip:hover{border-color:var(--ac);color:var(--tx)} .chip.active{background:var(--ac);border-color:var(--ac);color:#fff}
.format-note{font-size:.75rem;color:var(--dm);margin-top:6px;font-style:italic}

/* opacity slider */
.opacity-row{display:flex;align-items:center;gap:8px;margin-top:6px}
.opacity-row input[type=range]{flex:1;accent-color:var(--ac);height:4px;cursor:pointer}
.opacity-row .ov{font-size:.78rem;color:var(--dm);min-width:36px;text-align:right}

/* images/video */
.img-upload{margin-top:12px;border:2px dashed var(--bd);border-radius:8px;padding:14px;text-align:center;cursor:pointer;transition:border-color .15s;position:relative}
.img-upload:hover{border-color:var(--ac)}
.img-upload input{position:absolute;inset:0;opacity:0;cursor:pointer}
.img-upload .lbl{font-size:.82rem;color:var(--dm)} .img-upload .lbl b{color:var(--ac)}
.img-list{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.img-item{display:flex;align-items:center;gap:8px;background:var(--bg);border:1px solid var(--bd);border-radius:8px;padding:8px 10px;transition:border-color .15s,opacity .2s}
.img-item:hover{border-color:var(--ac)} .img-item.dragging{opacity:.4;border-style:dashed} .img-item.drag-over{border-color:var(--a2);border-width:2px}
.img-item .handle{cursor:grab;color:var(--dm);font-size:1.1rem;user-select:none;padding:0 4px} .img-item .handle:active{cursor:grabbing}
.sort-btns{display:flex;flex-direction:column;gap:3px;flex-shrink:0}
.sort-btns button{background:var(--sf);border:1px solid var(--bd);color:var(--dm);border-radius:4px;font-size:.65rem;padding:3px 6px;cursor:pointer;display:flex;align-items:center;justify-content:center}
.sort-btns button:hover{background:var(--ac);color:#fff;border-color:var(--ac)}
.img-item img{width:48px;height:36px;object-fit:cover;border-radius:4px;flex-shrink:0;cursor:pointer}
.img-item .info{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.img-item .name{font-size:.78rem;color:var(--dm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.img-item .dur-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.img-item .dur-row input[type=number]{width:64px;padding:4px 6px;font-size:.8rem;text-align:center;border-radius:4px}
.img-item .dur-row input[type=range]{width:70px; height:24px; cursor:pointer; accent-color:var(--a2);}
.img-item .dur-row span{font-size:.75rem;color:var(--dm)}
.img-item .btn-icon{background:var(--sf); color:var(--tx); border:1px solid var(--bd); padding:4px 8px; font-size:0.75rem; border-radius:4px; cursor:pointer;}
.img-item .btn-icon:hover{background:var(--ac); border-color:var(--ac);}
.img-item .rm{color:var(--dn);cursor:pointer;border:none;background:0 0;font-size:1rem;padding:6px 10px;flex-shrink:0;border-radius:6px} .img-item .rm:hover{background:rgba(255,107,107,0.1)}
.timeline-bar{display:flex;height:24px;border-radius:6px;overflow:hidden;margin-top:8px;background:var(--bg);border:1px solid var(--bd);cursor:pointer;}
.timeline-bar .seg{display:flex;align-items:center;justify-content:center;font-size:.68rem;color:#fff;overflow:hidden;white-space:nowrap;transition:width .3s;pointer-events:none;}
.img-count{font-size:.78rem;color:var(--dm);margin-top:6px}

/* New Toggles */
.chk-row{display:flex;align-items:center;gap:8px;margin-top:10px}
.chk-row input{accent-color:var(--ac);width:16px;height:16px;cursor:pointer}
.chk-row label{margin:0;cursor:pointer;font-size:.82rem;color:var(--tx)}

/* Adv Settings Collapsible */
details.adv-set { margin-top: 18px; background: var(--bg); border: 1px solid var(--bd); border-radius: 8px; }
details.adv-set summary { padding: 12px 14px; font-weight: 600; font-size: 0.9rem; cursor: pointer; user-select: none; color: var(--tx); outline: none;}
details.adv-set summary:hover { color: var(--ac); }
.adv-content { padding: 14px; border-top: 1px solid var(--bd); display: flex; flex-direction: column; gap: 14px; }
.adv-section { border-bottom: 1px dashed var(--bd); padding-bottom: 14px; }
.adv-section:last-child { border-bottom: none; padding-bottom: 0; }

.inline-btn { background: var(--sf); color: var(--tx); border: 1px solid var(--bd); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75rem; font-weight: bold;}
.inline-btn:hover { background: var(--ac); border-color: var(--ac); color: white;}
.inline-remove-btn { background: var(--dn); color: white; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75rem; font-weight: bold;}
.inline-remove-btn:hover { opacity: 0.8; }
.thumb-preview { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap:wrap;}
.thumb-preview img { height: 36px; border-radius: 4px; border: 1px solid var(--bd); object-fit: contain; cursor:pointer;}

/* Modal Preview */
.modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 1000; align-items: center; justify-content: center; flex-direction: column; backdrop-filter: blur(5px);}
.modal.active { display: flex; }
.modal-content { max-width: 90%; max-height: 80vh; position:relative; }
.modal-content img, .modal-content video { max-width: 100%; max-height: 80vh; border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
.modal-close { margin-top: 20px; background: var(--dn); color: #fff; border: none; padding: 10px 24px; border-radius: 8px; cursor: pointer; font-weight:bold; font-size:1rem;}
.modal-close:hover { opacity: 0.8; }
</style>
</head>
<body>

<!-- MEDIA PREVIEW MODAL -->
<div class="modal" id="mediaModal">
    <div class="modal-content" id="modalContent"></div>
    <button class="modal-close" onclick="closeModal()">✕ Đóng</button>
</div>

<div class="ctn">
<div class="hdr">
  <h1>Story<span>2</span>Video</h1>
  <span class="ver">{{VERSION}}</span>
</div>
<p class="sub">Edge TTS → MP3 + SRT/VTT → Client-side Video Rendering</p>
<div class="grid">

<!-- ═══ LEFT PANEL ═══ -->
<div class="left-panel">
<div class="card">
  <h2>Input <span class="badge">Edge TTS</span></h2>
  <label>Text</label>
  <textarea id="inputText" placeholder="Nhập văn bản…">Xin chào! Bản cập nhật này đã ghim cố định màn hình Preview bên phải để bạn dễ theo dõi. Ngoài ra bạn có thể nghe thử BGM, xem trước kích thước thật của ảnh/video, và lỗi âm thanh lúc tua cũng đã được khắc phục hoàn toàn!</textarea>
  <label style="margin-top:14px">Quick Voice</label>
  <div class="chips" id="voiceTabs"></div>
  <div class="row">
    <div><label>All Voices</label><select id="voiceSelect"><option value="vi-VN-HoaiMyNeural">vi-VN-HoaiMyNeural</option></select></div>
    <div><label>Rate</label><select id="rateSelect">
      <option value="-50%">0.5x</option><option value="-30%">0.7x</option><option value="-15%">0.85x</option>
      <option value="+0%" selected>1.0x</option><option value="+15%">1.15x</option><option value="+30%">1.3x</option><option value="+50%">1.5x</option>
    </select></div>
  </div>
  <button class="btn btn-p" id="btnGen" onclick="genTTS()">Generate MP3 + Subtitles</button>
  <div class="status" id="stTTS"></div>
  <div class="downloads" id="dlLinks"></div>
  <div class="srt-pre" id="srtPre" style="display:none"></div>
</div>

<div class="card">
  <h2>Video Settings</h2>
  <label>Preset</label>
  <div class="chips" id="presetChips">
    <button class="chip active" data-w="1280" data-h="720">YouTube 720p</button>
    <button class="chip" data-w="1920" data-h="1080">YouTube 1080p</button>
    <button class="chip" data-w="1080" data-h="1920">TikTok</button>
    <button class="chip" data-w="1080" data-h="1080">Square</button>
    <button class="chip" data-w="" data-h="">Custom</button>
  </div>
  <div class="sgrid">
    <div><label>Width</label><input type="number" id="vidW" value="1280"></div>
    <div><label>Height</label><input type="number" id="vidH" value="720"></div>
    <div><label>FPS</label><select id="vidFPS"><option value="24">24</option><option value="30" selected>30</option><option value="60">60</option></select></div>
    <div><label>Font Size</label><input type="number" id="fontSize" value="48"></div>
  </div>

  <div style="margin-top:14px">
    <label>Background Color (fallback)</label>
    <div class="color-row">
      <input type="color" id="bgColor" value="#1a1a2e" oninput="$('bgColorText').value=this.value">
      <input type="text" id="bgColorText" value="#1a1a2e" oninput="$('bgColor').value=this.value">
    </div>
  </div>

  <!-- Image/Video Manager -->
  <div style="margin-top:14px; border-top:1px dashed var(--bd); padding-top:14px;">
    <label>Background Media (Images/Videos)</label>
    
    <!-- Toggles -->
    <div class="chk-row">
      <input type="checkbox" id="kenBurns" checked onchange="drawFrame(-1)">
      <label for="kenBurns">Hiệu ứng ảnh động (Ken Burns Zoom)</label>
    </div>
    <div class="chk-row" style="margin-bottom:10px">
      <input type="checkbox" id="blurBg" checked onchange="drawFrame(-1)">
      <label for="blurBg">Nền mờ (Blur Fit Mode thay vì Crop)</label>
    </div>

    <div class="img-upload" style="margin-top:0;">
      <input type="file" accept="image/*,video/*" multiple id="bgFileInput" onchange="handleImgUpload(this)">
      <div class="lbl"><b>Click or drop</b> images/videos here (multiple)</div>
    </div>
    <div class="img-list" id="imgList"></div>
    <div class="timeline-bar" id="timelineBar" title="Click để tua"></div>
    <div class="img-count" id="imgCount"></div>
  </div>

  <!-- Advanced Settings (Collapsible) -->
  <details class="adv-set">
    <summary>Cài đặt nâng cao (BGM, Watermark, Màu sắc) ⚙️</summary>
    <div class="adv-content">
        
        <!-- BGM -->
        <div class="adv-section">
            <label>Nhạc nền (BGM)</label>
            <div class="img-upload" style="margin-top:4px; padding:10px;">
              <input type="file" accept="audio/*" id="bgmInput" onchange="handleBgmUpload(this)">
              <div class="lbl"><b>Upload MP3/WAV</b></div>
            </div>
            <div class="thumb-preview" id="bgmPreviewWrap" style="display:none; flex-wrap:wrap; align-items:center;">
                <span id="bgmName" style="color:var(--tx); font-size:0.8rem; max-width: 150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"></span>
                <button class="inline-btn" onclick="previewMedia('audio', bgm.el.src)" title="Nghe thử">🔊 Nghe</button>
                <div style="flex:1"></div>
                <div class="chk-row" style="margin:0"><input type="checkbox" id="bgmLoop" checked onchange="if(bgm.el) bgm.el.loop=this.checked;"><label for="bgmLoop">Lặp</label></div>
                <button class="inline-remove-btn" onclick="removeBgm()" title="Xóa nhạc nền">✕</button>
            </div>
            <div class="opacity-row" style="margin-top:10px">
              <span style="font-size:.78rem;color:var(--dm)">Âm lượng</span>
              <input type="range" id="bgmVol" min="0" max="100" value="15" oninput="updateBgmVol(this.value)">
              <span class="ov" id="bgmVolVal">15%</span>
            </div>
        </div>

        <!-- Watermark -->
        <div class="adv-section">
            <label>Watermark / Logo</label>
            <div class="sgrid" style="grid-template-columns: 2fr 1fr; gap:10px; margin-top:4px">
                <div class="img-upload" style="margin-top:0; padding:8px"><input type="file" accept="image/*" id="wmFileInput" onchange="handleWmUpload(this)"><div class="lbl"><b>Upload Logo</b></div></div>
                <div><label>Vị trí</label><select id="wmPos" onchange="drawFrame(-1)"><option value="tl">Top-Left</option><option value="tr">Top-Right</option><option value="bl">Bot-Left</option><option value="br" selected>Bot-Right</option></select></div>
            </div>
            <div class="thumb-preview" id="wmPreviewWrap" style="display:none;">
                <span style="font-size:0.8rem;color:var(--dm)">Ảnh:</span>
                <img id="wmPreviewImg" src="" onclick="previewMedia('image', this.src)">
                <button class="inline-btn" onclick="previewMedia('image', wm.img.src)" title="Xem">👁️</button>
                <div style="flex:1"></div>
                <button class="inline-remove-btn" onclick="removeWm()" title="Xóa Watermark">✕</button>
            </div>
            <div class="opacity-row" style="margin-top:10px">
              <span style="font-size:.78rem;color:var(--dm)">Kích thước</span>
              <input type="range" id="wmScale" min="5" max="100" value="15" oninput="$('wmScaleVal').textContent=this.value+'%'; drawFrame(-1)">
              <span class="ov" id="wmScaleVal">15%</span>
            </div>
            <div class="opacity-row">
              <span style="font-size:.78rem;color:var(--dm)">Độ mờ</span>
              <input type="range" id="wmOpacity" min="0" max="100" value="60" oninput="$('wmOv').textContent=this.value+'%'; drawFrame(-1)">
              <span class="ov" id="wmOv">60%</span>
            </div>
        </div>

        <!-- Colors -->
        <div class="adv-section">
            <label>Text Color</label>
            <div class="color-row">
              <input type="color" id="textColor" value="#ffffff" oninput="$('textColorText').value=this.value">
              <input type="text" id="textColorText" value="#ffffff" oninput="$('textColor').value=this.value">
            </div>
            <div class="opacity-row">
              <span style="font-size:.78rem;color:var(--dm)">Opacity</span>
              <input type="range" id="textOpacity" min="0" max="100" value="100" oninput="$('toVal').textContent=this.value+'%'">
              <span class="ov" id="toVal">100%</span>
            </div>
            
            <label style="margin-top:10px">Highlight Color</label>
            <div class="color-row">
              <input type="color" id="hlColor" value="#6c5ce7" oninput="$('hlColorText').value=this.value">
              <input type="text" id="hlColorText" value="#6c5ce7" oninput="$('hlColor').value=this.value">
            </div>
            <div class="opacity-row">
              <span style="font-size:.78rem;color:var(--dm)">Opacity</span>
              <input type="range" id="hlOpacity" min="0" max="100" value="40" oninput="$('hoVal').textContent=this.value+'%'">
              <span class="ov" id="hoVal">40%</span>
            </div>
        </div>

    </div>
  </details>
</div>
</div>

<!-- ═══ RIGHT PANEL (STICKY) ═══ -->
<div class="right-panel">
<div class="card">
  <h2>Preview <span class="badge">Canvas</span></h2>
  <div class="preview-wrap"><canvas id="cvs" width="1280" height="720"></canvas></div>
  <div style="display:flex;gap:8px;margin-top:14px">
    <button class="btn btn-p" style="flex:1;margin:0" id="btnPlay" onclick="playPrev()" disabled>▶ Play</button>
    <button class="btn btn-d" id="btnStop" onclick="stopPrev()" disabled>■ Stop</button>
  </div>
  <p style="font-size:0.75rem; color:var(--dm); margin-top:8px; text-align:center;">💡 <i>Mẹo: Click vào thanh Timeline màu sắc phía bên trái để tua nhanh Video.</i></p>
</div>
<div class="card">
  <h2>Export <span class="badge">Client-side</span></h2>
  <div class="row" style="margin-top:0">
    <div><label>Format</label><select id="expFmt"><option value="mp4" selected>MP4 (H.264)</option><option value="webm">WebM (VP9)</option></select></div>
    <div><label>Bitrate</label><select id="expBr"><option value="3000000">3 Mbps</option><option value="5000000" selected>5 Mbps</option><option value="8000000">8 Mbps</option><option value="12000000">12 Mbps</option></select></div>
  </div>
  <button class="btn btn-e" id="btnExp" onclick="exportVid()" disabled>Export Video</button>
  <p class="format-note" id="fmtNote"></p>
  <div class="progress-bar"><div class="fill" id="expFill"></div></div>
  <div class="status" id="stExp"></div>
</div>
</div>

</div>
</div>

<script>
const $=id=>document.getElementById(id);
const SEG_COLORS=['#6c5ce7','#00cec9','#e17055','#fdcb6e','#a29bfe','#55efc4','#fab1a0','#74b9ff','#ff7675','#81ecec'];

let audioBuf=null,audioCtx=null,subs=[],isPlay=false,aFrame=null,srcNode=null,t0=0;
let bgImages=[],totalDur=10,dragIdx=-1,curTime=0;

// BGM & Watermark Objects
let bgm = { el: null, src: null, gain: null, vol: 0.15 };
let wm = { img: null };

// ══ UI HELPERS ══════════════════════════════════════════════════════════════
function previewMedia(type, url) {
    const mc = $('modalContent'); mc.innerHTML = '';
    if(type==='image') { mc.innerHTML = `<img src="${url}">`; }
    else if(type==='video') { mc.innerHTML = `<video src="${url}" controls autoplay loop></video>`; }
    else if(type==='audio') { mc.innerHTML = `<audio src="${url}" controls autoplay style="width:300px; height:50px;"></audio>`; }
    $('mediaModal').classList.add('active');
}
function closeModal() {
    $('modalContent').innerHTML = ''; // automatically stops audio/video playing
    $('mediaModal').classList.remove('active');
}

function uid(){return Math.random().toString(36).slice(2,8);}
function hexRgba(hex,a){
  const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${a})`;
}

// ══ AUDIO CONTEXT ═══════════════════════════════════════════════════════════
function initAudioCtx() {
  if(!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  bgImages.forEach(item => {
    if(item.type === 'video' && !item.mediaSrc) {
       item.vid.muted = false; // Bật tiếng cho WebAudio xử lý
       item.mediaSrc = audioCtx.createMediaElementSource(item.vid);
       item.gainNode = audioCtx.createGain();
       item.gainNode.gain.value = item.volume;
       item.mediaSrc.connect(item.gainNode);
       item.gainNode.connect(audioCtx.destination);
    }
  });
  // Setup BGM
  if(bgm.el && !bgm.src) {
       bgm.src = audioCtx.createMediaElementSource(bgm.el);
       bgm.gain = audioCtx.createGain();
       bgm.gain.gain.value = bgm.vol;
       bgm.src.connect(bgm.gain);
       bgm.gain.connect(audioCtx.destination);
  }
}

// ══ BGM & WATERMARK HANDLERS ══
function updateBgmVol(v) {
  $('bgmVolVal').textContent=v+'%'; bgm.vol = parseInt(v)/100;
  if(bgm.gain) bgm.gain.gain.value = bgm.vol;
}
function handleBgmUpload(input) {
  const file = input.files[0]; if(!file) return;
  if(bgm.el) { bgm.el.pause(); bgm.el.src=''; bgm.src = null; }
  bgm.el = new Audio(URL.createObjectURL(file));
  bgm.el.loop = $('bgmLoop').checked; 
  bgm.el.crossOrigin = "anonymous";
  $('bgmName').textContent = file.name;
  $('bgmPreviewWrap').style.display = 'flex';
}
function removeBgm() {
  if(bgm.el) { bgm.el.pause(); bgm.el.src=''; bgm.src = null; bgm.el = null; }
  $('bgmInput').value = '';
  $('bgmPreviewWrap').style.display = 'none';
}

function handleWmUpload(input) {
  const file = input.files[0]; if(!file) return;
  const img = new Image(); 
  img.onload = () => { 
      wm.img = img; 
      $('wmPreviewImg').src = img.src;
      $('wmPreviewWrap').style.display = 'flex';
      drawFrame(curTime); 
  };
  img.src = URL.createObjectURL(file);
}
function removeWm() {
  wm.img = null;
  $('wmFileInput').value = '';
  $('wmPreviewWrap').style.display = 'none';
  drawFrame(curTime);
}

// ══ PRESETS ══════════════════════════════════════════════════════════════════
document.querySelectorAll('#presetChips .chip').forEach(c=>{
  c.addEventListener('click',()=>{
    document.querySelectorAll('#presetChips .chip').forEach(x=>x.classList.remove('active'));c.classList.add('active');
    if(c.dataset.w&&c.dataset.h){$('vidW').value=c.dataset.w;$('vidH').value=c.dataset.h;
      $('fontSize').value=parseInt(c.dataset.w)/parseInt(c.dataset.h)<1?40:48;}
    drawFrame(curTime);
  });
});
['vidW','vidH'].forEach(id=>$(id).addEventListener('input',()=>{
  document.querySelectorAll('#presetChips .chip').forEach(c=>c.classList.remove('active'));
  document.querySelector('#presetChips .chip:last-child').classList.add('active');
  drawFrame(curTime);
}));

// ══ MIME ═════════════════════════════════════════════════════════════════════
function pickMime(mp4){
  const a=['video/mp4;codecs=avc1.42E01E,mp4a.40.2','video/mp4;codecs=avc1,mp4a.40.2','video/mp4;codecs=avc1.42E01E,opus','video/mp4;codecs=avc1,opus','video/mp4'];
  const b=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'];
  for(const m of(mp4?[...a,...b]:[...b,...a]))if(MediaRecorder.isTypeSupported(m))return m;return'video/webm';
}
function updFmt(){const m=pickMime($('expFmt').value==='mp4');$('fmtNote').textContent='Codec: '+m+(!m.startsWith('video/mp4')&&$('expFmt').value==='mp4'?' (fallback WebM)':'');}
$('expFmt').addEventListener('change',updFmt);setTimeout(updFmt,100);

// ══ VOICES ══════════════════════════════════════════════════════════════════
(async()=>{try{const r=await fetch('/api/featured-voices'),f=await r.json(),t=$('voiceTabs');
f.forEach(v=>{const b=document.createElement('button');b.className='chip'+(v.name==='vi-VN-HoaiMyNeural'?' active':'');
b.textContent=v.label;b.onclick=()=>{t.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));b.classList.add('active');
const s=$('voiceSelect');s.value=v.name;if(s.value!==v.name){const o=document.createElement('option');o.value=v.name;o.textContent=v.name;s.prepend(o);s.value=v.name;}};
t.appendChild(b);});}catch(e){}})();
(async()=>{try{const r=await fetch('/api/voices'),v=await r.json(),s=$('voiceSelect');s.innerHTML='';
const g={};v.forEach(x=>{if(!g[x.locale])g[x.locale]=[];g[x.locale].push(x);});
const pr=['vi-VN','en-US','en-GB','ja-JP','ko-KR','zh-CN','fr-FR','de-DE','es-ES','pt-BR','th-TH','hi-IN'];
Object.keys(g).sort((a,b)=>{const ai=pr.indexOf(a),bi=pr.indexOf(b);if(ai>-1&&bi>-1)return ai-bi;if(ai>-1)return-1;if(bi>-1)return 1;return a.localeCompare(b);})
.forEach(l=>{const og=document.createElement('optgroup');og.label=l;g[l].forEach(x=>{const o=document.createElement('option');o.value=x.name;o.textContent=`${x.name} (${x.gender})`;
if(x.name==='vi-VN-HoaiMyNeural')o.selected=true;og.appendChild(o);});s.appendChild(og);});}catch(e){}})();

// ══ MEDIA MANAGER (IMAGES & VIDEOS) ═════════════════════════════════════════
function handleImgUpload(input){
  const files=Array.from(input.files);let loaded=0;
  const checkDone = () => { loaded++; if(loaded===files.length){redistEqual();renderImgUI();drawFrame(curTime);} };
  
  files.forEach(f=>{
    const url=URL.createObjectURL(f);
    if(f.type.startsWith('video/')){
      const vid = document.createElement('video');
      vid.src = url; vid.crossOrigin = "anonymous"; vid.muted = true;
      vid.addEventListener('loadeddata', () => {
         const cvs = document.createElement('canvas'); cvs.width = 160; cvs.height = 90;
         cvs.getContext('2d').drawImage(vid, 0, 0, 160, 90);
         bgImages.push({id:uid(), type:'video', vid:vid, name:f.name, duration:vid.duration||5, thumbUrl:cvs.toDataURL(), volume:0.5});
         checkDone();
      }, {once:true});
      vid.load(); vid.currentTime = 0.1; // lấy thumbnail
    } else {
      const img=new Image();
      img.onload=()=>{bgImages.push({id:uid(), type:'image', img:img, name:f.name, duration:0, thumbUrl:url, volume:0});checkDone();};
      img.src=url;
    }
  });
  input.value='';
}

function moveItem(from, to) {
    if(to < 0 || to >= bgImages.length || from === to) return;
    const [moved] = bgImages.splice(from, 1);
    bgImages.splice(to, 0, moved);
    renderImgUI(); drawFrame(curTime);
}

function redistEqual(){if(!bgImages.length)return;const each=totalDur/bgImages.length;bgImages.forEach(i=>i.duration=each);}
function adjustDur(idx,newD){
  const MIN=0.5,n=bgImages.length;if(n<2)return;
  newD=Math.max(MIN,Math.min(newD,totalDur-(n-1)*MIN));
  const old=bgImages[idx].duration;bgImages[idx].duration=newD;
  const diff=old-newD,others=bgImages.filter((_,i)=>i!==idx),oT=others.reduce((s,x)=>s+x.duration,0);
  if(oT<=0){const each=(totalDur-newD)/(n-1);bgImages.forEach((x,i)=>{if(i!==idx)x.duration=each;});}
  else{const sc=(oT+diff)/oT;bgImages.forEach((x,i)=>{if(i!==idx)x.duration=Math.max(MIN,x.duration*sc);});}
  normDur();renderImgUI();drawFrame(curTime);
}
function normDur(){if(!bgImages.length)return;const sm=bgImages.reduce((s,x)=>s+x.duration,0);
  if(Math.abs(sm-totalDur)>0.001){const sc=totalDur/sm;bgImages.forEach(x=>x.duration*=sc);}}
function removeImg(i){bgImages.splice(i,1);if(bgImages.length)redistEqual();renderImgUI();drawFrame(curTime);}

function renderImgUI(){
  const list=$('imgList'),bar=$('timelineBar'),cnt=$('imgCount'); list.innerHTML='';
  bgImages.forEach((item,i)=>{
    const el=document.createElement('div');el.className='img-item'; el.draggable=false;
    const volHtml = item.type==='video' ? `<input type="range" title="Volume" min="0" max="1" step="0.05" value="${item.volume}" data-vidx="${i}">` : ``;
    
    // Add Preview Button (👁️)
    const previewUrl = item.type==='video' ? item.vid.src : item.img.src;
    
    el.innerHTML=`
      <span class="handle" title="Drag to sort">☰</span>
      <div class="sort-btns">
         <button class="up" title="Move Up">▲</button>
         <button class="dn" title="Move Down">▼</button>
      </div>
      <img src="${item.thumbUrl}" onclick="previewMedia('${item.type}','${previewUrl}')">
      <div class="info"><div class="name">${item.type==='video'?'🎬':''} ${item.name}</div>
      <div class="dur-row"><input type="number" value="${item.duration.toFixed(1)}" step="0.5" min="0.5" data-idx="${i}"><span>s</span>${volHtml}</div></div>
      <button class="btn-icon" onclick="previewMedia('${item.type}','${previewUrl}')" title="Xem thử">👁️</button>
      <button class="rm" data-idx="${i}" title="Remove">✕</button>`;
      
    el.querySelector('input[type="number"]').addEventListener('change',e=>adjustDur(parseInt(e.target.dataset.idx),parseFloat(e.target.value)||1));
    
    const vRange = el.querySelector('input[type="range"]');
    if(vRange) vRange.addEventListener('input',e=>{ item.volume=parseFloat(e.target.value); if(item.gainNode) item.gainNode.gain.value=item.volume; });
    
    el.querySelector('.rm').addEventListener('click',e=>removeImg(parseInt(e.target.dataset.idx)));
    
    // Sort buttons
    el.querySelector('.up').addEventListener('click',()=>moveItem(i, i-1));
    el.querySelector('.dn').addEventListener('click',()=>moveItem(i, i+1));

    // Drag setup
    const handle = el.querySelector('.handle');
    handle.onmousedown = () => el.draggable = true;
    handle.onmouseup = () => el.draggable = false;
    handle.onmouseleave = () => el.draggable = false;
    handle.ontouchstart = () => el.draggable = true;
    handle.ontouchend = () => el.draggable = false;

    el.addEventListener('dragstart',e=>{dragIdx=i;el.classList.add('dragging');e.dataTransfer.effectAllowed='move';});
    el.addEventListener('dragend',()=>{el.draggable=false;dragIdx=-1;list.querySelectorAll('.img-item').forEach(x=>{x.classList.remove('dragging','drag-over');});});
    el.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='move';el.classList.add('drag-over');});
    el.addEventListener('dragleave',()=>el.classList.remove('drag-over'));
    el.addEventListener('drop',e=>{e.preventDefault();el.classList.remove('drag-over');moveItem(dragIdx, i);});
    list.appendChild(el);
  });
  
  bar.innerHTML='';
  if(bgImages.length){bgImages.forEach((item,i)=>{const pct=item.duration/totalDur*100;
    const seg=document.createElement('div');seg.className='seg';seg.style.width=pct+'%';
    seg.style.background=SEG_COLORS[i%SEG_COLORS.length];seg.textContent=pct>8?item.duration.toFixed(1)+'s':'';
    seg.title=`${item.name} — ${item.duration.toFixed(1)}s`;bar.appendChild(seg);});bar.style.display='flex';}
  else bar.style.display='none';
  cnt.textContent=bgImages.length?`${bgImages.length} media item(s) — total ${totalDur.toFixed(1)}s`:'';
}

// ══ TIMELINE SEEK ══
$('timelineBar').addEventListener('click', e => {
    if(!audioBuf) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    curTime = pct * totalDur;
    if(isPlay) { 
        stopPrev(); playPrev(curTime); 
    } else { 
        // Sync but DO NOT play audio if just seeking
        syncVideos(curTime, false); 
        drawFrame(curTime); 
    }
});

// ══ GENERATE TTS ════════════════════════════════════════════════════════════
async function genTTS(){
  const btn=$('btnGen'),st=$('stTTS'),dl=$('dlLinks'),sp=$('srtPre');
  const text=$('inputText').value.trim();
  if(!text){st.textContent='Vui lòng nhập văn bản!';st.className='status error';return;}
  btn.disabled=true;st.textContent='Đang tạo MP3 + Subtitles…';st.className='status';dl.innerHTML='';sp.style.display='none';
  try{
    const r=await fetch('/api/tts',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text,voice:$('voiceSelect').value,rate:$('rateSelect').value})});
    if(!r.ok)throw new Error(`HTTP ${r.status}: ${await r.text()}`);
    const d=await r.json();subs=d.subtitles;
    sp.textContent=await(await fetch(d.srt_url)).text();sp.style.display='block';
    if(!audioCtx) audioCtx=new(window.AudioContext||window.webkitAudioContext)();
    audioBuf=await audioCtx.decodeAudioData(await(await fetch(d.mp3_url)).arrayBuffer());
    totalDur=audioBuf.duration;if(bgImages.length)redistEqual();renderImgUI();
    st.textContent=`Done! ${subs.length} cues, ${totalDur.toFixed(1)}s.`;
    dl.innerHTML=`<a class="btn btn-d" href="${d.mp3_url}" download="audio.mp3">MP3</a>
      <a class="btn btn-d" href="${d.srt_url}" download="subtitles.srt">SRT</a>
      <a class="btn btn-d" href="${d.vtt_url}" download="subtitles.vtt">VTT</a>
      <a class="btn btn-d" href="${d.json_url}" download="subtitles.json">JSON</a>`;
    $('btnPlay').disabled=false;$('btnExp').disabled=false; curTime=0; drawFrame(0);
  }catch(e){st.textContent='Error: '+e.message;st.className='status error';console.error(e);}
  finally{btn.disabled=false;}
}

// ══ CANVAS RENDERER ═════════════════════════════════════════════════════════
function S(){return{
  w:parseInt($('vidW').value)||1280, h:parseInt($('vidH').value)||720,
  fps:parseInt($('vidFPS').value)||30, fs:parseInt($('fontSize').value)||48,
  bg:$('bgColor').value, fg:$('textColor').value, hl:$('hlColor').value,
  fgA:parseInt($('textOpacity').value)/100,
  hlA:parseInt($('hlOpacity').value)/100,
  kb:$('kenBurns').checked, blur:$('blurBg').checked,
  wmPos:$('wmPos').value, wmA:parseInt($('wmOpacity').value)/100,
  wmScale:parseInt($('wmScale').value)/100
};}
function activeSub(t){for(const s of subs)if(t>=s.start&&t<=s.end)return s;return null;}
function activeBgInfo(t){
  if(!bgImages.length)return null; let cum=0;
  for(const item of bgImages){ if(t>=cum && t<cum+item.duration) return {item, localTime: t-cum}; cum+=item.duration; }
  return {item: bgImages[bgImages.length-1], localTime: t-cum};
}

function drawFrame(time,canvas,settings){
  if(time === -1) time = curTime; // UI trigger
  curTime = time;
  const c=canvas||$('cvs'),s=settings||S(),ctx=c.getContext('2d');
  if(c.width!==s.w||c.height!==s.h){c.width=s.w;c.height=s.h;}
  
  // 1. Draw Background (Images/Videos + Ken Burns + Blur Mode)
  const bgInfo=activeBgInfo(time);
  if(bgInfo){
    const item = bgInfo.item;
    const source = item.type==='video' ? item.vid : item.img;
    const w = item.type==='video' ? item.vid.videoWidth||s.w : item.img.width;
    const h = item.type==='video' ? item.vid.videoHeight||s.h : item.img.height;
    
    const ir=w/h, cr=s.w/s.h;
    
    let scale = 1.0;
    if(s.kb && item.type === 'image') scale = 1.0 + (bgInfo.localTime / item.duration) * 0.1; // 10% zoom max
    
    if(s.blur) {
        // Draw Blurred Background
        ctx.save(); ctx.filter = 'blur(30px) brightness(0.4)';
        let cw, ch, cx, cy;
        if(ir>cr){ch=h; cw=ch*cr; cx=(w-cw)/2; cy=0;} else {cw=w; ch=cw/cr; cx=0; cy=(h-ch)/2;}
        ctx.drawImage(source, cx, cy, cw, ch, -20, -20, s.w+40, s.h+40);
        ctx.restore();
        // Draw Fitted Image
        let fw, fh, fx, fy;
        if(ir > cr) { fw = s.w * scale; fh = (s.w / ir) * scale; fx = (s.w - fw)/2; fy = (s.h - fh)/2; }
        else { fh = s.h * scale; fw = (s.h * ir) * scale; fx = (s.w - fw)/2; fy = (s.h - fh)/2; }
        ctx.drawImage(source, 0, 0, w, h, fx, fy, fw, fh);
    } else {
        // Draw Crop Filled Image
        let cw, ch, cx, cy;
        if(ir > cr) { ch = h / scale; cw = ch * cr; cx = (w - cw)/2; cy = (h - ch)/2; }
        else { cw = w / scale; ch = cw / cr; cx = (w - cw)/2; cy = (h - ch)/2; }
        ctx.drawImage(source, cx, cy, cw, ch, 0, 0, s.w, s.h);
        ctx.fillStyle='rgba(0,0,0,0.3)';ctx.fillRect(0,0,s.w,s.h);
    }
  }else{ctx.fillStyle=s.bg;ctx.fillRect(0,0,s.w,s.h);}
  
  // 2. Draw Watermark (With Scale support)
  if(wm.img) {
      ctx.save(); ctx.globalAlpha = s.wmA;
      // Use s.wmScale to determine width percentage
      const ww = s.w * s.wmScale, wh = ww * (wm.img.height / wm.img.width), pad = 30;
      let wx, wy;
      if(s.wmPos.includes('l')) wx = pad; else wx = s.w - ww - pad;
      if(s.wmPos.includes('t')) wy = pad; else wy = s.h - wh - pad;
      ctx.drawImage(wm.img, wx, wy, ww, wh);
      ctx.restore();
  }

  // 3. Draw Subtitles
  const sub=activeSub(time);
  if(sub){
    ctx.save();ctx.font=`bold ${s.fs}px 'Segoe UI',system-ui,sans-serif`;
    ctx.textAlign='center';ctx.textBaseline='middle';
    const x=s.w/2,y=s.h*.82,mw=s.w*.88;
    const lines=wrap(ctx,sub.text,mw),lh=s.fs*1.35,th=lines.length*lh,sy2=y-th/2+lh/2;
    let bw=0;lines.forEach(l=>{bw=Math.max(bw,ctx.measureText(l).width);});
    const p=20,bx=x-bw/2-p,by=sy2-lh/2-p/2,bfw=bw+p*2,bfh=th+p;
    ctx.fillStyle='rgba(0,0,0,0.6)';rrF(ctx,bx,by,bfw,bfh,12);
    const pr=Math.min(1,Math.max(0,(time-sub.start)/(sub.end-sub.start)));
    ctx.save();ctx.beginPath();rrP(ctx,bx,by,bfw,bfh,12);ctx.clip();
    ctx.fillStyle=hexRgba(s.hl,s.hlA);ctx.fillRect(bx,by,bfw*pr,bfh);ctx.restore();
    ctx.shadowColor='rgba(0,0,0,0.9)';ctx.shadowBlur=8;
    ctx.fillStyle=hexRgba(s.fg,s.fgA);
    lines.forEach((l,i)=>ctx.fillText(l,x,sy2+i*lh));ctx.restore();
  }
  
  // 4. Progress bar at bottom
  if(audioBuf&&time>0){const pct=time/audioBuf.duration;ctx.save();
    ctx.fillStyle='rgba(255,255,255,0.12)';ctx.fillRect(0,s.h-3,s.w,3);
    ctx.fillStyle=hexRgba(s.hl,0.8);ctx.fillRect(0,s.h-3,s.w*pct,3);ctx.restore();}
}
function wrap(ctx,t,mw){const w=t.split(/\s+/),ls=[];let c='';w.forEach(x=>{const tt=c?c+' '+x:x;if(ctx.measureText(tt).width>mw&&c){ls.push(c);c=x;}else c=tt;});if(c)ls.push(c);return ls.length?ls:[''];}
function rrP(c,x,y,w,h,r){c.moveTo(x+r,y);c.lineTo(x+w-r,y);c.quadraticCurveTo(x+w,y,x+w,y+r);c.lineTo(x+w,y+h-r);c.quadraticCurveTo(x+w,y+h,x+w-r,y+h);c.lineTo(x+r,y+h);c.quadraticCurveTo(x,y+h,x,y+h-r);c.lineTo(x,y+r);c.quadraticCurveTo(x,y,x+r,y);c.closePath();}
function rrF(c,x,y,w,h,r){c.beginPath();rrP(c,x,y,w,h,r);c.fill();}

// ══ PREVIEW PLAYBACK ════════════════════════════════════════════════════════
function syncVideos(time, playTarget = false){
  const active=activeBgInfo(time);
  bgImages.forEach(i=>{
    if(i.type==='video'){
      if(active && active.item===i){ 
          // Cập nhật currentTime nếu bị lệch quá 0.1s
          if(Math.abs(i.vid.currentTime - active.localTime) > 0.1){
              i.vid.currentTime = active.localTime;
          }
          if(playTarget && i.vid.paused) i.vid.play().catch(()=>{});
          if(!playTarget && !i.vid.paused) i.vid.pause();
      }
      else { 
          if(!i.vid.paused) i.vid.pause(); 
      }
    }
  });
}
function stopAllVideos(){ bgImages.forEach(i=>{if(i.type==='video')i.vid.pause();}); }

function playPrev(startTime = curTime){
  if(!audioBuf)return; stopPrev(); initAudioCtx();
  if(audioCtx.state==='suspended')audioCtx.resume();
  srcNode=audioCtx.createBufferSource();srcNode.buffer=audioBuf;srcNode.connect(audioCtx.destination);
  
  srcNode.start(0, startTime);
  t0=audioCtx.currentTime - startTime; isPlay=true;$('btnPlay').disabled=true;$('btnStop').disabled=false;
  
  if(bgm.el) { bgm.el.currentTime = startTime % bgm.el.duration; bgm.el.play().catch(()=>{}); }

  srcNode.onended=()=>{
    isPlay=false;$('btnPlay').disabled=false;$('btnStop').disabled=true;
    if(aFrame)cancelAnimationFrame(aFrame);stopAllVideos(); if(bgm.el) bgm.el.pause(); curTime=0; drawFrame(0);
  };
  (function lp(){
      if(!isPlay)return; 
      curTime = audioCtx.currentTime-t0; 
      syncVideos(curTime, true); // true = allow video playing
      drawFrame(curTime); 
      aFrame=requestAnimationFrame(lp);
  })();
}
function stopPrev(){
  isPlay=false;if(aFrame)cancelAnimationFrame(aFrame); stopAllVideos(); if(bgm.el) bgm.el.pause();
  if(srcNode){try{srcNode.stop();}catch(e){}srcNode=null;}$('btnPlay').disabled=!audioBuf;$('btnStop').disabled=true;
}

// ══ EXPORT ══════════════════════════════════════════════════════════════════
async function exportVid(){
  if(!audioBuf)return;$('btnExp').disabled=true;stopPrev();initAudioCtx();
  const s=S(),dur=audioBuf.duration,tot=Math.ceil(dur*s.fps);
  const br=parseInt($('expBr').value),mime=pickMime($('expFmt').value==='mp4'),ext=mime.startsWith('video/mp4')?'mp4':'webm';
  $('stExp').textContent=`Rendering ${tot} frames…`;$('expFill').style.width='0%';
  const off=document.createElement('canvas');off.width=s.w;off.height=s.h;
  
  const st=off.captureStream(s.fps), ad=audioCtx.createMediaStreamDestination();
  const as2=audioCtx.createBufferSource(); as2.buffer=audioBuf;
  as2.connect(ad); as2.connect(audioCtx.destination);
  
  bgImages.forEach(i=>{
     if(i.type==='video' && i.gainNode){
         i.gainNode.disconnect(); i.gainNode.connect(ad); i.gainNode.connect(audioCtx.destination);
     }
  });
  if(bgm.gain){ 
      bgm.gain.disconnect(); bgm.gain.connect(ad); bgm.gain.connect(audioCtx.destination); 
      if(bgm.el){ bgm.el.currentTime=0; bgm.el.play(); } 
  }

  ad.stream.getAudioTracks().forEach(t=>st.addTrack(t));
  const rec=new MediaRecorder(st,{mimeType:mime,videoBitsPerSecond:br}),ch=[];
  rec.ondataavailable=e=>{if(e.data.size)ch.push(e.data);};
  const done=new Promise(r=>{rec.onstop=r;});rec.start();as2.start(0);
  const rt=audioCtx.currentTime,vt=st.getVideoTracks()[0];let last=-1;
  
  (function lp(){const el=audioCtx.currentTime-rt,fn=Math.floor(el*s.fps);
    if(el>=dur+.3 || fn>=tot){
        rec.stop();try{as2.stop();}catch(e){} stopAllVideos(); if(bgm.el) bgm.el.pause();
        bgImages.forEach(i=>{ if(i.type==='video'&&i.gainNode){ i.gainNode.disconnect(); i.gainNode.connect(audioCtx.destination); } });
        if(bgm.gain){ bgm.gain.disconnect(); bgm.gain.connect(audioCtx.destination); }
        return;
    }
    if(fn!==last&&fn<tot){const t=fn/s.fps; syncVideos(t, true); drawFrame(t,off,s); drawFrame(t);
      if(vt&&vt.requestFrame)vt.requestFrame();last=fn;
      const p=Math.round(fn/tot*100);$('expFill').style.width=p+'%';$('stExp').textContent=`${fn+1}/${tot} (${p}%)`;}
    requestAnimationFrame(lp);})();
    
  await done;$('expFill').style.width='100%';
  const blob=new Blob(ch,{type:mime}),a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download=`tts_video.${ext}`;document.body.appendChild(a);a.click();document.body.removeChild(a);
  $('stExp').textContent=`Exported ${ext.toUpperCase()}! ${(blob.size/1048576).toFixed(1)} MB`;$('btnExp').disabled=false;
}

drawFrame(0);
</script>
</body></html>"""

@app.get("/")
async def index():
    return HTMLResponse(FRONTEND_HTML.replace("{{VERSION}}", VERSION))

if __name__=="__main__":
    import uvicorn
    print(f"[*] {VERSION}  Proxy: {PROXY or 'None'}  Port: {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)