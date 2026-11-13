"""Tareekh Ki Kahani - VOICE RECORDER in the browser.
RECORD.bat starts this and opens http://localhost:8765 . Read each scene (shown in Urdu script when the episode has narration_ur), click Record, click Stop.
Takes are saved by themselves as recordings\\tkNNN\\01.wav ... (Shorts: recordings\\tkNNN\\short1\\01.wav ...).
Scenes without a take use the AI voice in RENDER.bat."""
import json, re, shutil, sys, time, webbrowser, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
EPIS, RECS, READY = ROOT / "episodes", ROOT / "recordings", ROOT / "Ready to Upload"
PORT = 8765


def parts(data):
    out = [{"id": "main", "name": "Long video", "scenes": data["scenes"]}]
    for k, sh in enumerate(data.get("shorts", []), 1):
        out.append({"id": f"short{k}", "name": f"Short {k}", "scenes": sh["scenes"]})
    return out


def rec_dir(ep, part):
    return RECS / ep if part == "main" else RECS / ep / part


def checked(q):
    ep, part, n = q.get("ep", [""])[0], q.get("part", ["main"])[0], q.get("n", ["0"])[0]
    if not re.fullmatch(r"tk\d{3}", ep) or not re.fullmatch(r"main|short[1-9]", part) or not re.fullmatch(r"\d{1,2}", n):
        raise ValueError("bad request")
    return ep, part, int(n)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)): body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path == "/":
                return self.send(200, PAGE, "text/html; charset=utf-8")
            if u.path == "/api/episodes":
                eps = sorted(e.stem for e in EPIS.glob("tk[0-9][0-9][0-9].json"))
                dflt = next((e for e in eps if not ((READY / e).exists() and list((READY / e).glob("*.mp4")))), eps[-1] if eps else "")
                return self.send(200, {"episodes": eps, "default": dflt})
            if u.path == "/api/episode":
                ep = q.get("ep", [""])[0]
                if not re.fullmatch(r"tk\d{3}", ep): raise ValueError("bad episode")
                data = json.loads((EPIS / f"{ep}.json").read_text(encoding="utf-8"))
                res = []
                for p in parts(data):
                    d = rec_dir(ep, p["id"])
                    res.append({"id": p["id"], "name": p["name"], "scenes": [
                        {"n": i, "roman": s.get("narration_roman", ""), "hi": s.get("narration_hi", ""), "ur": s.get("narration_ur", ""),
                         "title": s.get("text_on_screen", ""), "dl": s.get("delivery"), "feel": s.get("feel", ""), "done": (d / f"{i:02d}.wav").exists()}
                        for i, s in enumerate(p["scenes"], 1)]})
                rendered = bool(list((READY / ep).glob("*.mp4"))) if (READY / ep).exists() else False
                return self.send(200, {"ep": ep, "title": data.get("title", ep), "parts": res, "rendered": rendered})
            if u.path == "/api/take":
                ep, part, n = checked(q); f = rec_dir(ep, part) / f"{n:02d}.wav"
                if not f.exists(): return self.send(404, {"error": "no take"})
                return self.send(200, f.read_bytes(), "audio/wav")
            self.send(404, {"error": "not found"})
        except Exception as e:
            self.send(400, {"error": str(e)})

    def do_POST(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path == "/api/save":
                ep, part, n = checked(q)
                size = int(self.headers.get("Content-Length", "0"))
                if not 1000 < size < 200_000_000: raise ValueError("empty or too large recording")
                body = self.rfile.read(size)
                if body[:4] != b"RIFF": raise ValueError("not a WAV file")
                d = rec_dir(ep, part); d.mkdir(parents=True, exist_ok=True)
                tmp = d / f"{n:02d}.part"; tmp.write_bytes(body); tmp.replace(d / f"{n:02d}.wav")
                return self.send(200, {"ok": True})
            if u.path == "/api/discard":      # remove one take -> that scene uses the AI voice again
                ep, part, n = checked(q); f = rec_dir(ep, part) / f"{n:02d}.wav"
                if f.exists(): f.unlink()
                return self.send(200, {"ok": True})
            if u.path == "/api/rerender":     # move the old finished video aside so RENDER.bat makes it again
                ep = q.get("ep", [""])[0]
                if not re.fullmatch(r"tk\d{3}", ep): raise ValueError("bad episode")
                src = READY / ep
                if not src.exists(): return self.send(200, {"ok": True, "moved": False})
                dst = READY / "_old versions" / f"{ep}_{time.strftime('%Y%m%d_%H%M%S')}"
                dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), str(dst))
                return self.send(200, {"ok": True, "moved": True, "to": str(dst)})
            self.send(404, {"error": "not found"})
        except Exception as e:
            self.send(400, {"error": str(e)})


PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tareekh Ki Kahani – Voice Recorder</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu:wght@400;600&display=swap">
<style>
:root{--bg:#14110d;--panel:#211b14;--line:#3b3124;--gold:#e8c15a;--text:#f3e6c8;--dim:#a8997a;--red:#d9482f;--green:#6fbf73}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:17px/1.5 "Segoe UI",system-ui,sans-serif}
header{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 20px;border-bottom:1px solid var(--line);background:var(--panel)}
header h1{font-size:19px;margin:0 auto 0 0;color:var(--gold)}
select,button{font:inherit;color:var(--text);background:#2c241a;border:1px solid var(--line);border-radius:8px;padding:8px 14px;cursor:pointer}
button:hover{border-color:var(--gold)}button:disabled{opacity:.4;cursor:default}
main{display:grid;grid-template-columns:230px 1fr;min-height:calc(100vh - 62px)}
nav{border-right:1px solid var(--line);padding:10px;overflow:auto;max-height:calc(100vh - 62px)}
nav button{display:flex;gap:8px;width:100%;text-align:left;margin-bottom:5px;padding:7px 10px;font-size:14px}
nav button.cur{border-color:var(--gold);background:#3a2f1f}nav .ok{color:var(--green)}nav .no{color:var(--dim)}
nav .t{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
section{padding:22px 30px;max-width:980px}
.meta{color:var(--dim);font-size:14px;margin-bottom:6px}
#roman{font-size:27px;line-height:1.65;margin:8px 0 14px}
#roman.ur{direction:rtl;text-align:right;font-family:"Jameel Noori Nastaleeq","Noto Nastaliq Urdu","Urdu Typesetting","Alvi Nastaleeq",serif;font-size:32px;line-height:2.25}
#roman .feel{font-family:system-ui,Segoe UI,Arial;font-size:16px;line-height:1.6;direction:rtl;background:#2a2417;border:1px solid var(--gold);color:var(--gold);border-radius:8px;padding:8px 12px;margin-bottom:12px}
#roman .ln{margin:0 0 6px}#roman .tags{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-start;margin:6px 0 -4px}
#roman .tg{font-family:system-ui,Segoe UI,Arial;font-size:14px;line-height:1.4;border-radius:12px;padding:1px 10px;background:#243044;color:#cfe0ff;direction:rtl}
#roman .tg.stress,#roman .tg.fast{background:#4a2a24;color:#ffd3c9}#roman .tg.pause,#roman .tg.pause2{background:#2d2d2d;color:#ddd}#roman .tg.warm{background:#27402b;color:#cdeed0}
#roman mark{background:#e0b84a;color:#111;border-radius:4px;padding:0 4px}
#hi{color:var(--dim);font-size:17px;line-height:1.7;border-top:1px solid var(--line);padding-top:12px}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0;padding:14px;background:var(--panel);border:1px solid var(--line);border-radius:12px;position:sticky;top:0}
#rec{background:var(--red);border-color:var(--red);font-weight:700;font-size:20px;padding:12px 26px;min-width:190px}
#rec.on{background:#7a1f12;animation:p 1s infinite}@keyframes p{50%{box-shadow:0 0 0 8px rgba(217,72,47,.25)}}
#time{font-variant-numeric:tabular-nums;font-size:22px;min-width:74px}
#meter{flex:1;min-width:120px;height:12px;background:#000;border-radius:6px;overflow:hidden}#lvl{height:100%;width:0;background:var(--green)}
#msg{min-height:24px;color:var(--gold)}.hint{color:var(--dim);font-size:14px}
#done{border-color:var(--gold);color:var(--gold)}
@media(max-width:760px){main{grid-template-columns:1fr}nav{max-height:170px;border-right:0;border-bottom:1px solid var(--line)}#roman{font-size:22px}}
</style></head><body>
<header><h1>Tareekh Ki Kahani – Voice Recorder</h1>
<select id="ep" title="Episode"></select><select id="part" title="Long video or Short"></select>
<span id="count" class="hint"></span><button id="done">Finished – make the video again</button></header>
<main><nav id="list"></nav>
<section>
<div class="meta" id="meta"></div>
<div id="roman">Loading…</div>
<div class="bar">
<button id="rec">● Record</button><span id="time">0:00</span><div id="meter"><div id="lvl"></div></div>
<button id="play" disabled>▶ Play my take</button><button id="del" disabled>Remove take</button>
<button id="prev">← Back</button><button id="next">Next →</button>
</div>
<div id="msg"></div>
<div id="hi"></div>
<p class="hint">Keys: <b>Space</b> = record / stop, <b>→</b> = next scene, <b>←</b> = back, <b>P</b> = play. Each take is saved by itself the moment you stop. Not happy? Just press Record again – the new take replaces the old one.</p>
</section></main>
<audio id="au"></audio>
<script>
const $=id=>document.getElementById(id);let EP=null,part=0,idx=0,stream=null,mr=null,chunks=[],t0=0,timer=null,ac=null,an=null,busy=false;
const api=(p,o)=>fetch(p,o).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j});
const say=(t,bad)=>{$('msg').textContent=t;$('msg').style.color=bad?'#ff8a70':''};
async function boot(){const e=await api('/api/episodes');$('ep').innerHTML=e.episodes.map(x=>`<option>${x}</option>`).join('');$('ep').value=e.default||e.episodes[0];await load()}
async function load(keep){const d=await api('/api/episode?ep='+$('ep').value);EP=d;
 $('part').innerHTML=d.parts.map((p,i)=>`<option value="${i}">${p.name} (${p.scenes.length} scenes)</option>`).join('');
 if(!keep){part=0;const f=d.parts[0].scenes.findIndex(s=>!s.done);idx=f<0?0:f}$('part').value=part;draw()}
function sc(){return EP.parts[part].scenes}
function draw(){const S=sc(),s=S[idx];
 $('list').innerHTML=S.map((x,i)=>`<button class="${i==idx?'cur':''}" data-i="${i}"><span class="${x.done?'ok':'no'}">${x.done?'✓':'○'}</span><span class="t">${x.n}. ${esc(x.title||x.roman.slice(0,28))}</span></button>`).join('');
 $('meta').textContent=`${EP.ep} · ${EP.parts[part].name} · Scene ${s.n} of ${S.length}`+(s.done?' · recorded ✓':' · not recorded yet');
 $('roman').classList.toggle('ur',!!s.ur);
 if(s.dl&&s.ur){const L={slow:['🐢','آہستہ'],soft:['🤫','دھیمی'],low:['🔉','گہری آواز'],stress:['🔊','زور'],fast:['⚡','تیز'],pause:['⏸','وقفہ'],pause2:['⏸⏸','لمبا وقفہ'],warm:['🙂','نرمی'],rise:['❓','آواز اوپر']};
  const ss=s.ur.match(/[^\u06d4\u061f!?]+[\u06d4\u061f!?]?/g).map(x=>x.trim()).filter(x=>x.replace(/\u06d4/g,'').trim());
  $('roman').innerHTML=(s.feel?`<div class="feel">🎭 ${esc(s.feel)}</div>`:'')+ss.map((t,k)=>{const d=s.dl[k]||{m:[],w:''};let h=esc(t);
   if(d.w){h=h.replace(esc(d.w),`<mark>${esc(d.w)}</mark>`)}
   const tags=d.m.map(m=>`<span class="tg ${m}">${(L[m]||['',m])[0]} ${(L[m]||['',m])[1]}</span>`).join('');
   return `<div class="ln">${tags?`<div class="tags">${tags}</div>`:''}<div>${h}</div></div>`}).join('')}
 else $('roman').textContent=s.ur||s.roman;$('hi').textContent=s.ur?s.roman:s.hi;$('play').disabled=$('del').disabled=!s.done;
 const all=EP.parts.flatMap(p=>p.scenes),n=all.filter(x=>x.done).length;$('count').textContent=`${n} / ${all.length} recorded`;
 const c=$('list').querySelector('.cur');if(c)c.scrollIntoView({block:'nearest'})}
const esc=t=>t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function go(i){if(mr||busy)return;const S=sc();if(i<0||i>=S.length)return;idx=i;say('');draw()}
async function mic(){if(stream)return;stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:false,noiseSuppression:true,autoGainControl:true}});
 ac=new AudioContext({sampleRate:48000});an=ac.createAnalyser();an.fftSize=1024;ac.createMediaStreamSource(stream).connect(an);
 const b=new Float32Array(an.fftSize);(function loop(){an.getFloatTimeDomainData(b);let m=0;for(const v of b)m=Math.max(m,Math.abs(v));$('lvl').style.width=Math.min(100,m*140)+'%';$('lvl').style.background=m>.9?'#d9482f':'#6fbf73';requestAnimationFrame(loop)})()}
