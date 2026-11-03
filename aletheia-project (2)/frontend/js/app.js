(function(){
var $=function(s){return document.querySelector(s)},$$=function(s){return Array.prototype.slice.call(document.querySelectorAll(s))};
var names={check:'Check Video',analysis:'Analysis Score',report:'Report Incident',how:'How It Works',privacy:'Privacy & Safety'};
function show(v){
  if(!names[v])v='check';
  $$('.view').forEach(function(e){e.classList.toggle('on',e.id==='v-'+v)});
  $$('.nav').forEach(function(b){if(b.dataset.go===v)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
  $('#crumb').textContent=names[v];window.scrollTo(0,0);
  if(location.hash!=='#'+v)history.replaceState(null,'','#'+v);
}
$$('[data-go]').forEach(function(b){b.addEventListener('click',function(){show(b.dataset.go)})});
window.addEventListener('hashchange',function(){show(location.hash.slice(1))});

var mode='file',picked=null,MAX=9600000;
function setMode(m){mode=m;$('#m-file').setAttribute('aria-pressed',m==='file');$('#m-link').setAttribute('aria-pressed',m==='link');
  $('#p-file').hidden=m!=='file';$('#p-link').hidden=m!=='link';$('#err').textContent=''}
$('#m-file').onclick=function(){setMode('file')};$('#m-link').onclick=function(){setMode('link')};
$('#browse').onclick=function(){$('#file').click()};
function take(f){
  if(!/\.(mp4|mov|webm)$/i.test(f.name)){picked=null;$('#fname').textContent='';$('#err').textContent='This file type is not supported. Use MP4, MOV or WEBM.';return}
  picked=f;$('#err').textContent='';$('#fname').textContent=f.name+' ('+(f.size/1e6).toFixed(1)+' MB)';
  var vp=$('#v-preview');
  if(vp){
    if(vp.src){URL.revokeObjectURL(vp.src);vp.src=''}
    vp.src=URL.createObjectURL(f);
    vp.load();
    $('#v-preview-wrap').style.display='block';
  }
}
$('#file').onchange=function(e){if(e.target.files[0])take(e.target.files[0])};
var d=$('#drop');
['dragenter','dragover'].forEach(function(t){d.addEventListener(t,function(e){e.preventDefault();d.classList.add('over')})});
['dragleave','drop'].forEach(function(t){d.addEventListener(t,function(e){e.preventDefault();d.classList.remove('over')})});
d.addEventListener('drop',function(e){if(e.dataTransfer.files[0])take(e.dataTransfer.files[0])});
function validUrl(u){try{var x=new URL(u);return /^https?:$/.test(x.protocol)&&x.hostname.indexOf('.')>0}catch(e){return false}}
var busy=false,lastResult=null;
function band(s){return s>=70?'tampered':s>=40?'suspicious':'authentic'}
var TEXT={
  tampered:['likely fake','This video looks likely fake','Multiple suspicious signs were found in the video.'],
  suspicious:['not sure','We are not sure about this video','The pulse signal is weak or unclear. Poor lighting, compression, or editing can cause this.'],
  authentic:['likely real','This video looks real','A natural pulse signal was found in the face.']};
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function render(r){
  lastResult=r;
  var s=Math.max(0,Math.min(100,Math.round(r.score))),b=band(s),t=TEXT[b];
  $('#v-analysis').setAttribute('data-band',b);
  var nm=String(r.fileName||'video');$('#a-name').textContent=nm.length>48?nm.slice(0,45)+'…':nm;
  if(r.sha256)$('#a-hash').textContent=r.sha256;
  if(r.fps)$('#a-fps').textContent=r.fps;
  if(r.duration)$('#a-dur').textContent=r.duration;
  $('#a-score').textContent=s+'%';$('#a-band').textContent=t[0];
  $('#a-pin').style.left=s+'%';$('#a-pinlabel').textContent=s+'%';
  $('.bar').setAttribute('aria-label','Chance this video is fake: '+s+' percent, '+t[0]);
  $('#a-vt').textContent=r.verdictTitle||t[1];$('#a-vs').textContent=r.verdictDetail||t[2];
  var c=$('#a-checks');
  if(r.checks&&r.checks.length){
    c.hidden=false;
    c.innerHTML=r.checks.map(function(k){return '<div class="card"><div class="sev"'+(k.ok?' style="color:var(--grn)"':'')+'>'+(k.ok?'OK':'PROBLEM')+'</div><h3>'+esc(k.label)+'</h3><p>'+esc(k.text)+'</p></div>'}).join('');
  }else c.hidden=(b!=='tampered');
}
function browserTrim(file,onp){
  return new Promise(function(resolve,reject){
    var v=document.createElement('video'),url=URL.createObjectURL(file),done=false;
    v.muted=true;v.playsInline=true;v.preload='auto';v.src=url;
    function fail(m){if(done)return;done=true;URL.revokeObjectURL(url);reject(new Error(m))}
    var NO='This browser cannot record streams directly. Please ensure the backend is running for FFmpeg trimming.';
    v.onerror=function(){fail('This browser cannot open this video to trim it. Try an MP4 under 9.6 MB.')};
    v.onloadedmetadata=function(){
      if(!v.captureStream||!window.MediaRecorder||!isFinite(v.duration)||v.duration<=0){fail(NO);return}
      var mime=['video/mp4;codecs=avc1.42E01E','video/mp4','video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'].filter(function(m){return MediaRecorder.isTypeSupported(m)})[0],ext=/mp4/.test(mime||'')?'mp4':'webm';
      if(!mime){fail(NO);return}
      var bits=MAX*0.8*8,len=Math.min(v.duration,bits/1200000),rate=Math.max(300000,Math.min(Math.floor(bits/len)-48000,8000000)),rec,chunks=[];
      try{rec=new MediaRecorder(v.captureStream(),{mimeType:mime,videoBitsPerSecond:rate,audioBitsPerSecond:48000})}catch(e){fail(NO);return}
      rec.ondataavailable=function(e){if(e.data&&e.data.size)chunks.push(e.data)};
      rec.onstop=function(){
        if(done)return;done=true;URL.revokeObjectURL(url);
        var b=new Blob(chunks,{type:mime.split(';')[0]});
        resolve(new File([b],file.name.replace(/\.[^.]+$/,'')+'_portal.'+ext,{type:mime.split(';')[0]}));
      };
      v.ontimeupdate=function(){if(onp)onp(Math.min(99,Math.round(v.currentTime/len*100)));if(v.currentTime>=len&&rec.state==='recording')rec.stop()};
      v.onended=function(){if(rec.state==='recording')rec.stop()};
      rec.start(1000);
      v.play().catch(function(){fail('Playback blocked. Press Check This Video again.')});
    };
  });
}
function trim(file,onp){
  if(onp)onp(15);
  // Prefer reliable server-side FFmpeg trimming for Chrome & Safari compatibility
  if(window.AletheiaAPI&&window.AletheiaAPI.trimVideo){
    if(onp)onp(35);
    return window.AletheiaAPI.trimVideo(file).then(function(f){
      if(onp)onp(100);
      return f;
    }).catch(function(err){
      return browserTrim(file,onp);
    });
  }
  return browserTrim(file,onp);
}
$('#run').onclick=function(){
  if(busy)return;var input;
  if(mode==='file'){if(!picked){$('#err').textContent='Choose a video file first.';return}input={file:picked,original:picked}}
  else{var u=$('#url').value.trim();if(!validUrl(u)){$('#err').textContent='Paste a full link starting with http:// or https://';return}input={url:u}}
  $('#err').textContent='';busy=true;$('#run').disabled=true;$('#prog').style.display='block';
  var timer=null;
  function stop(){clearInterval(timer);busy=false;$('#run').disabled=false;$('#prog').style.display='none';$('#pbar').style.width='0';$('#stat').textContent=''}
  function analyze(){
    var ph=['Loading video…','Scanning scene cuts…','Reading skin & pulse…','Checking generative AI…','Working out the score…'],i=0;
    function paint(){$('#pbar').style.width=((i+1)/ph.length*100)+'%';$('#stat').textContent=ph[i]}
    paint();timer=setInterval(function(){if(i<ph.length-1){i++;paint()}},900);
    return AletheiaAPI.analyze(input);
  }
  analyze().then(function(r){stop();render(r);setDl(input.file||null);show('analysis')},
    function(e){stop();$('#err').textContent='Could not check the video. '+((e&&e.message)||'Please try again.')});
};
$('#pdf').onclick=function(){
  if(lastResult&&lastResult.reportUrl)window.open(lastResult.reportUrl,'_blank','noopener');
  else window.print();
};

var step=0,rmode='link';
function wiz(n){
  step=Math.max(0,Math.min(2,n));
  $$('.pane').forEach(function(p,i){p.classList.toggle('on',i===step)});
  $$('.st').forEach(function(s,i){s.classList.toggle('on',i===step);s.classList.toggle('done',i<step)});
  $('#back').style.visibility=step===0?'hidden':'visible';
  $('#next').style.display=step===2?'none':'';
}
$$('.st').forEach(function(s,i){s.onclick=function(){wiz(i)}});
$('#back').onclick=function(){wiz(step-1)};
$('#next').onclick=function(){wiz(step+1)};
function setR(m){rmode=m;$('#o-link').setAttribute('aria-pressed',m==='link');$('#o-file').setAttribute('aria-pressed',m==='file');
  $('#r-link').hidden=m!=='link';$('#r-file').hidden=m!=='file'}
$('#o-link').onclick=function(){setR('link')};$('#o-file').onclick=function(){setR('file')};
$('#verify').onclick=function(){
  var u=$('#r-url').value.trim();$('#r-ok').textContent='';$('#r-err').textContent='';
  if(validUrl(u))$('#r-ok').textContent='Link looks good. Keep a copy for the complaint form.';
  else $('#r-err').textContent='Enter a full link starting with http:// or https://';
};
var checks=$$('#s3 .chk input');
checks.forEach(function(c){c.onchange=function(){
  c.parentNode.classList.toggle('d',c.checked);
  var n=checks.filter(function(x){return x.checked}).length;
  $('#cnt').textContent=n===checks.length?'All done. You are ready to file.':n+' of '+checks.length+' done';
}});
/*DESC*/
// The description is written from the person's own answers in Report Incident, step 1.
// It describes what happened to them. It does not include the detector score or verdict.
var SIT=[
  'A fake (deepfake) video of me is being shared online. It uses my face or voice without my permission.',
  'A fake (deepfake) video of someone I know is being shared online without their permission.',
  'A fake (deepfake) video is being used to threaten and blackmail me.',
  'A fake (deepfake) video is being used to cheat people.',
  'A fake (deepfake) video is spreading false claims and harming a person\'s name.'],
  sit=-1,edited=false;
function sentence(t){t=t.replace(/\s+/g,' ').trim();if(!t)return '';return /[.!?…]$/.test(t)?t:t+'.'}
function buildDesc(){
  if(sit<0)return '';
  var where=$('#d-where').value.trim(),own=sentence($('#d-own').value),
  money=$('#d-money').checked?'Someone is asking me for money because of this video.':'',
  end='I request that it be checked, removed and investigated. The video or link and an evidence report are attached.';
  function make(o){return [SIT[sit],where?'I saw it here: '+sentence(where):'',o,money,end].filter(Boolean).join(' ')}
  var t=make(own);
  if(t.length>500&&own){var over=t.length-500;own=own.slice(0,Math.max(0,own.length-over-1)).replace(/\s+\S*$/,'')+'…';t=make(own)}
  return t.slice(0,500);
}
function regen(){if(edited)return;$('#desc').value=buildDesc();cnt()}
$$('#d-sit .opt').forEach(function(b){b.onclick=function(){
  sit=+b.dataset.i;$$('#d-sit .opt').forEach(function(x){x.setAttribute('aria-pressed',x===b)});regen()}});
$('#d-where').addEventListener('input',regen);$('#d-own').addEventListener('input',regen);
$('#d-money').onchange=function(){$('#d-moneynote').hidden=!this.checked;regen()};
$('#desc').addEventListener('input',function(){edited=true;$('#d-reset').hidden=false;cnt()});
$('#d-reset').onclick=function(){edited=false;this.hidden=true;regen()};
/*END*/
var dlUrl=null;
function setDl(f){var a=$('#a-dl');if(dlUrl){URL.revokeObjectURL(dlUrl);dlUrl=null}
  if(f){dlUrl=URL.createObjectURL(f);a.href=dlUrl;a.download=f.name;a.hidden=false}else a.hidden=true}
function cnt(){var n=$('#desc').value.length,e=$('#d-cnt');e.textContent=n+' of 500 characters'+(n<100?'. The portal needs at least 100.':'');e.style.color=n<100?'var(--red)':'var(--mut)'}
function copyText(t,el){
  function ok(){el.textContent='Copied.';setTimeout(function(){el.textContent=''},2500)}
  function fb(){var x=document.createElement('textarea');x.value=t;document.body.appendChild(x);x.select();
    try{document.execCommand('copy');ok()}catch(e){el.textContent='Select the text and copy it.'}document.body.removeChild(x)}
  if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(t).then(ok,fb);else fb();
}
function copyDesc(el){var t=$('#desc').value;if(!t.trim()){el.textContent='Write your description in step 1 first.';setTimeout(function(){el.textContent=''},3500);return}copyText(t,el)}
$('#d-copy').onclick=function(){copyDesc($('#d-msg'))};
$('#r-copy').onclick=function(){copyDesc($('#r-copied'))};
var rUrl=null;
$('#r-fbrowse').onclick=function(){$('#r-fin').click()};
$('#r-fin').onchange=function(e){
  var f=e.target.files[0];if(!f)return;
  $('#r-ferr').textContent='';$('#r-dl').hidden=true;$('#r-stat').textContent='';
  if(!/\.(mp4|mov|webm)$/i.test(f.name)){$('#r-ferr').textContent='This file type is not supported. Use MP4, MOV or WEBM.';return}
  $('#r-fname').textContent=f.name+' ('+(f.size/1e6).toFixed(1)+' MB)';
  function ready(g){if(rUrl)URL.revokeObjectURL(rUrl);rUrl=URL.createObjectURL(g);var a=$('#r-dl');a.href=rUrl;a.download=g.name;
    a.textContent='Download video for the portal ('+(g.size/1e6).toFixed(1)+' MB)';a.hidden=false;
    $('#r-stat').textContent=f.size>MAX?'Trimmed to fit the portal. Download it and upload it in the last filing step.':'Already small enough. You can upload this file as it is.'}
  if(f.size<=MAX){ready(f);return}
  $('#r-prog').style.display='block';$('#r-pbar').style.width='0';$('#r-stat').textContent='Trimming. Keep this tab open.';
  trim(f,function(p){$('#r-pbar').style.width=p+'%';$('#r-stat').textContent='Trimming… '+p+'%'}).then(
    function(g){$('#r-prog').style.display='none';ready(g)},
    function(err){$('#r-prog').style.display='none';$('#r-stat').textContent='';$('#r-ferr').textContent=err.message});
};
render({fileName:'incident_clip_oct24_statement.mp4',sha256:$('#a-hash').textContent,fps:'29.97',duration:'0:42',score:88});lastResult=null;cnt();
wiz(0);show(location.hash.slice(1));
})();
