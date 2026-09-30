"""Standalone interactive HTML: the chart's SVG plus a few lines of JavaScript.

Hover shows the marks' tooltips in a styled box; the wheel zooms around the
pointer, dragging pans, and double-click resets. No external files or CDNs, so
the page works offline and can be emailed as a single file.
"""

from __future__ import annotations

from html import escape

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html,body{{margin:0;background:#f4f5f4;font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}}
  main{{max-width:{width}px;margin:24px auto;padding:0 16px}}
  .lv-frame{{background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden;touch-action:none;cursor:grab}}
  .lv-frame.dragging{{cursor:grabbing}}
  .lv-frame svg{{display:block;width:100%;height:auto}}
  .lv-hint{{color:#777;font-size:12px;margin-top:8px}}
  #lv-tip{{position:fixed;pointer-events:none;background:#15191b;color:#f3f5f4;padding:6px 9px;border-radius:5px;
          max-width:280px;font-size:12px;opacity:0;transition:opacity .08s;box-shadow:0 4px 14px rgba(0,0,0,.25);z-index:9}}
  #lv-tip.on{{opacity:1}}
  [data-tip]:hover{{filter:brightness(1.12)}}
  @media (prefers-reduced-motion:reduce){{#lv-tip{{transition:none}}}}
  #lv-tip .lv-x{{font-weight:600;margin-bottom:3px}}
  #lv-tip .lv-row{{display:flex;gap:6px;align-items:center;white-space:nowrap}}
  #lv-tip .lv-sw{{width:9px;height:9px;border-radius:2px;flex:none}}
  #lv-tip .lv-v{{margin-left:auto;padding-left:12px;font-variant-numeric:tabular-nums;font-weight:600}}
  details.lv-data{{margin-top:14px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:10px 14px}}
  details.lv-data summary{{cursor:pointer;font-weight:600;color:#333}}
  .lv-desc{{color:#444;margin:10px 0}}
  .lv-table{{max-height:360px;overflow:auto}}
  .lv-table table{{border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}}
  .lv-table th,.lv-table td{{border-bottom:1px solid #e6e6e6;padding:3px 10px;text-align:right}}
  .lv-table th:first-child,.lv-table td:first-child{{text-align:left}}
  .lv-table caption{{caption-side:bottom;color:#777;text-align:left;padding-top:6px}}
  .lv-csv{{display:inline-block;margin-top:8px;color:#2f5bd3}}
  .lv-th{{margin:16px 0 6px;font-size:13px}}
</style></head>
<body><main>
<div class="lv-frame" id="lv-frame">{svg}</div>
<div class="lv-hint">Hover for values · scroll to zoom · drag to pan · double-click to reset</div>
{data}
</main>
<script type="application/json" id="lv-meta">{meta}</script>
<div id="lv-tip" role="tooltip"></div>
<script>
(function(){{
  var frame=document.getElementById('lv-frame'), svg=frame.querySelector('svg'), tip=document.getElementById('lv-tip');
  // move <title> children into data attributes so the browser's slow native tooltip doesn't fire
  svg.querySelectorAll('title').forEach(function(t){{
    var p=t.parentNode; if(p&&p!==svg){{p.setAttribute('data-tip',t.textContent); p.removeChild(t);}}
  }});
  function place(e){{var r=tip.getBoundingClientRect(),x=e.clientX+14,y=e.clientY+14;
    if(x+r.width>innerWidth-8)x=e.clientX-r.width-14; if(y+r.height>innerHeight-8)y=e.clientY-r.height-14;
    tip.style.left=x+'px'; tip.style.top=y+'px';}}
  svg.addEventListener('pointerover',function(e){{var el=e.target.closest('[data-tip]');
    if(el){{tip.textContent=el.getAttribute('data-tip'); tip.classList.add('on'); place(e);}}}});
  svg.addEventListener('pointermove',function(e){{if(tip.classList.contains('on'))place(e);}});
  svg.addEventListener('pointerout',function(e){{if(e.target.closest('[data-tip]'))tip.classList.remove('on');}});
  // zoom & pan by editing the viewBox
  var vb0=svg.viewBox.baseVal, base=[vb0.x,vb0.y,vb0.width,vb0.height], vb=base.slice();
  function apply(){{svg.setAttribute('viewBox',vb.join(' '));}}
  function toSvg(e){{var r=svg.getBoundingClientRect();
    return [vb[0]+(e.clientX-r.left)/r.width*vb[2], vb[1]+(e.clientY-r.top)/r.height*vb[3]];}}
  frame.addEventListener('wheel',function(e){{e.preventDefault();
    var p=toSvg(e), k=Math.exp(e.deltaY*0.0015), w=Math.min(base[2],Math.max(base[2]/40,vb[2]*k)), s=w/vb[2];
    vb=[p[0]-(p[0]-vb[0])*s, p[1]-(p[1]-vb[1])*s, w, vb[3]*s]; apply();}},{{passive:false}});
  var drag=null;
  frame.addEventListener('pointerdown',function(e){{drag={{x:e.clientX,y:e.clientY,vb:vb.slice()}};
    frame.classList.add('dragging'); frame.setPointerCapture(e.pointerId);}});
  frame.addEventListener('pointermove',function(e){{if(!drag)return; var r=svg.getBoundingClientRect();
    vb[0]=drag.vb[0]-(e.clientX-drag.x)/r.width*vb[2]; vb[1]=drag.vb[1]-(e.clientY-drag.y)/r.height*vb[3]; apply();}});
  function end(){{drag=null; frame.classList.remove('dragging');}}
  frame.addEventListener('pointerup',end); frame.addEventListener('pointercancel',end);
  frame.addEventListener('dblclick',function(){{vb=base.slice(); apply();}});
  // crosshair readout for line charts: nearest sample of every series under the pointer
  var meta=[]; try{{meta=JSON.parse(document.getElementById('lv-meta').textContent)||[];}}catch(err){{}}
  if(meta.length){{
    var NS='http://www.w3.org/2000/svg', layer=document.createElementNS(NS,'g');
    layer.setAttribute('pointer-events','none'); svg.appendChild(layer);
    function near(a,v){{var lo=0,hi=a.length-1; while(hi-lo>1){{var m=(lo+hi)>>1; if(a[m]<v)lo=m; else hi=m;}}
      return Math.abs(a[lo]-v)<=Math.abs(a[hi]-v)?lo:hi;}}
    function clear(){{while(layer.firstChild)layer.removeChild(layer.firstChild);}}
    svg.addEventListener('pointermove',function(e){{
      if(drag)return; var p=toSvg(e), hit=null;
      meta.forEach(function(m){{var r=m.plot; if(p[0]>=r[0]&&p[0]<=r[0]+r[2]&&p[1]>=r[1]&&p[1]<=r[1]+r[3])hit=m;}});
      clear();
      if(!hit){{return;}}
      var best=null;
      hit.series.forEach(function(sr){{if(!sr.px.length)return; var i=near(sr.px,p[0]);
        if(!best||Math.abs(sr.px[i]-p[0])<Math.abs(best.sr.px[best.i]-p[0]))best={{sr:sr,i:i}};}});
      if(!best)return;
      var x=best.sr.px[best.i], r=hit.plot, ln=document.createElementNS(NS,'line');
      ln.setAttribute('x1',x);ln.setAttribute('x2',x);ln.setAttribute('y1',r[1]);ln.setAttribute('y2',r[1]+r[3]);
      ln.setAttribute('stroke',hit.ink);ln.setAttribute('stroke-opacity','0.35');ln.setAttribute('stroke-width','1');
      layer.appendChild(ln);
      tip.textContent=''; var head=document.createElement('div'); head.className='lv-x'; head.textContent=best.sr.x[best.i];
      tip.appendChild(head);
      hit.series.forEach(function(sr){{if(!sr.px.length)return; var i=near(sr.px,x);
        if(Math.abs(sr.px[i]-x)>6)return;
        var c=document.createElementNS(NS,'circle'); c.setAttribute('cx',sr.px[i]); c.setAttribute('cy',sr.py[i]);
        c.setAttribute('r','4'); c.setAttribute('fill',sr.color); c.setAttribute('stroke',hit.bg); c.setAttribute('stroke-width','2');
        layer.appendChild(c);
        var row=document.createElement('div'); row.className='lv-row';
        var sw=document.createElement('span'); sw.className='lv-sw'; sw.style.background=sr.color;
        var nm=document.createElement('span'); nm.textContent=sr.name;
        var v=document.createElement('span'); v.className='lv-v'; v.textContent=sr.y[i];
        row.appendChild(sw); row.appendChild(nm); row.appendChild(v); tip.appendChild(row);}});
      tip.classList.add('on'); place(e);
    }});
    svg.addEventListener('pointerleave',function(){{clear(); tip.classList.remove('on');}});
  }}
}})();
</script>
</body></html>
"""


def _data_block(description: str, tables) -> str:
    """Accessible extras below the chart: the text description and the data table(s), with CSV."""
    from urllib.parse import quote
    parts = []
    if description:
        parts.append(f'<p class="lv-desc">{escape(description)}</p>')
    for t in tables:
        if t is None or not len(t.columns):
            continue
        csv = t.to_csv()
        link = (f'<a class="lv-csv" download="{escape(t.name or "data")}.csv" '
                f'href="data:text/csv;charset=utf-8,{quote(csv)}">Download CSV</a>') if len(csv) < 2_000_000 else ""
        head = f'<h4 class="lv-th">{escape(t.title)}</h4>' if getattr(t, "title", "") and len(tables) > 1 else ""
        parts.append(f'{head}<div class="lv-table">{t.to_html()}</div>{link}')
    if not parts:
        return ""
    return '<details class="lv-data"><summary>Description and data</summary>' + "".join(parts) + "</details>"


def render(svg: str, title: str | None = None, meta=None, description: str = "", tables=()) -> str:
    import json
    import re
    m = re.search(r'width="([\d.]+)"', svg)
    width = int(float(m.group(1))) + 32 if m else 900
    meta_json = json.dumps(meta or [], separators=(",", ":")).replace("</", "<\\/")
    return _PAGE.format(svg=svg, title=escape(title or "Chart"), width=max(width, 360),
                        data=_data_block(description, tables), meta=meta_json)
