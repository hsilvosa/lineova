"""JavaScript for the smart zoom (see ``lineova._zoom``). Injected into the interactive page only when the
chart has zoomable plots. It talks to the base script through ``window.__lv``."""

CSS = """
  .lv-frame{user-select:none;-webkit-user-select:none}
  .lv-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 8px;font-size:12px}
  .lv-bar button,.lv-chip{font:inherit;border:1px solid #d5d8d7;background:#fff;border-radius:14px;padding:2px 10px;cursor:pointer;color:#333}
  .lv-bar button:hover,.lv-chip:hover{background:#f0f2f1}
  .lv-bar label{display:flex;gap:4px;align-items:center;color:#555;cursor:pointer}
  .lv-chip{display:inline-flex;gap:6px;align-items:center}
  .lv-chip i{width:9px;height:9px;border-radius:2px;display:inline-block}
  .lv-chip.off{opacity:.45;text-decoration:line-through}
  .lv-mini{margin-top:6px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);touch-action:none}
  .lv-mini svg{display:block;width:100%;height:auto}
  .lv-mini .win{fill:rgba(47,91,211,.13);cursor:grab}
  .lv-mini .hd{fill:#2f5bd3;cursor:ew-resize}
"""

JS = r"""
(function(){
  var L=window.__lv; if(!L) return;
  var svg=L.svg, frame=L.frame, tip=L.tip, NS='http://www.w3.org/2000/svg';
  var plots=[]; L.meta.forEach(function(m){ if(m.zoom) plots.push(make(m)); });
  if(!plots.length) return;
  var st=document.createElement('style'); st.textContent=window.__lvZoomCss||''; document.head.appendChild(st);

  function el(name,attrs,parent){var e=document.createElementNS(NS,name); for(var k in attrs){ if(attrs[k]!==null&&attrs[k]!==undefined) e.setAttribute(k,attrs[k]); } if(parent) parent.appendChild(e); return e;}
  function clear(g){while(g.firstChild) g.removeChild(g.firstChild);}
  function lower(a,v){var lo=0,hi=a.length; while(lo<hi){var m=(lo+hi)>>1; if(a[m]<v) lo=m+1; else hi=m;} return lo;}
  function fmtNum(v){var a=Math.abs(v); if(a>=1e9) return (v/1e9).toPrecision(3).replace(/\.?0+$/,'')+'B';
    if(a>=1e6) return (v/1e6).toPrecision(3).replace(/\.?0+$/,'')+'M';
    return new Intl.NumberFormat('en',{maximumSignificantDigits:5}).format(v).replace(/-/g,'\u2212');}
  function fmtX(P,v){ if(P.z.x.kind!=='time') return fmtNum(v);
    var iso=new Date(v/1e6).toISOString(), span=(P.x1-P.x0)/864e11;
    return span>5? iso.slice(0,10) : iso.slice(0,16).replace('T',' ');}

  function make(m){
    var z=m.zoom, P={m:m,z:z,lp:z.plot,off:[m.plot[0]-z.plot[0],m.plot[1]-z.plot[1]],
      full:[z.x.d0,z.x.d1],fy:[z.y.d0,z.y.d1],x0:z.x.d0,x1:z.x.d1,y0:z.y.d0,y1:z.y.d1,hidden:{},fit:false,dyn:false};
    P.marks=svg.querySelector('.'+z.id+'-marks'); P.parent=P.marks.parentNode;
    var cp=el('clipPath',{id:z.id+'-cp'},svg); el('rect',{x:P.lp[0]-1,y:P.lp[1]-1,width:P.lp[2]+2,height:P.lp[3]+2},cp);
    P.gGrid=el('g',{'clip-path':'url(#'+z.id+'-cp)'}); P.parent.insertBefore(P.gGrid,P.marks);
    P.gSeries=el('g',{'clip-path':'url(#'+z.id+'-cp)'}); P.parent.insertBefore(P.gSeries,P.marks.nextSibling);
    P.gAxis=el('g',{}); P.parent.insertBefore(P.gAxis,P.gSeries.nextSibling);
    P.gCross=el('g',{'pointer-events':'none'}); P.parent.appendChild(P.gCross);
    P.gBrush=el('g',{'pointer-events':'none'}); P.parent.appendChild(P.gBrush);
    return P;
  }
  function cls(P,k){return svg.querySelectorAll('.'+P.z.id+'-'+k);}
  function vis(P,k,on){cls(P,k).forEach(function(e){e.style.display=on?'':'none';});}
  function px(P,v){return P.lp[0]+(v-P.x0)/(P.x1-P.x0)*P.lp[2];}
  function py(P,v){return P.lp[1]+P.lp[3]-(v-P.y0)/(P.y1-P.y0)*P.lp[3];}
  function xAt(P,x){return P.x0+(x-P.lp[0])/P.lp[2]*(P.x1-P.x0);}

  function pick(levels,a,b,target,cap,minGap){
    var best=null,bs=1e9,coarse=null;
    levels.forEach(function(lv){var i=lower(lv.v,a-1e-9*Math.abs(b-a)), j=lower(lv.v,b+1e-9*Math.abs(b-a)); var n=j-i;
      if(n<2) return; if(!coarse) coarse={lv:lv,i:i,j:j};
      if(n>cap) return; var s=Math.abs(n-target); if(s<bs){bs=s;best={lv:lv,i:i,j:j};}});
    return best||coarse||(levels.length?{lv:levels[0],i:lower(levels[0].v,a),j:lower(levels[0].v,b)}:null);
  }
  function line(g,x1,y1,x2,y2,color,w,dash,cl){return el('line',{x1:x1,y1:y1,x2:x2,y2:y2,stroke:color,'stroke-width':w,'stroke-dasharray':dash?dash.join(' '):null},g);}
  function text(g,x,y,s,size,color,anchor){var t=el('text',{x:x,y:y,'font-size':size,fill:color,'text-anchor':anchor},g); t.textContent=s; return t;}

  function drawAxes(P){
    var z=P.z, s=z.style, lp=P.lp, size=s.size, i;
    if(s.x_visible||s.grid.x){
      var maxc=0; z.x.levels.forEach(function(lv){lv.l.forEach(function(l){if(l.length>maxc)maxc=l.length;});});
      var cap=Math.max(2,Math.floor(lp[2]/(Math.min(maxc,14)*size*0.58+16)));
      var pk=pick(z.x.levels,P.x0,P.x1,Math.max(2,lp[2]/90),cap);
      if(pk){ for(i=pk.i;i<pk.j;i++){var v=pk.lv.v[i]; if(v<P.x0||v>P.x1) continue; var x=px(P,v);
        if(s.grid.x) line(P.gGrid,x,lp[1],x,lp[1]+lp[3],s.grid.color,s.grid.width,s.grid.dash);
        if(s.x_visible){ if(s.xk) line(P.gAxis,x,s.xk[0],x,s.xk[1],s.ink,s.axis_width);
          text(P.gAxis,x,s.xt_y,pk.lv.l[i],size,s.label,'middle');} } }
    }
    if(P.yDyn){
      var pk2=pick(z.y.levels,P.y0,P.y1,Math.max(2,lp[3]/46),Math.max(2,Math.floor(lp[3]/(size*1.7))));
      if(pk2){ for(i=pk2.i;i<pk2.j;i++){var w=pk2.lv.v[i]; if(w<P.y0||w>P.y1) continue; var y=py(P,w);
        if(s.grid.y) line(P.gGrid,lp[0],y,lp[0]+lp[2],y,s.grid.color,s.grid.width,s.grid.dash);
        if(s.y_visible){ if(s.yk) line(P.gAxis,s.yk[0],y,s.yk[1],y,s.ink,s.axis_width);
          text(P.gAxis,s.yt_x,y+s.dy_mid,pk2.lv.l[i],size,s.label,'end');} } }
    }
    if(s.axis_style==='baseline'&&P.yDyn&&s.y_visible!==false){
      var yz=(P.y0<=0&&0<=P.y1)?py(P,0):lp[1]+lp[3]; line(P.gAxis,lp[0],yz,lp[0]+lp[2],yz,s.ink,s.axis_width); }
    if(s.axis_style==='range'){
      if(s.x_visible) line(P.gAxis,lp[0],lp[1]+lp[3]+s.offset,lp[0]+lp[2],lp[1]+lp[3]+s.offset,s.ink,s.axis_width);
      if(s.y_visible&&P.yDyn) line(P.gAxis,lp[0]-s.offset,lp[1],lp[0]-s.offset,lp[1]+lp[3],s.ink,s.axis_width);
    }
  }

  function series(P){
    var z=P.z, lp=P.lp, cols=Math.max(32,Math.round(lp[2]*2)), lo=Infinity, hi=-Infinity;
    var vs=[];
    z.series.forEach(function(sr,k){
      if(P.hidden[sr.name]) return;
      var i0=Math.max(0,lower(sr.x,P.x0)-1), i1=Math.min(sr.x.length,lower(sr.x,P.x1)+1);
      vs.push({sr:sr,i0:i0,i1:i1});
      for(var i=i0;i<i1;i++){var y=sr.y[i]; if(y!==null&&isFinite(y)&&sr.x[i]>=P.x0&&sr.x[i]<=P.x1){ if(y<lo)lo=y; if(y>hi)hi=y;} }
    });
    if(P.fit){ if(!isFinite(lo)){lo=P.fy[0];hi=P.fy[1];} var pad=(hi-lo)*0.06||Math.abs(hi)*0.05||1; P.y0=lo-pad; P.y1=hi+pad; P.yDyn=true; }
    else { P.y0=P.fy[0]; P.y1=P.fy[1]; P.yDyn=false; }
    drawAxes(P);
    vs.forEach(function(o){
      var sr=o.sr, xs=[], ys=[], n=o.i1-o.i0, i;
      if(n>4*cols){
        var cur=null, f=null, mn=null, mx=null, la=null;
        function flush(){ if(!f) return; var arr=[f,mn,mx,la].sort(function(a,b){return a.i-b.i;}), last=-1;
          arr.forEach(function(p){ if(p.i!==last){ xs.push(p.x); ys.push(p.y); last=p.i; } }); }
        for(i=o.i0;i<o.i1;i++){ var y=sr.y[i]; if(y===null||!isFinite(y)){ flush(); f=mn=mx=la=null; cur=null; xs.push(NaN); ys.push(NaN); continue; }
          var c=Math.floor((sr.x[i]-P.x0)/(P.x1-P.x0)*cols); if(c!==cur){ flush(); cur=c; f={i:i,x:sr.x[i],y:y}; mn=f; mx=f; la=f; }
          else { var p={i:i,x:sr.x[i],y:y}; if(y<mn.y)mn=p; if(y>mx.y)mx=p; la=p; } }
        flush();
      } else { for(i=o.i0;i<o.i1;i++){ var yy=sr.y[i]; xs.push(sr.x[i]); ys.push(yy===null?NaN:yy); } }
      var d='', pen=false;
      for(i=0;i<xs.length;i++){ if(!isFinite(ys[i])){pen=false;continue;} d+=(pen?'L':'M')+px(P,xs[i]).toFixed(1)+' '+py(P,ys[i]).toFixed(1); pen=true; }
      if(d) el('path',{d:d,fill:'none',stroke:sr.color,'stroke-width':sr.width,'stroke-linejoin':'round','stroke-linecap':'round',
        'stroke-dasharray':sr.dash?sr.dash.join(' '):null},P.gSeries);
    });
  }

  function draw(P){
    var z=P.z, xCh=P.x0!==P.full[0]||P.x1!==P.full[1], anyHid=Object.keys(P.hidden).some(function(k){return P.hidden[k];});
    P.dyn=xCh||anyHid||P.fit;
    P.m.zoomActive=P.dyn;
    clear(P.gGrid); clear(P.gSeries); clear(P.gAxis); clear(P.gCross);
    ['marks','ov'].forEach(function(k){vis(P,k,!P.dyn);});
    ['xt','xk','xg','xa'].forEach(function(k){vis(P,k,!P.dyn);});
    ['yt','yk','yg','ya'].forEach(function(k){vis(P,k,!(P.dyn&&P.fit));});
    if(!P.dyn){ P.y0=P.fy[0]; P.y1=P.fy[1]; return; }
    series(P);
  }

  var linked=plots.length>1&&plots.every(function(P){return P.z.x.kind===plots[0].z.x.kind&&Math.abs(P.full[0]-plots[0].full[0])<=1e-9*Math.abs(P.full[1]-P.full[0])&&Math.abs(P.full[1]-plots[0].full[1])<=1e-9*Math.abs(P.full[1]-P.full[0]);});
  function setWin(P,a,b,fromLink){
    var f0=P.full[0], f1=P.full[1], span=f1-f0, w=Math.min(span,Math.max(span/600,b-a));
    if(b-a>=span){a=f0;b=f1;} else { if(a<f0){a=f0;} if(a+w>f1){a=f1-w;} b=a+w; }
    P.x0=a; P.x1=b; draw(P); updateMini();
    if(linked&&!fromLink) plots.forEach(function(Q){ if(Q!==P) setWin(Q,a,b,true); });
  }
  function reset(){ fc.checked=false; plots.forEach(function(P){P.x0=P.full[0];P.x1=P.full[1];P.hidden={};P.fit=false;draw(P);}); updateMini(); syncChips(); }

  function at(e){ var g=L.toSvg(e), r=null; plots.forEach(function(P){ var x=g[0]-P.off[0], y=g[1]-P.off[1], lp=P.lp;
    if(x>=lp[0]&&x<=lp[0]+lp[2]&&y>=lp[1]&&y<=lp[1]+lp[3]) r={P:P,x:x,y:y}; }); return r; }
  window.__lvZoom={owns:function(e){return !!at(e);}};

  frame.addEventListener('wheel',function(e){ var h=at(e); if(!h) return; e.preventDefault();
    var P=h.P, k=Math.exp(e.deltaY*0.0015), w=(P.x1-P.x0)*k, v=xAt(P,h.x), f=(v-P.x0)/(P.x1-P.x0);
    setWin(P,v-f*w,v+(1-f)*w); },{passive:false});

  var gest=null;
  frame.addEventListener('pointerdown',function(e){ var h=at(e); if(!h) return;
    gest={P:h.P,x:e.clientX,x0:h.P.x0,x1:h.P.x1,brush:e.shiftKey,sx:h.x};
    frame.setPointerCapture(e.pointerId); frame.classList.add('dragging'); });
  frame.addEventListener('pointermove',function(e){
    if(gest){ var P=gest.P, r=svg.getBoundingClientRect(), k=svg.viewBox.baseVal.width/r.width;
      if(gest.brush){ var g=L.toSvg(e), cx=Math.max(P.lp[0],Math.min(P.lp[0]+P.lp[2],g[0]-P.off[0])); clear(P.gBrush);
        el('rect',{x:Math.min(gest.sx,cx),y:P.lp[1],width:Math.abs(cx-gest.sx),height:P.lp[3],fill:'rgba(47,91,211,.15)',stroke:'#2f5bd3','stroke-width':1},P.gBrush); gest.cx=cx; }
      else { var dx=(e.clientX-gest.x)*k/P.lp[2]*(gest.x1-gest.x0); setWin(P,gest.x0-dx,gest.x1-dx); }
      return; }
    cross(e); });
  function endG(e){ if(!gest) return; var P=gest.P;
    if(gest.brush&&gest.cx!==undefined&&Math.abs(gest.cx-gest.sx)>6){ var a=xAt(P,Math.min(gest.sx,gest.cx)), b=xAt(P,Math.max(gest.sx,gest.cx)); setWin(P,a,b); }
    clear(P.gBrush); gest=null; frame.classList.remove('dragging'); }
  frame.addEventListener('pointerup',endG); frame.addEventListener('pointercancel',endG);
  frame.addEventListener('dblclick',function(e){ if(at(e)) reset(); });

  var tipOwner=null;
  function near(a,v){var i=lower(a,v); if(i>0&&(i>=a.length||Math.abs(a[i-1]-v)<=Math.abs(a[i]-v))) i--; return Math.min(i,a.length-1);}
  function cross(e){
    var h=at(e); plots.forEach(function(P){clear(P.gCross);});
    if(!h||!h.P.dyn){ if(tipOwner){tip.classList.remove('on'); tipOwner=null;} return; }
    var P=h.P, v=xAt(P,h.x), best=null;
    P.z.series.forEach(function(sr){ if(P.hidden[sr.name]||!sr.x.length) return; var i=near(sr.x,v);
      if(sr.y[i]===null) return; var d=Math.abs(px(P,sr.x[i])-h.x); if(!best||d<best.d) best={sr:sr,i:i,d:d}; });
    if(!best) return;
    var x=px(P,best.sr.x[best.i]), lp=P.lp;
    el('line',{x1:x,x2:x,y1:lp[1],y2:lp[1]+lp[3],stroke:P.m.ink,'stroke-opacity':.35,'stroke-width':1},P.gCross);
    tip.textContent=''; var head=document.createElement('div'); head.className='lv-x'; head.textContent=fmtX(P,best.sr.x[best.i]); tip.appendChild(head);
    P.z.series.forEach(function(sr){ if(P.hidden[sr.name]||!sr.x.length) return; var i=near(sr.x,v), xx=px(P,sr.x[i]);
      if(sr.y[i]===null||Math.abs(xx-x)>6) return; var yy=py(P,sr.y[i]);
      if(yy>=lp[1]&&yy<=lp[1]+lp[3]) el('circle',{cx:xx,cy:yy,r:4,fill:sr.color,stroke:P.m.bg,'stroke-width':2},P.gCross);
      var row=document.createElement('div'); row.className='lv-row'; var sw=document.createElement('span'); sw.className='lv-sw'; sw.style.background=sr.color;
      var nm=document.createElement('span'); nm.textContent=sr.name; var vv=document.createElement('span'); vv.className='lv-v'; vv.textContent=fmtNum(sr.y[i]);
      row.appendChild(sw); row.appendChild(nm); row.appendChild(vv); tip.appendChild(row); });
    tip.classList.add('on'); tipOwner=P; L.place(e);
  }
  svg.addEventListener('pointerleave',function(){ plots.forEach(function(P){clear(P.gCross);}); if(tipOwner){tip.classList.remove('on'); tipOwner=null;} });

  // toolbar: reset, fit y, series chips
  var bar=document.createElement('div'); bar.className='lv-bar'; frame.parentNode.insertBefore(bar,frame);
  var rb=document.createElement('button'); rb.type='button'; rb.textContent='Reset zoom'; rb.onclick=reset; bar.appendChild(rb);
  var fl=document.createElement('label'), fc=document.createElement('input'); fc.type='checkbox'; fl.appendChild(fc); fl.appendChild(document.createTextNode('Fit y to view'));
  fc.onchange=function(){plots.forEach(function(P){P.fit=fc.checked; draw(P);}); updateMini();}; bar.appendChild(fl);
  var chips=[];
  if(plots.length===1&&plots[0].z.series.length>1){
    plots[0].z.series.slice().sort(function(a,b){return 0;}).forEach(function(sr){
      var c=document.createElement('button'); c.type='button'; c.className='lv-chip'; var sw=document.createElement('i'); sw.style.background=sr.color;
      c.appendChild(sw); c.appendChild(document.createTextNode(sr.name));
      c.onclick=function(){var P=plots[0]; P.hidden[sr.name]=!P.hidden[sr.name]; draw(P); syncChips();}; bar.appendChild(c); chips.push([c,sr]); });
  }
  function syncChips(){ chips.forEach(function(p){ p[0].classList.toggle('off',!!plots[0].hidden[p[1].name]); }); }

  // range strip under the chart: drag the window or its handles
  var mini=null, mwin, mhl, mhr, W=svg.viewBox.baseVal.width, MH=44;
  if(plots.length===1){
    var P0=plots[0], lp0=P0.lp; mini=document.createElement('div'); mini.className='lv-mini';
    var ms=el('svg',{viewBox:'0 0 '+W+' '+MH,preserveAspectRatio:'none'}); mini.appendChild(ms); frame.parentNode.insertBefore(mini,frame.nextSibling);
    var first=P0.z.series.filter(function(s){return !s.muted;})[0]||P0.z.series[0];
    if(first){ var n=first.x.length, step=Math.max(1,Math.floor(n/400)), lo=Infinity, hi=-Infinity, k;
      for(k=0;k<n;k+=step){var yy=first.y[k]; if(yy!==null){ if(yy<lo)lo=yy; if(yy>hi)hi=yy; } }
      var d=''; for(k=0;k<n;k+=step){var y2=first.y[k]; if(y2===null) continue;
        d+=(d?'L':'M')+(lp0[0]+(first.x[k]-P0.full[0])/(P0.full[1]-P0.full[0])*lp0[2]).toFixed(1)+' '+(MH-5-(y2-lo)/((hi-lo)||1)*(MH-10)).toFixed(1); }
      el('path',{d:d,fill:'none',stroke:first.color,'stroke-width':1.2,'stroke-opacity':.8},ms); }
    mwin=el('rect',{class:'win',y:0,height:MH},ms); mhl=el('rect',{class:'hd',y:4,height:MH-8,width:6,rx:2},ms); mhr=el('rect',{class:'hd',y:4,height:MH-8,width:6,rx:2},ms);
    var mdrag=null;
    function mval(e){var r=ms.getBoundingClientRect(); var x=(e.clientX-r.left)/r.width*W; return P0.full[0]+(x-lp0[0])/lp0[2]*(P0.full[1]-P0.full[0]);}
    [[mwin,'move'],[mhl,'l'],[mhr,'r']].forEach(function(p){ p[0].addEventListener('pointerdown',function(e){ mdrag={m:p[1],v:mval(e),a:P0.x0,b:P0.x1}; p[0].setPointerCapture(e.pointerId); e.preventDefault(); });
      p[0].addEventListener('pointermove',function(e){ if(!mdrag) return; var dv=mval(e)-mdrag.v;
        if(mdrag.m==='move') setWin(P0,mdrag.a+dv,mdrag.b+dv); else if(mdrag.m==='l') setWin(P0,Math.min(mdrag.a+dv,mdrag.b-(P0.full[1]-P0.full[0])/600),mdrag.b); else setWin(P0,mdrag.a,Math.max(mdrag.b+dv,mdrag.a+(P0.full[1]-P0.full[0])/600)); });
      p[0].addEventListener('pointerup',function(){mdrag=null;}); p[0].addEventListener('pointercancel',function(){mdrag=null;}); });
  }
  function updateMini(){ if(!mini) return; var P=plots[0], lp=P.lp, f=P.full[1]-P.full[0];
    var xa=lp[0]+(P.x0-P.full[0])/f*lp[2], xb=lp[0]+(P.x1-P.full[0])/f*lp[2];
    mwin.setAttribute('x',xa); mwin.setAttribute('width',Math.max(2,xb-xa)); mhl.setAttribute('x',xa-3); mhr.setAttribute('x',xb-3); }
  updateMini();
  window.__lvZoom.reset=reset; window.__lvZoom.setWindow=function(i,a,b){setWin(plots[i||0],a,b);}; window.__lvZoom.plots=plots;
})();
"""