async function start(){if(busy)return;try{await mic()}catch(e){say('Microphone not allowed. Click the lock/mic icon in the address bar, allow the microphone, and try again.',1);return}
 if(ac.state=='suspended')await ac.resume();chunks=[];mr=new MediaRecorder(stream);mr.ondataavailable=e=>e.data.size&&chunks.push(e.data);mr.onstop=finish;mr.start();
 t0=Date.now();$('rec').textContent='■ Stop';$('rec').classList.add('on');say('Recording… read the lines, then press Stop (or Space).');
 timer=setInterval(()=>{const s=Math.floor((Date.now()-t0)/1000);$('time').textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0')},200)}
function stop(){if(mr&&mr.state!='inactive')mr.stop()}
async function finish(){clearInterval(timer);$('rec').textContent='● Record';$('rec').classList.remove('on');mr=null;busy=true;say('Saving…');
 try{const buf=await new Blob(chunks).arrayBuffer();const a=await ac.decodeAudioData(buf);const wav=toWav(a);const s=sc()[idx];
  if(a.duration<0.7)throw new Error('That take was too short – record again.');
  await api(`/api/save?ep=${EP.ep}&part=${EP.parts[part].id}&n=${s.n}`,{method:'POST',headers:{'Content-Type':'audio/wav'},body:wav});
  s.done=true;say(`Saved scene ${s.n} (${a.duration.toFixed(1)} s). Press → for the next scene, or Record to redo.`);draw()}
 catch(e){say('Not saved: '+e.message,1)}busy=false}
function toWav(a){const n=a.length,ch=a.numberOfChannels,d=new Float32Array(n);for(let c=0;c<ch;c++){const x=a.getChannelData(c);for(let i=0;i<n;i++)d[i]+=x[i]/ch}
 const v=new DataView(new ArrayBuffer(44+n*2)),w=(o,s)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i))};
 w(0,'RIFF');v.setUint32(4,36+n*2,true);w(8,'WAVEfmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,a.sampleRate,true);v.setUint32(28,a.sampleRate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);w(36,'data');v.setUint32(40,n*2,true);
 for(let i=0;i<n;i++){const s=Math.max(-1,Math.min(1,d[i]));v.setInt16(44+i*2,s<0?s*32768:s*32767,true)}return v.buffer}
function play(){const s=sc()[idx];if(!s.done)return;$('au').src=`/api/take?ep=${EP.ep}&part=${EP.parts[part].id}&n=${s.n}&t=${Date.now()}`;$('au').play().catch(()=>{})}
async function del(){const s=sc()[idx];if(!s.done||mr||busy)return;await api(`/api/discard?ep=${EP.ep}&part=${EP.parts[part].id}&n=${s.n}`,{method:'POST'});s.done=false;say(`Take for scene ${s.n} removed – the AI voice will read it unless you record again.`);draw()}
async function done(){if(mr||busy)return;const all=EP.parts[0].scenes,miss=all.filter(x=>!x.done).map(x=>x.n);
 try{const r=await api('/api/rerender?ep='+EP.ep,{method:'POST'});
  say((miss.length?`Note: scenes ${miss.join(', ')} of the long video have no take, so the AI voice will read them. `:'')+(r.moved?'The old video was moved to "Ready to Upload\\_old versions". ':'')+'Now close this page and double-click RENDER.bat.')}
 catch(e){say('Could not prepare the re-render: '+e.message+' (close the old video if it is open, then click again).',1)}}
$('rec').onclick=()=>mr?stop():start();$('play').onclick=play;$('del').onclick=del;$('next').onclick=()=>go(idx+1);$('prev').onclick=()=>go(idx-1);$('done').onclick=done;
$('list').onclick=e=>{const b=e.target.closest('button');if(b)go(+b.dataset.i)};
$('ep').onchange=()=>{if(!mr)load()};$('part').onchange=()=>{if(mr)return;part=+$('part').value;const f=sc().findIndex(s=>!s.done);idx=f<0?0:f;say('');draw()};
document.addEventListener('keydown',e=>{if(e.target.tagName=='SELECT')return;if(e.code=='Space'){e.preventDefault();mr?stop():start()}else if(e.code=='ArrowRight')go(idx+1);else if(e.code=='ArrowLeft')go(idx-1);else if(e.key=='p'||e.key=='P')play()});
boot().catch(e=>{$('roman').textContent='Could not load: '+e.message});
</script></body></html>"""


def main():
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        print(f"The recorder is already running. Opening http://localhost:{PORT} ...")
        webbrowser.open(f"http://localhost:{PORT}"); return
    url = f"http://localhost:{PORT}"
    print("\n  VOICE RECORDER is running.\n")
    print(f"  Your browser opens by itself. If it does not, open:  {url}")
    print("  Keep this black window open while you record. Close it when you are finished.\n")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
