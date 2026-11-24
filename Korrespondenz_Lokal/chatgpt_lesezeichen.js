/* Lesezeichen „→ DocuManager“: übernimmt den in ChatGPT geöffneten Chat samt hochgeladener Dateien.
   Läuft in der angemeldeten ChatGPT-Seite und übergibt die Daten per postMessage an das DocuManager-Fenster
   (http://127.0.0.1:8765/#chatempfang); geht das nicht, wird eine Datei *.documanager.json in Downloads gespeichert.
   Nutzt die Schnittstelle, mit der die ChatGPT-Seite selbst Chats und Dateien lädt. */
(async()=>{
const Z='http://127.0.0.1:8765';
const m=location.pathname.match(/\/c\/([0-9a-f-]{36})/);
if(!/(^|\.)(chatgpt\.com|chat\.openai\.com)$/.test(location.hostname)||!m){alert('DocuManager: Bitte zuerst einen Chat in ChatGPT öffnen und dann das Lesezeichen anklicken.');return;}
const w=window.open(Z+'/#chatempfang','documanager');
const hinweis=t=>{let d=document.getElementById('dm-hinweis');if(!d){d=document.createElement('div');d.id='dm-hinweis';d.style.cssText='position:fixed;z-index:2147483647;right:16px;bottom:16px;background:#3341c9;color:#fff;padding:12px 16px;border-radius:10px;font:14px/1.4 system-ui;max-width:380px;box-shadow:0 6px 24px rgba(0,0,0,.3)';document.body.append(d);}d.textContent=t;};
try{
hinweis('DocuManager: Chat wird gelesen …');
const tok=(await (await fetch('/api/auth/session',{credentials:'include'})).json()).accessToken;
const H={Authorization:'Bearer '+tok};
const k=await (await fetch('/backend-api/conversation/'+m[1],{headers:H,credentials:'include'})).json();
if(!k.mapping)throw new Error('Chat nicht lesbar');
let n=k.mapping[k.current_node];const kette=[];while(n){kette.unshift(n);n=n.parent?k.mapping[n.parent]:null;}
const nachr=[],ids=new Map();
for(const x of kette){const g=x.message;if(!g||!g.content)continue;const r=g.author&&g.author.role;
for(const a of (g.metadata&&g.metadata.attachments)||[])if(a.id)ids.set(a.id,{name:a.name,mime:a.mime_type});
let t='';for(const p of g.content.parts||[]){if(typeof p==='string')t+=p;else if(p&&p.asset_pointer){const id=String(p.asset_pointer).replace(/^[a-z-]+:\/\//,'');if(!ids.has(id))ids.set(id,{name:'',mime:''});}}
if((r==='user'||r==='assistant')&&t.trim())nachr.push({rolle:r,text:t,zeit:g.create_time||null});}
const dateien=[];let i=0;
for(const [id,a] of ids){i++;hinweis('DocuManager: Datei '+i+' von '+ids.size+' wird geladen …');
try{let j=await (await fetch('/backend-api/files/'+id+'/download',{headers:H,credentials:'include'})).json();
if(!j.download_url)j=await (await fetch('/backend-api/files/download/'+id+'?conversation_id='+m[1]+'&inline=false',{headers:H,credentials:'include'})).json();
if(!j.download_url)throw new Error('kein Link');
const antw=await fetch(j.download_url);const b=await antw.arrayBuffer();
dateien.push({name:j.file_name||a.name||'',mime:a.mime||antw.headers.get('content-type')||'',daten:b});}
catch(e){dateien.push({name:a.name||id,mime:a.mime||'',fehler:'nicht verfügbar'});}}
const paket={documanager:'chat',titel:k.title||'ChatGPT-Chat',url:location.href,nachrichten:nachr,dateien:dateien};
let ok=false;addEventListener('message',e=>{if(e.origin===Z&&e.data&&e.data.documanager==='erhalten')ok=true;});
for(let v=0;v<40&&!ok&&w&&!w.closed;v++){try{w.postMessage(paket,Z);}catch(e){}await new Promise(r=>setTimeout(r,500));}
if(ok){hinweis('DocuManager: '+dateien.filter(d=>d.daten).length+' Datei(en) übertragen. Bitte im DocuManager-Fenster zuordnen.');try{w.focus();}catch(e){}}
else{const b64=buf=>{let s='';const u=new Uint8Array(buf);for(let q=0;q<u.length;q+=32768)s+=String.fromCharCode.apply(null,u.subarray(q,q+32768));return btoa(s);};
const json=JSON.stringify(Object.assign({},paket,{dateien:dateien.map(d=>d.daten?Object.assign({},d,{daten:b64(d.daten)}):d)}));
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([json],{type:'application/json'}));a.download=(k.title||'chat').replace(/[^\wäöüÄÖÜß -]+/g,'').trim().slice(0,60)+'.documanager.json';document.body.append(a);a.click();setTimeout(()=>{a.remove();URL.revokeObjectURL(a.href);},4000);
hinweis('DocuManager war nicht direkt erreichbar. Die Datei „'+a.download+'“ liegt jetzt in Downloads: Ziehen Sie sie in das DocuManager-Fenster.');}
}catch(e){hinweis('DocuManager: Der Chat konnte nicht gelesen werden ('+e.message+'). Sind Sie bei ChatGPT angemeldet?');}
setTimeout(()=>{const d=document.getElementById('dm-hinweis');if(d)d.remove();},20000);
})();
