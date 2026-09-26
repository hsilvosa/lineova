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
</style></head>
<body><main>
<div class="lv-frame" id="lv-frame">{svg}</div>
<div class="lv-hint">Hover for values · scroll to zoom · drag to pan · double-click to reset</div>
</main>
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
}})();
</script>
</body></html>
"""


def render(svg: str, title: str | None = None) -> str:
    import re
    m = re.search(r'width="([\d.]+)"', svg)
    width = int(float(m.group(1))) + 32 if m else 900
    return _PAGE.format(svg=svg, title=escape(title or "Chart"), width=max(width, 360))
