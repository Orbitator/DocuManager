'use strict';
/* Oberfläche der Korrespondenzverwaltung (Etappe 3).
   Gestaltung und Abläufe aus dem Klickprototyp, Daten aus dem lokalen Dienst (akte.py, app.py). */
(() => {
// ---------- Hilfen ----------
const $ = sel => document.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad = n => String(n).padStart(2, '0');
const isoHeute = () => { const t = new Date(); return `${t.getFullYear()}-${pad(t.getMonth()+1)}-${pad(t.getDate())}`; };
const dt = iso => iso ? iso.slice(0, 10).split('-').reverse().join('.') : '–';
const dShort = iso => { const [, m, d] = iso.split('-'); return `${d}.${m}.`; };
const tage = iso => Math.round((new Date(iso.slice(0,10) + 'T12:00') - new Date(isoHeute() + 'T12:00')) / 864e5);
const plusTage = (iso, n) => { const t = new Date(iso + 'T12:00'); t.setDate(t.getDate() + n); return `${t.getFullYear()}-${pad(t.getMonth()+1)}-${pad(t.getDate())}`; };
const relTage = iso => { const n = tage(iso); return n === 0 ? 'heute' : n === 1 ? 'morgen' : n === -1 ? 'gestern' : n < 0 ? `seit ${-n} Tagen überfällig` : `in ${n} Tagen`; };
const groesse = n => n == null ? '' : n < 1024 ? n + ' B' : n < 1048576 ? Math.round(n / 1024) + ' KB' : (n / 1048576).toFixed(1).replace('.', ',') + ' MB';
const WD = ['So','Mo','Di','Mi','Do','Fr','Sa'];
const MON = ['Januar','Februar','März','April','Mai','Juni','Juli','August','September','Oktober','November','Dezember'];
let snap = {};  // Eingaben eines Dialogs, festgehalten beim Speichern (der Dialog schließt vor dem Senden)
const val = id => document.getElementById(id)?.value ?? snap[id] ?? '';
const P = {
  ki: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8z"/>',
  home:'<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  inbox:'<path d="M3 13l3-8h12l3 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M3 13h5l1 3h6l1-3h5"/>',
  folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  cal:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  book:'<rect x="4" y="3" width="16" height="18" rx="2"/><circle cx="12" cy="10" r="2.6"/><path d="M8 17c.8-1.7 2.2-2.6 4-2.6s3.2.9 4 2.6"/>',
  archive:'<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4"/>',
  doc:'<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>',
  in:'<path d="M12 3v11M8 10l4 4 4-4"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  out:'<path d="M12 14V3M8 7l4-4 4 4"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  phone:'<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z"/>',
  note:'<path d="M5 4h14v11l-5 5H5z"/><path d="M14 20v-5h5M8 9h8M8 13h4"/>',
  draft:'<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13 7 4 4"/>',
  check:'<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  receipt:'<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  chat:'<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
  alert:'<path d="M12 3 22 20H2z"/><path d="M12 10v4M12 17v.5"/>',
  plus:'<path d="M12 5v14M5 12h14"/>', minus:'<path d="M5 12h14"/>',
  trash:'<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
  expand:'<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  restore:'<path d="M4 12a8 8 0 1 0 3-6.2"/><path d="M4 4v4h4"/>',
  para:'<path d="M14 4v16M18 4v16M18 4h-7a4 4 0 0 0 0 8h3"/>',
  link:'<path d="M10 14a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-1 1"/><path d="M14 10a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l1-1"/>',
  photo:'<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-8 8"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  move:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 13h7M13 10l3 3-3 3"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  stapel:'<rect x="7" y="3" width="13" height="15" rx="1.5"/><path d="M4 7v12.5A1.5 1.5 0 0 0 5.5 21H16"/>',
  lupe:'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  rotl:'<path d="M4 12a8 8 0 1 0 2.3-5.6M4 4v5h5"/>',
  rotr:'<path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5"/>',
  refresh:'<path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5"/>',
  gear:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>'
};
const I = (n, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24">${P[n]}</svg>`;

// Status: gespeicherter Wert bleibt, angezeigt wird die kurze Bezeichnung aus dem Prototyp
const ST_LABEL = {'Schreiben verfassen':'Verfassen'};
const ST_KEY = {'Offen':'offen','Recherchieren':'recherche','Schreiben verfassen':'verfassen','Schreiben abgeschickt':'abgeschickt','Wartet auf Antwort':'wartet','Erledigt':'erledigt'};
const ST_PILL = {'Offen':'grey','Schreiben abgeschickt':'ok','Wartet auf Antwort':'warn','Erledigt':'ok'};
const ST_ORDER = ['Offen','Recherchieren','Schreiben verfassen','Schreiben abgeschickt','Wartet auf Antwort','Erledigt'];
const stLabel = s => ST_LABEL[s] || s;
const statusPill = s => `<span class="pill ${ST_PILL[s] || ''}">${esc(stLabel(s))}</span>`;
const statusOptions = cur => ST_ORDER.map(s => `<option value="${esc(s)}" ${s === cur ? 'selected' : ''}>${esc(stLabel(s))}</option>`).join('');
const KIND = {eingang:['Eingang','in'],ausgang:['Versendet','out'],entwurf:['Entwurf','draft'],nachweis:['Versandnachweis','receipt'],telefonat:['Telefonat','phone'],notiz:['Notiz','note'],entscheidung:['Entscheidung','check'],chat:['Chat-Notiz','chat'],fehlt:['Original fehlt','doc']};
const FK = {frist:'Verbindliche Frist', wiedervorlage:'Wiedervorlage', aufgabe:'Aufgabe'};
const FKC = {frist:'crit', wiedervorlage:'warn', aufgabe:''};
const VERSAND = ['Post','Einschreiben','E-Mail','Fax','Persönlich','Online-Portal'];

// ---------- Schnittstelle ----------
// Ist der Dienst im Hintergrund nicht erreichbar, meldet der Browser nur „Load failed“ bzw. „Failed to fetch“.
const OFFLINE = 'DocuManager läuft nicht mehr. Bitte das Programm „DocuManager“ (Launchpad oder Spotlight) starten; danach diese Seite neu laden.';
async function holen(url, opt) {
  try { return await fetch(url, opt); } catch (e) { throw new Error(OFFLINE); }
}
async function api(path, body, method) {
  const opt = body === undefined && !method ? {} : {method: method || 'POST',
    headers: {'Content-Type': 'application/json', 'X-Korrespondenz': 'lokal'}, body: JSON.stringify(body || {})};
  const res = await holen('/api/' + path, opt);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Anfrage fehlgeschlagen.');
  return data;
}
async function upload(path, file) {
  const res = await holen('/api/' + path, {method: 'POST', body: file,
    headers: {'X-Korrespondenz': 'lokal', 'X-Dateiname': encodeURIComponent(file.name),
      ...(file.lastModified ? {'X-Datei-Datum': new Date(file.lastModified - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10)} : {})}});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Import fehlgeschlagen.');
  return data;
}

// ---------- Zustand ----------
const S = {view: 'uebersicht', v: null, teil: 'all', entry: null, tab: 'chronik', ktype: 'alle', ibSel: null,
  vb: 'alle', vs: 'alle', vt: 'alle', sortV: {k: 'frist', d: 1}, sortD: {k: 'datum', d: -1}, sortA: {k: 'datum', d: -1},
  fFilter: 'alle', aGroup: 'vorgang', aBereich: 'alle', aJahr: 'alle', aText: '', contact: null, abq: ''};
const D = {cases: [], statuses: [], groups: [], akte: null, inbox: [], fristen: [], archiv: [], kontakte: [], trash: [], eigene: ''};

async function loadBase() {
  const c = await api('cases');
  Object.assign(D, {cases: c.cases, statuses: c.statuses, groups: c.groups, ocr: c.ocr, version: c.version});
  D.inbox = (await api('posteingang')).dokumente;
  D.trash = (await api('papierkorb')).eintraege;
  D.arten = (await api('eintragsarten')).arten;
  D.empfaenger = (await api('empfaenger')).empfaenger;
  if (!D.ui) D.ui = await api('oberflaeche');
}

// ---------- Navigation ----------
function nav() {
  const items = [['uebersicht','Übersicht','home'],['posteingang','Posteingang','inbox',D.inbox.length],['vorgaenge','Vorgänge','folder'],
    ['fristen','Fristen','cal'],['archiv','Archiv','archive'],['adressbuch','Adressbuch','book'],['chat','Chat-Notizen','chat']];
  const cur = S.view === 'akte' ? 'vorgaenge' : S.view;
  $('#nav').innerHTML = items.map(([id, l, ic, n]) => `<a href="#${id}" class="${cur === id ? 'on' : ''}" ${cur === id ? 'aria-current="page"' : ''}>${I(ic)}${l}${n ? `<span class="cnt num">${n}</span>` : ''}</a>`).join('');
  $('#trashlink').innerHTML = `${I('trash')}Papierkorb${D.trash.length ? `<span class="cnt num" style="margin-left:auto">${D.trash.length}</span>` : ''}`;
  document.querySelector('.side-foot a[href="#einstellungen"]').innerHTML = `${I('gear')}Einstellungen`;
  $('#version').textContent = D.version || '';
}
const VIEWS = ['uebersicht','posteingang','vorgaenge','fristen','archiv','adressbuch','chat','papierkorb','einstellungen','chatempfang'];
async function route() {
  const h = location.hash.slice(1);
  if (h.startsWith('akte-')) { const id = +h.slice(5); if (S.v !== id) { S.v = id; S.teil = 'all'; S.entry = null; S.tab = 'chronik'; } S.view = 'akte'; }
  else S.view = VIEWS.includes(h) ? h : 'uebersicht';
  await render();
}
let renderToken = 0;
async function render() {
  const token = ++renderToken;
  try {
    await loadBase();
    if (S.view === 'akte') D.akte = await api('akte/' + S.v);
    if (S.view === 'fristen' || S.view === 'uebersicht') D.fristen = (await api('fristen')).fristen;
    if (S.view === 'archiv') D.archiv = (await api('archiv')).dokumente;
    if (['adressbuch', 'akte', 'posteingang', 'archiv'].includes(S.view)) D.kontakte = (await api('kontakte')).kontakte;
    if (S.view === 'einstellungen') { D.eigene = (await api('einstellungen')).eigene_angaben; D.mail = await api('mail'); D.sicherungen = (await api('sicherungen')).sicherungen; D.scanordner = await api('scanordner'); D.claude = await api('claude'); }
    if (S.view === 'chat') { D.chats = (await api('chatnotizen')).notizen; D.threads = (await api('chat/threads')).threads || []; }
  } catch (e) {
    if (token !== renderToken) return;
    werkzeugeParken(); $('#view').innerHTML = `<div class="notice crit">${I('alert')}<p>${esc(e.message)}</p></div>`;
    if (S.view === 'akte') { location.hash = 'vorgaenge'; }
    return;
  }
  if (token !== renderToken) return;
  nav();
  werkzeugeParken();
  $('#view').innerHTML = ({uebersicht: vHome, posteingang: vInbox, vorgaenge: vList, akte: vAkte, fristen: vFristen,
    archiv: vArchiv, adressbuch: vAb, chat: vChat, papierkorb: vTrash, einstellungen: vSettings, chatempfang: vEmpfang})[S.view]();
  textPanes();
  werkzeugeEinsetzen();
  if (S.view === 'einstellungen' && $('#lz-link')) fetch('/chatgpt_lesezeichen.js').then(r => r.text()).then(code => { $('#lz-link').href = 'javascript:' + encodeURIComponent(code.replace(/^\/\*[\s\S]*?\*\/\s*/, '')); });
  document.querySelector('.imp').hidden = !['posteingang', 'archiv'].includes(S.view);
  $('#impbtn').firstChild.textContent = S.view === 'archiv' ? 'Im Archiv ablegen ' : 'Dokument importieren ';
  if (S.view === 'archiv' && D.archiv.some(d => /Wartet|läuft/.test(d.ocr_status || ''))) { clearTimeout(followTimer); followTimer = setTimeout(() => { if (S.view === 'archiv' && !$('#modalroot').innerHTML) render(); }, 3000); }
  mailTexte();
  followInbox();
}

// ---------- Übersicht ----------
// Mehrfachauswahl (Bereiche, Kontakte): gewählte Einträge als Chips, weitere über eine Auswahlliste
const MULTI = {};
function mehrfach(id, optionen, gewaehlt, was) {
  MULTI[id] = {optionen: optionen.map(([v, l]) => [String(v), l]), was};
  return `<div class="multi" data-multi="${id}"><input type="hidden" id="${id}" value="${esc(JSON.stringify(gewaehlt.map(String)))}">${multiInnen(id, gewaehlt.map(String))}</div>`;
}
function multiInnen(id, gewaehlt) {
  const m = MULTI[id], label = v => (m.optionen.find(o => o[0] === v) || [v, v])[1];
  const frei = m.optionen.filter(o => !gewaehlt.includes(o[0]));
  return `<span class="mchips">${gewaehlt.map(v => `<span class="mchip">${esc(label(v))}<button type="button" data-act="multi-del" data-multi="${id}" data-v="${esc(v)}" aria-label="${esc(label(v))} entfernen">×</button></span>`).join('') || `<span class="muted" style="font-size:13px">keine</span>`}</span>
   ${frei.length ? `<select class="madd" data-multi="${id}" aria-label="${esc(m.was)} hinzufügen"><option value="">+ ${esc(m.was)}</option>${frei.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('')}</select>` : ''}`;
}
function multiSetzen(id, werte) {
  const box = document.querySelector(`.multi[data-multi="${id}"]`); if (!box) return;
  box.querySelector('input[type=hidden]').value = JSON.stringify(werte);
  box.querySelectorAll(':scope > :not(input)').forEach(e => e.remove());
  box.insertAdjacentHTML('beforeend', multiInnen(id, werte));
}
const multiWert = id => { try { return JSON.parse(val(id) || '[]'); } catch (e) { return []; } };
const kontaktOpt = () => [...D.kontakte].sort((x, y) => cmp(x.name, y.name)).map(k => [k.id, k.kurzname || k.name]);
async function vorgangBearbeiten(id) {
  const v = D.akte && D.akte.id === id ? D.akte : await api('akte/' + id);
  if (!D.kontakte.length) D.kontakte = (await api('kontakte')).kontakte;
  modal('Vorgang bearbeiten', `<label>Titel<input id="m-vt" value="${esc(v.titel)}" maxlength="160"></label>
   <label>Bereiche <small class="muted">· der erste ist der Hauptbereich</small></label>${mehrfach('m-vbs', D.groups.map(b => [b, b]), v.bereiche || [v.bereich], 'Bereich')}
   <label>Priorität<select id="m-vprio">${Object.keys(PRIO).map(p => `<option value="${p}" ${(v.prioritaet || 'keine') === p ? 'selected' : ''}>${p === 'keine' ? 'Keine' : PRIO[p][1]}</option>`).join('')}</select></label>
   <label>Kontakte <small class="muted">· Beteiligte des Vorgangs</small></label>${mehrfach('m-vks', kontaktOpt(), v.beteiligte.map(b => b.kontakt_id), 'Kontakt')}
   <div class="two"><label>Zuständig<input id="m-vz" value="${esc(v.zustaendig || '')}"></label><label>Nächster Schritt<input id="m-vn" value="${esc(v.naechster_schritt || '')}"></label></div><label>Beschreibung<textarea id="m-vd" rows="3">${esc(v.beschreibung)}</textarea></label>`, async () => {
    const bereiche = multiWert('m-vbs'); if (!bereiche.length) { toast('Bitte mindestens einen Bereich wählen.'); return false; }
    closeModal(); await act(() => api('akte/' + v.id, {titel: val('m-vt'), bereiche, prioritaet: val('m-vprio'), kontakte: multiWert('m-vks').map(Number), zustaendig: val('m-vz'), naechster_schritt: val('m-vn'), beschreibung: val('m-vd')}), 'Vorgang gespeichert.'); return false; });
}
// Erledigte Vorgänge verlassen die Liste „Vorgänge“ und stehen nur noch im Archiv.
const aktiv = () => D.cases.filter(c => c.status !== 'Erledigt');
// Auswahl aus allen bestehenden Vorgängen: laufende zuerst, erledigte (im Archiv) darunter
const vorgangOptionen = (cur, ohne) => {
  const opt = c => `<option value="${c.id}" ${String(cur) === String(c.id) ? 'selected' : ''}>${esc(c.titel)}</option>`;
  const fertig = D.cases.filter(c => c.status === 'Erledigt' && c.id !== ohne).sort((x, y) => cmp(x.titel, y.titel));
  return `<optgroup label="Laufende Vorgänge">${aktiv().filter(c => c.id !== ohne).sort((x, y) => cmp(x.titel, y.titel)).map(opt).join('')}</optgroup>`
    + (fertig.length ? `<optgroup label="Erledigte Vorgänge (Archiv)">${fertig.map(opt).join('')}</optgroup>` : '');
};
// Empfänger: erkannt oder von Hand; bei versendeten Schreiben der Kontakt
const empfaengerVon = d => d.empfaenger || (['ausgang', 'entwurf', 'nachweis'].includes(d.art) ? d.absender : null);
// Dateityp als kleines Symbol
const WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const TYP = m => m === 'application/pdf' ? ['pdf', 'PDF'] : m === 'message/rfc822' ? ['mail', 'MAIL'] : m === WORD ? ['word', 'WORD'] : /^image\//.test(m || '') ? ['bild', 'BILD'] : ['datei', 'DATEI'];
const TYP_NAME = {pdf: 'PDF-Dokument', mail: 'E-Mail', word: 'Word-Dokument', bild: 'Bild/Scan', datei: 'Datei'};
const typIcon = m => { const [k, l] = TYP(m); return `<span class="ftyp ftyp-${k}" title="${TYP_NAME[k]}">${l}</span>`; };
const typBadges = typen => Object.entries(typen || {}).map(([m, n]) => `${typIcon(m)}<span class="muted num" style="font-size:12px;margin:0 6px 0 2px">${n}</span>`).join('');
const dokMime = id => (D.akte?.dokumente || []).find(d => d.id === id)?.mime;
// Seitenansicht mit pdf.js: eine A4-Seite füllt die Fensterhöhe, ab zwei Seiten zwei nebeneinander
let pdfjsLaden = null;
function pdfjs() {
  if (!pdfjsLaden) pdfjsLaden = new Promise((ok, fehler) => { const s = document.createElement('script'); s.src = '/pdfjs/pdf.min.js';
    s.onload = () => { window.pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdfjs/pdf.worker.min.js'; ok(window.pdfjsLib); }; s.onerror = fehler; document.head.append(s); });
  return pdfjsLaden;
}
async function seitenAnzeigen(box, url, drehung) {
  try {
    const pdf = await (await pdfjs()).getDocument(url).promise, n = pdf.numPages;
    box.classList.toggle('zwei', n > 1); box.innerHTML = '';
    const hoehe = box.clientHeight - 32, breite = (n > 1 ? (box.clientWidth - 56) / 2 : box.clientWidth - 32), dpr = window.devicePixelRatio || 1;
    for (let i = 1; i <= n; i++) {
      if (!box.isConnected) return;
      const seite = await pdf.getPage(i), rot = (seite.rotate + (drehung || 0)) % 360, eins = seite.getViewport({scale: 1, rotation: rot});
      const massstab = Math.min(hoehe / eins.height, breite / eins.width), vp = seite.getViewport({scale: massstab * dpr, rotation: rot});
      const c = document.createElement('canvas'); c.width = vp.width; c.height = vp.height;
      c.style.width = vp.width / dpr + 'px'; c.style.height = vp.height / dpr + 'px'; c.title = `Seite ${i} von ${n}`; box.append(c);
      await seite.render({canvasContext: c.getContext('2d'), viewport: vp}).promise;
    }
  } catch (e) {
    box.classList.remove('zwei'); box.innerHTML = `<iframe src="${url}#view=Fit" title="Original" style="width:100%;height:100%;border:0;background:#fff"></iframe>`;
  }
}
// Originale passend verkleinert: Bilder als <img> (ganz sichtbar), PDFs mit „ganze Seite“
const alsBild = d => /^image\/(jpeg|png)$/.test(d.mime || '') || (d.mime === 'image/tiff' && !d.gedreht);
const originalHtml = (d, titel, voll) => d.mime === WORD
  ? `<div class="pvrot ${voll ? 'full' : ''}"><iframe class="pvframe" src="/api/documents/${d.id}/html" title="${esc(titel || d.titel || 'Word-Dokument')}"></iframe></div>`
  : alsBild(d)
  ? `<div class="pvimgwrap ${voll ? 'full' : ''}" data-rot="${d.drehung_manuell || 0}"><img class="pvimg" src="/api/documents/${d.id}/original" alt="${esc(titel || d.titel || 'Original')}"></div>`
  : `<div class="pvrot ${voll ? 'full' : ''}" data-rot="${d.drehung_manuell || 0}"><iframe class="pvframe" src="/api/documents/${d.id}/original#view=Fit&amp;navpanes=0" title="Original ${esc(titel || d.titel || '')}"></iframe></div>`;
// Drehung von Hand anzeigen: Bild bzw. PDF-Rahmen drehen und dabei vollständig einpassen
function drehungAnwenden(root = document) {
  for (const box of root.querySelectorAll('[data-rot]')) {
    const grad = +box.dataset.rot || 0, quer = grad % 180 !== 0, el = box.querySelector('img, iframe'); if (!el) continue;
    if (el.tagName === 'IMG') {
      el.style.transform = grad ? `rotate(${grad}deg)` : '';
      el.style.maxWidth = quer ? box.clientHeight + 'px' : ''; el.style.maxHeight = quer ? box.clientWidth + 'px' : '';
    } else {
      const w = box.clientWidth, h = box.clientHeight;
      Object.assign(el.style, quer ? {position: 'absolute', width: h + 'px', height: w + 'px', left: (w - h) / 2 + 'px', top: (h - w) / 2 + 'px', transform: `rotate(${grad}deg)`}
        : {position: '', width: '', height: '', left: '', top: '', transform: grad ? `rotate(${grad}deg)` : ''});
    }
  }
}
addEventListener('resize', () => drehungAnwenden());
function vHome() {
  const offen = D.fristen.filter(f => !f.erledigt_am);
  const ueber = offen.filter(f => tage(f.faellig_am) < 0), bald = offen.filter(f => tage(f.faellig_am) >= 0 && tage(f.faellig_am) <= 14);
  const wartet = D.cases.filter(c => c.status === 'Wartet auf Antwort' || c.status === 'Schreiben abgeschickt');
  return `<h1>Übersicht</h1>
  <div class="kpis"><a class="kpi ${ueber.length ? 'crit' : ''}" href="#fristen"><b class="num">${ueber.length}</b><span>Überfällig</span></a>
   <a class="kpi ${bald.length ? 'warn' : ''}" href="#fristen"><b class="num">${bald.length}</b><span>Fällig in 14 Tagen</span></a>
   <a class="kpi" href="#posteingang"><b class="num">${D.inbox.length}</b><span>Im Posteingang</span></a>
   <a class="kpi" href="#vorgaenge"><b class="num">${aktiv().length}</b><span>Laufende Vorgänge</span></a></div>
  <div class="grid2"><div class="panel"><h2>Fristen</h2>${fristList([...ueber, ...bald], false)}</div>
   <div class="stack"><div class="panel"><h2>Posteingang</h2><ul class="mini" style="margin-top:8px">${D.inbox.slice(0, 6).map(p => `<li><span>${esc(p.titel)}</span><span class="muted num">${dt(p.angelegt_am)}</span></li>`).join('') || '<li class="muted">Alles einsortiert.</li>'}</ul>${D.inbox.length ? '<div style="margin-top:10px"><a class="btn sm" href="#posteingang">Einsortieren</a></div>' : ''}</div>
   <div class="panel"><h2>Warten auf Antwort</h2><ul class="mini" style="margin-top:8px">${wartet.map(c => `<li><a href="#akte-${c.id}">${esc(c.titel)}</a><span class="muted">${esc(stLabel(c.status))}</span></li>`).join('') || '<li class="muted">Keine.</li>'}</ul></div></div></div>`;
}

// ---------- Posteingang ----------
function tileState(p) {
  if (/Wartet|läuft/.test(p.ocr_status)) return ['', 'Wird gelesen …'];
  if (/fehlgeschlagen|nicht verfügbar|Kein Text/.test(p.ocr_status)) return ['crit', 'Kein Text'];
  if (p.vorschlag.vorgaenge.length) return ['ok', 'Vorschlag bereit'];
  return ['warn', 'Zuordnen'];
}
// Kachel: Datum des Dokuments (aus dem Text, sonst Erstellungsdatum der Datei); nur ersatzweise das Importdatum
const kachelDatum = p => { const d = p.dokument_datum || p.vorschlag?.datum;
  return d ? `<span title="Dokumentdatum${p.vorschlag?.datum_quelle ? ' – ' + esc(p.vorschlag.datum_quelle) : ''}">${dt(d)}</span>` : `<span class="muted" title="Kein Datum im Dokument gefunden">importiert ${dt(p.angelegt_am)}</span>`; };
function tileHtml(p) {
  const [cls, lbl] = tileState(p);
  const lines = (p.seiten[0]?.text || '').split('\n').filter(Boolean).slice(0, 9);
  const text = lines.length ? `<div class="tdoc">${lines.map(l => `<span>${esc(l)}</span>`).join('')}</div>` : `<div class="tdoc tempty">${I('doc')}</div>`;
  const bereit = !/Wartet|läuft/.test(p.ocr_status || '');
  const prev = p.mime === 'message/rfc822' || !bereit ? text
    : `${text}<img class="thumb" src="/api/documents/${p.id}/vorschaubild?v=${encodeURIComponent(p.ocr_status + (p.seiten[0]?.drehung || 0))}" alt="" loading="lazy" onerror="this.remove()">`;
  const nr = S.kombi ? S.kombi.indexOf(p.id) + 1 : 0;
  return `<div class="tile ${S.ibSel === p.id && !S.kombi ? 'on' : ''} ${nr ? 'kombi-an' : ''} ${S.kombi && !kombinierbar(p) ? 'kombi-nein' : ''}" id="it-${p.id}" role="button" tabindex="0" data-act="ib-open" data-id="${p.id}" aria-pressed="${S.ibSel === p.id}" aria-label="${esc(p.titel)}">
   <span class="tprev">${prev}${nr ? `<span class="knr">${nr}</span>` : ''}<span class="tacts"><button class="tbtn" data-act="tile-kombi" data-id="${p.id}" title="Mit anderen Dokumenten zu einem PDF kombinieren" aria-label="${esc(p.titel)} kombinieren">${I('stapel')}</button><button class="tbtn" data-act="tile-view" data-id="${p.id}" title="Bildschirmfüllend ansehen" aria-label="${esc(p.titel)} ansehen">${I('lupe')}</button><button class="tbtn del" data-act="tile-del" data-id="${p.id}" title="Löschen (in den Papierkorb)" aria-label="${esc(p.titel)} löschen">${I('trash')}</button></span></span>
   <span class="tname" title="${esc(p.dateiname)}">${esc(p.titel)}</span>
   <span class="tmeta num">${groesse(p.groesse)} · ${kachelDatum(p)}</span><span class="pill ${cls} tstate">${lbl}</span></div>`;
}
const draft = {};  // Eingaben im Posteingang bis zum Zuordnen
function detailHtml(p) {
  const v = p.vorschlag, d = draft[p.id] || (draft[p.id] = {fristen: [], empfaenger: p.empfaenger || '', titel: p.titel, datum: v.datum || '', kontakt: v.kontakt ? String(v.kontakt.id) : (v.absender ? 'neu' : ''), vorgang: v.vorgaenge[0] ? String(v.vorgaenge[0].vorgang_id) : '', teil: ''});
  const titleSrc = p.titel_quelle === 'Manuell' ? 'manuell geändert' : p.titel_quelle === 'Dateiname' ? 'aus dem Dateinamen' : `erkannt aus: ${p.titel_quelle}${p.titel_seite ? ', Seite ' + p.titel_seite : ''}`;
  const pending = /Wartet|läuft/.test(p.ocr_status);
  if (!pending && !d.frInit) { d.fristen = [...(v.fristen || []).map(f => ({...f, an: true})), ...d.fristen]; d.frInit = true; }
  const neu = v.absender && !v.absender.kontakt;
  return `<div class="icard" id="ic-${p.id}"><div class="ibhead"><div style="min-width:0"><h3>${esc(p.dateiname)}</h3><span class="muted num" style="font-size:13px">${esc(p.mime.split('/')[1].toUpperCase())} · ${groesse(p.groesse)} · eingegangen ${dt(p.angelegt_am)} · ${esc(p.ocr_status)}</span></div>
   <span style="display:flex;gap:6px"><button class="btn sm" data-act="view" data-doc="${p.id}">${I('expand')}Original</button><button class="iconbtn" data-act="ib-del" data-id="${p.id}" title="Löschen" aria-label="${esc(p.dateiname)} löschen">${I('trash')}</button><button class="iconbtn" data-act="ib-close" title="Details schließen" aria-label="Details schließen">${I('minus')}</button></span></div>
   ${pending ? `<div class="notice info">${I('doc')}<p>Der Text wird gerade erkannt. Die Vorschläge erscheinen gleich.</p></div>` : ''}
   ${p.ocr_fehler ? `<div class="notice crit">${I('alert')}<p>${esc(p.ocr_status)}: ${esc(p.ocr_fehler)}</p></div>` : ''}
   <div class="ibsec ibsec-found"><h4>Erkannte Angaben</h4><div class="found2">
    <label class="wide">Titel <small>${esc(titleSrc)}</small><input data-ib="titel" data-id="${p.id}" value="${esc(d.titel)}" maxlength="160"></label>
    <label>Dokumentdatum <small>${v.datum_quelle ? 'aus: ' + esc(v.datum_quelle) : 'nicht erkannt'}</small><input type="date" data-ib="datum" data-id="${p.id}" value="${esc(d.datum)}"></label>
    <label>Absender <small>${v.absender ? 'aus: ' + esc(v.absender.quelle) : v.kontakt ? 'aus Erwähnung im Text' : 'nicht erkannt'}</small><select data-ib="kontakt" data-id="${p.id}"><option value="">– unbekannt –</option>
     ${neu ? `<option value="neu" ${d.kontakt === 'neu' ? 'selected' : ''}>Neu: ${esc(v.absender.name)}</option>` : ''}
     ${D.kontakte.map(k => `<option value="${k.id}" ${d.kontakt === String(k.id) ? 'selected' : ''}>${esc(k.kurzname || k.name)}</option>`).join('')}<option value="__neu">+ Neuer Kontakt …</option></select></label>
    <label>Empfänger <small>${p.empfaenger ? (D.empfaenger || []).includes(p.empfaenger) ? 'erkannt (zulässiger Empfänger)' : 'aus dem Anschriftenfeld' : 'nicht erkannt'}</small><select data-ib="empfaenger" data-id="${p.id}"><option value="">– unbekannt –</option>
     ${[...new Set([...(D.empfaenger || []), ...(p.empfaenger ? [p.empfaenger] : []), ...(d.empfaenger ? [d.empfaenger] : [])])].map(e => `<option value="${esc(e)}" ${d.empfaenger === e ? 'selected' : ''}>${esc(e)}</option>`).join('')}
     <option value="__neu">+ Neuer Empfänger …</option></select></label>
    ${v.referenz ? `<div class="refbox"><small>${esc(v.referenz.bezeichnung)}</small><b class="num">${esc(v.referenz.wert)}</b></div>` : ''}</div>
    ${neu ? `<p class="hint">„${esc(v.absender.name)}“ ist noch nicht im Adressbuch. Beim Zuordnen wird der Kontakt${v.absender.anschrift ? ' mit Anschrift' : ''} angelegt.</p>` : '<p class="hint">Vorschläge aus dem erkannten Text. Bitte prüfen und bei Bedarf ändern.</p>'}</div>
   ${p.seiten.length ? `<details class="ocrd ibsec ibsec-text"><summary>Erkannter Text · ${p.seiten.length} Seite(n)</summary><pre>${esc(p.seiten.map(s => `— Seite ${s.nummer} · ${s.methode === 'ocr' ? 'OCR' : 'Textschicht'} —\n${s.text}`).join('\n\n').slice(0, 8000))}</pre></details>` : ''}
   ${pending ? '' : `<div class="ibsec ibsec-found"><h4>Fristen</h4>
    ${d.fristen.length ? `<ul class="frlist">${d.fristen.map((f, i) => `<li><label class="chk"><input type="checkbox" data-fr="an" data-i="${i}" data-id="${p.id}" ${f.an ? 'checked' : ''} aria-label="Frist übernehmen"></label>
      <input class="inp" data-fr="titel" data-i="${i}" data-id="${p.id}" value="${esc(f.titel)}" aria-label="Titel der Frist"><input class="inp" type="date" data-fr="faellig_am" data-i="${i}" data-id="${p.id}" value="${esc(f.faellig_am)}" aria-label="Fällig am">
      <small class="muted">${f.zitat ? `${f.relativ ? 'berechnet aus' : 'aus'}: „${esc(f.zitat.length > 140 ? f.zitat.slice(0, 140) + ' …' : f.zitat)}“, S. ${f.seite}` : 'von Hand festgelegt'}</small></li>`).join('')}</ul>`
      : '<p class="hint" style="margin:0 0 6px">Im Text wurde keine Frist erkannt.</p>'}
    <button class="btn sm ghost" data-act="ib-fadd" data-id="${p.id}">${I('plus')}Frist von Hand</button>
    <p class="hint">Angehakte Fristen werden beim Zuordnen mit Fundstelle im Vorgang eingetragen.</p></div>`}
   <div class="ibsec ibsec-assign"><h4>Zuordnen</h4>
    ${v.vorgaenge.length ? `<div class="sugg"><span class="muted" style="font-size:13px">Gehört vermutlich zu</span>${v.vorgaenge.map(s => `<button class="btn sm out" data-act="ib-assign" data-id="${p.id}" data-v="${s.vorgang_id}">${esc(s.titel)}</button><span class="why">${esc(s.grund)}</span>`).join('')}</div>` : '<p class="hint" style="margin:0 0 6px">Kein passender Vorgang erkannt.</p>'}
    <div class="manual" style="margin-top:8px"><span class="muted" style="font-size:13px">${v.vorgaenge.length ? 'oder' : 'Vorgang'}</span><select id="mv-${p.id}" aria-label="Vorgang wählen">${vorgangOptionen(d.vorgang)}<option value="__new">+ Neuer Vorgang …</option></select>
     <button class="btn pri sm" data-act="ib-manual" data-id="${p.id}">Zuordnen</button></div>
    <div class="manual" style="margin-top:10px"><span class="muted" style="font-size:13px">oder</span><button class="btn sm" data-act="ib-archiv" data-id="${p.id}">${I('archive')}Ohne Vorgang ins Archiv</button></div></div></div>`;
}
function vInbox() {
  if (S.ibSel && !D.inbox.some(p => p.id === S.ibSel)) S.ibSel = null;
  const sel = D.inbox.find(p => p.id === S.ibSel);
  return `<div class="head" style="justify-content:space-between"><h1>Posteingang</h1><button class="btn" data-act="mail-get">${I('mail')}Aus Mail holen</button></div><p class="muted" style="margin:6px 0 16px">${D.inbox.length ? `${D.inbox.length} ${D.inbox.length === 1 ? 'Dokument wartet' : 'Dokumente warten'} auf Zuordnung. Ein Klick auf ein Dokument öffnet die Details.` : 'Alles einsortiert.'} Dateien können Sie auch auf das Fenster ziehen.</p>
  ${S.kombi ? `<div class="kombibar"><span>${I('stapel')}<b>Kombinieren:</b> Dokumente in der gewünschten Reihenfolge anklicken (PDFs und Bilder). <b class="num">${S.kombi.length}</b> ausgewählt.</span>
    <span style="display:flex;gap:8px"><button class="btn pri sm" data-act="kombi-los" ${S.kombi.length < 2 ? 'disabled' : ''}>Zu einem PDF kombinieren</button><button class="btn sm" data-act="kombi-ab">Abbrechen</button></span></div>` : ''}
  <div class="ibgrid ${sel && !S.kombi ? 'has-sel' : ''}" role="list">${D.inbox.map(p => tileHtml(p) + (p === sel ? `<section class="ibdetail" id="ibdetail" aria-label="Details">${detailHtml(p)}</section>` : '')).join('')}</div>`;
}
let followTimer = null;
function followInbox() {  // Solange Texterkennung läuft, Stand nachladen, ohne laufende Eingaben zu stören
  clearTimeout(followTimer);
  const pending = D.inbox.some(p => /Wartet|läuft/.test(p.ocr_status)) || (D.akte?.dokumente || []).some(d => /Wartet|läuft/.test(d.ocr_status));
  if (!pending && S.view === 'posteingang') {  // Neue Dateien aus dem Scan-Ordner erscheinen von selbst
    followTimer = setTimeout(async () => {
      try { const n = (await api('posteingang')).dokumente.length; if (n !== D.inbox.length && !$('#modalroot').innerHTML && !document.activeElement?.closest('.ibdetail')) { await render(); return; } } catch (e) { /* später erneut */ }
      followInbox();
    }, 5000);
    return;
  }
  if (!pending || !['posteingang', 'akte', 'uebersicht'].includes(S.view)) return;
  followTimer = setTimeout(() => {
    const busy = document.activeElement && document.activeElement.closest('.modal, .ibdetail');
    if (busy || $('#modalroot').innerHTML || !$('#viewer').hidden) { followInbox(); return; }
    render();
  }, 2500);
}
async function assign(id, vorgangId) {
  const p = D.inbox.find(x => x.id === id), d = draft[id] || {};
  const ablage = vorgangId === 'ablage';
  const body = ablage ? {ablage: true, titel: d.titel, datum: d.datum || null, empfaenger: d.empfaenger ?? null}
    : {vorgang_id: +vorgangId, titel: d.titel, datum: d.datum || null, teile: d.teil ? [+d.teil] : [],
       empfaenger: d.empfaenger ?? null, fristen: (d.fristen || []).filter(f => f.an && f.faellig_am && f.titel.trim()).map(f => ({titel: f.titel, faellig_am: f.faellig_am, seite: f.seite || null, zitat: f.zitat || null, art: f.zitat ? 'frist' : 'wiedervorlage'}))};
  if (d.kontakt === 'neu' && p.vorschlag.absender) body.neuer_absender = {name: p.vorschlag.absender.name, anschrift: p.vorschlag.absender.anschrift};
  else if (d.kontakt) body.kontakt_id = +d.kontakt;
  const r = await api(`posteingang/${id}/zuordnen`, body);
  delete draft[id]; S.ibSel = null;
  if (ablage) { toast('Ohne Vorgang ins Archiv gelegt.'); await render(); return; }
  const n = body.fristen.length, fertig = D.cases.find(c => c.id === +vorgangId)?.status === 'Erledigt';
  S.v = +vorgangId; S.entry = r.id; S.teil = 'all'; S.tab = 'chronik';
  toast(`Zugeordnet${n ? `, ${n} Frist${n === 1 ? '' : 'en'} eingetragen` : ''}${fertig ? '. Der Vorgang ist erledigt, das Dokument steht im Archiv' : ''}.`); location.hash = 'akte-' + vorgangId; await route();
}

// ---------- Vorgänge ----------
function sortTh(t, k, label) {
  const so = S['sort' + t], on = so.k === k;
  return `<th aria-sort="${on ? (so.d > 0 ? 'ascending' : 'descending') : 'none'}"><button class="thsort ${on ? 'on' : ''}" data-act="tsort" data-t="${t}" data-k="${k}">${label}<span class="arr" aria-hidden="true">${on ? (so.d > 0 ? '▲' : '▼') : '↕'}</span></button></th>`;
}
const cmp = (a, b) => String(a ?? '').localeCompare(String(b ?? ''), 'de', {numeric: true, sensitivity: 'base'});
// Filter: als Chips untereinander (Zeilen) oder als Ausklappmenüs in einer Zeile; Wahl wird gespeichert.
// zeilen: [[{lbl, act, aktiv, opt: [[id, label]], neu: [act, label]}], …], extra: z. B. Suchfeld
function filterBlock(zeilen, extra = '', klein = false) {
  const menue = (D.ui || {}).filteransicht === 'menue';
  const schalter = `<button class="iconbtn sm fumsch" data-act="filteransicht" title="${menue ? 'Filter untereinander als Schaltflächen zeigen' : 'Filter als Ausklappmenüs in einer Zeile zeigen'}" aria-label="Filterdarstellung wechseln">${menue ? '☷' : '▾'}</button>`;
  if (menue) {
    const sel = g => `<label class="fsel"><span class="lbl">${g.lbl}</span><select data-fsel="${g.act}">${g.opt.map(([id, l]) => `<option value="${esc(id)}" ${String(g.aktiv) === String(id) ? 'selected' : ''}>${esc(l)}</option>`).join('')}${g.neu ? `<option value="__neu" data-neu="${g.neu[0]}">${esc(g.neu[1])}</option>` : ''}</select></label>`;
    return `<div class="filters fmenue">${zeilen.flat().map(sel).join('')}${extra ? `<span style="flex:1"></span>${extra}` : ''}${schalter}</div>`;
  }
  return zeilen.map((zeile, i) => `<div class="filters" ${i ? 'style="margin-top:-6px"' : ''}>${zeile.map((g, j) => `${j ? '<span class="trenner"></span>' : ''}<span class="lbl">${g.lbl}</span>${g.opt.map(([id, l]) => `<button class="fchip ${String(g.aktiv) === String(id) ? 'on' : ''}" data-act="${g.act}" data-id="${esc(id)}" ${klein ? 'style="padding:3px 9px;font-size:12px"' : ''}>${l}</button>`).join('')}${g.neu ? `<button class="fchip" data-act="${g.neu[0]}" style="border-style:dashed">${esc(g.neu[1])}</button>` : ''}`).join('')}${i === zeilen.length - 1 ? `${extra ? `<span style="flex:1"></span>${extra}` : '<span style="flex:1"></span>'}${schalter}` : ''}</div>`).join('');
}
const PRIO = {'keine': [0, ''], 'hoch': [1, 'Hoch'], 'sehr hoch': [2, 'Sehr hoch']};
const prioPill = p => p && p !== 'keine' ? `<span class="prio prio-${p === 'hoch' ? 'hoch' : 'sehrhoch'}">${PRIO[p][1]}</span>` : '<span class="muted">–</span>';
function vList() {
  const bs = ['alle', ...new Set([...D.groups, ...aktiv().map(c => c.bereich)])];
  const erledigt = D.cases.length - aktiv().length;
  let list = aktiv().filter(c => (S.vb === 'alle' || (c.bereiche || [c.bereich]).includes(S.vb)) && (S.vs === 'alle' || c.status === S.vs));
  const key = {titel: c => c.titel, bereich: c => c.bereich, prio: c => -(PRIO[c.prioritaet || 'keine'] || [0])[0], status: c => ST_ORDER.indexOf(c.status), frist: c => c.naechste_frist || '9999', akt: c => c.angelegt_am}[S.sortV.k] || (c => c.titel);
  list.sort((a, b) => (typeof key(a) === 'number' ? key(a) - key(b) : cmp(key(a), key(b))) * S.sortV.d || cmp(a.titel, b.titel));
  // Gruppieren: ein Vorgang mit mehreren Bereichen bzw. Empfängern erscheint in jeder seiner Gruppen
  const gkey = {keine: () => [''], bereich: c => c.bereiche || [c.bereich], status: c => [stLabel(c.status)],
    prio: c => [PRIO[c.prioritaet || 'keine'][1] || 'Keine Priorität'], empfaenger: c => (c.empfaenger || []).length ? c.empfaenger : ['Empfänger unbekannt']}[S.vGroup || 'keine'];
  const groups = [];
  for (const c of list) for (const k of gkey(c)) { let g = groups.find(x => x.k === k); if (!g) groups.push(g = {k, items: []}); g.items.push(c); }
  if (S.vGroup === 'prio') groups.sort((x, y) => ['Sehr hoch', 'Hoch', 'Keine Priorität'].indexOf(x.k) - ['Sehr hoch', 'Hoch', 'Keine Priorität'].indexOf(y.k));
  else if (S.vGroup === 'status') groups.sort((x, y) => ST_ORDER.map(stLabel).indexOf(x.k) - ST_ORDER.map(stLabel).indexOf(y.k));
  else if (S.vGroup && S.vGroup !== 'keine') groups.sort((x, y) => cmp(x.k, y.k));
  const thead = `<thead><tr>${sortTh('V','titel','Vorgang')}${sortTh('V','prio','Priorität')}${sortTh('V','bereich','Bereich')}${sortTh('V','status','Status')}${sortTh('V','frist','Nächste Frist')}${sortTh('V','akt','Angelegt')}<th><span class="sr">Aktionen</span></th></tr></thead>`;
  const row = c => `<tr data-act="open-v" data-id="${c.id}"><td><b>${esc(c.titel)}</b><div class="muted" style="font-size:12.5px">${c.dokumente} Dokument${c.dokumente === 1 ? '' : 'e'}${c.dokumente ? ' · ' : ''}${typBadges(c.typen)}${(c.empfaenger || []).length ? ` · an ${esc(c.empfaenger.join(', '))}` : ''}</div></td>
   <td>${prioPill(c.prioritaet)}</td><td>${esc((c.bereiche || [c.bereich]).join(', '))}</td>
   <td><span class="st-${ST_KEY[c.status] || 'offen'}" style="display:flex;align-items:center;gap:6px;font-size:13px"><span class="dot"></span><span style="color:var(--fg)">${esc(stLabel(c.status))}</span></span></td>
   <td class="num">${c.naechste_frist ? `<span style="color:${tage(c.naechste_frist) < 0 ? 'var(--crit)' : tage(c.naechste_frist) <= 7 ? 'var(--warn)' : 'inherit'}">${dt(c.naechste_frist)}</span>` : '–'}</td><td class="num">${dt(c.angelegt_am)}</td>
   <td style="white-space:nowrap"><button class="iconbtn" data-act="v-edit" data-id="${c.id}" title="Vorgang bearbeiten" aria-label="${esc(c.titel)} bearbeiten">${I('draft')}</button><button class="iconbtn" data-act="v-del" data-id="${c.id}" title="Vorgang löschen" aria-label="${esc(c.titel)} löschen">${I('trash')}</button></td></tr>`;
  const tabelle = items => `<div class="tbl-wrap" style="margin-bottom:16px"><table>${thead}<tbody>${items.map(row).join('')}</tbody></table></div>`;
  return `<div class="head" style="justify-content:space-between"><h1>Vorgänge</h1><button class="btn pri" data-act="new-vorgang">${I('plus')}Neuer Vorgang</button></div>
  ${filterBlock([[{lbl: 'Gruppieren', act: 'vgroup', aktiv: S.vGroup || 'keine', opt: [['keine','Keine'],['bereich','Bereich'],['status','Status'],['prio','Priorität'],['empfaenger','Empfänger']]}],
    [{lbl: 'Bereich', act: 'vb', aktiv: S.vb, opt: bs.map(b => [b, b === 'alle' ? 'Alle' : b]), neu: ['b-add', '+ Bereich']}],
    [{lbl: 'Status', act: 'vs', aktiv: S.vs, opt: ['alle', ...ST_ORDER.filter(s => s !== 'Erledigt')].map(s => [s, s === 'alle' ? 'Alle' : stLabel(s)])}]])}
  ${!list.length ? '<div class="panel muted">Keine laufenden Vorgänge für diese Filter.</div>' : (S.vGroup || 'keine') === 'keine' ? tabelle(list)
    : groups.map(g => `<div class="agrp"><h3>${esc(g.k)}</h3><span class="muted num">${g.items.length}</span></div>${tabelle(g.items)}`).join('')}
  ${erledigt ? `<p class="muted" style="margin:10px 2px 0;font-size:13px">Erledigte Vorgänge werden hier nicht mehr geführt; ihre Dokumente stehen im <a href="#archiv">Archiv</a>.</p>` : ''}`;
}

// ---------- Vorgangsakte ----------
function paintAkte() { werkzeugeParken(); $('#view').innerHTML = vAkte(); mailTexte(); textPanes(); drehungAnwenden(); werkzeugeEinsetzen(); }
// Suche (als Symbol) und Import sitzen in der Kopfzeile der jeweiligen Ansicht, neben deren Knöpfen.
// Vor dem Neuaufbau der Ansicht werden sie geparkt, damit Eingaben und Zustand erhalten bleiben.
// Ansicht neu zeichnen, ohne Suche und Import (in der Kopfzeile) zu verlieren
function zeichne(ansicht) { werkzeugeParken(); $('#view').innerHTML = ansicht(); werkzeugeEinsetzen(); }
function werkzeugeParken() { const w = $('#werkzeuge'); if (w && w.parentElement !== $('#parkplatz')) $('#parkplatz').append(w); }
function werkzeugeEinsetzen() {
  const w = $('#werkzeuge'), kopf = document.querySelector('#view .head') || document.querySelector('#view h1');
  if (!w || !kopf) return;
  if (kopf.tagName === 'H1') { const h = document.createElement('div'); h.className = 'head'; kopf.replaceWith(h); h.append(kopf); return werkzeugeEinsetzen(); }
  const rechts = document.createElement('span'); rechts.className = 'kopfrechts';
  const letzter = kopf.children.length > 1 ? kopf.lastElementChild : null;
  if (letzter && letzter.tagName !== 'H1' && !letzter.matches('.crumb')) { letzter.replaceWith(rechts); rechts.append(w, letzter); } else { kopf.append(rechts); rechts.append(w); }
}
const teilName = id => D.akte.teilvorgaenge.find(t => t.id === id)?.name || '';
const kontaktName = id => { const k = D.kontakte.find(x => x.id === id); return k ? (k.kurzname || k.name) : ''; };
function visibleEntries() {
  const a = D.akte;
  return a.eintraege.filter(e => (S.teil === 'all' || e.teile.includes(S.teil) || !e.teile.length) && (S.ktype === 'alle' ||
    (S.ktype.startsWith('typ:') ? e.typ === S.ktype.slice(4) :
    (S.ktype === 'gespraech' ? ['telefonat','notiz','entscheidung'].includes(e.kind || e.art) : S.ktype === 'ausgang' ? ['ausgang','nachweis'].includes(e.art) : e.art === S.ktype))));
}
function vAkte() {
  const a = D.akte, multi = a.teilvorgaenge.length > 1;
  if (S.entry && !a.eintraege.some(e => e.id === S.entry)) S.entry = null;
  if (!S.entry) S.entry = (visibleEntries().find(e => e.dokument_id) || visibleEntries()[0])?.id || null;
  const head = `<div class="crumb"><a href="#vorgaenge">Vorgänge</a><span>/</span><span>${esc(a.bereich)}</span></div>
   <div class="head"><h1>${esc(a.titel)}</h1>${a.teilvorgaenge.length ? '' : statusPill(a.status)}<span style="flex:1"></span>
    <button class="btn sm" data-act="v-edit">Bearbeiten</button><button class="btn sm" data-act="teil-add">${I('plus')}Teilvorgang</button>
    <button class="btn sm" data-act="f-add">${I('cal')}Frist</button><button class="btn sm" data-act="doc-add">${I('plus')}Dokument</button><button class="btn sm" data-act="export">Exportieren</button><button class="iconbtn" data-act="v-del" data-id="${a.id}" title="Vorgang löschen" aria-label="Vorgang löschen">${I('trash')}</button></div>
   ${a.schlagwoerter.length ? `<div class="refs" style="margin-top:8px">${a.schlagwoerter.map(t => `<span class="pill grey"># ${esc(t)}</span>`).join('')}</div>` : ''}
   <div class="refs">${a.referenzen.map(r => `<span class="chip"><em>${esc(r.bezeichnung)}</em> <span class="num">${esc(r.wert)}</span>${r.kontakt_id ? ` <em>· ${esc(kontaktName(r.kontakt_id))}</em>` : ''}</span>`).join('')}
    ${a.beteiligte.filter(b => !a.referenzen.some(r => r.kontakt_id === b.kontakt_id)).map(b => `<button class="chip" data-act="contact" data-id="${b.kontakt_id}">${esc(b.kurzname || b.name)}${b.rolle ? ` <em>· ${esc(b.rolle)}</em>` : ''}</button>`).join('')}
</div>
   <div class="tabs" role="tablist">${[['chronik','Chronik'],['dokumente','Dokumente',a.dokumente.length],['beteiligte','Beteiligte',a.beteiligte.length],['fristen','Fristen',a.fristen.filter(f => !f.erledigt_am).length]].map(([id, l, n]) => `<button role="tab" data-act="tab" data-id="${id}" class="${S.tab === id ? 'on' : ''}" aria-selected="${S.tab === id}">${l}${n != null ? `<span class="n num">${n}</span>` : ''}</button>`).join('')}</div>`;
  let body = '';
  if (S.tab === 'chronik') body = `<div class="akte"><div class="l">${teilSwitch()}${fristCards()}${chronik()}</div><div class="r"><div class="sticky">${preview()}</div></div></div>`;
  if (S.tab === 'dokumente') body = docTable();
  if (S.tab === 'beteiligte') body = beteiligteTab();
  if (S.tab === 'fristen') body = `<div class="filters" style="margin:18px 0 12px"><button class="btn" data-act="f-add">${I('plus')}Frist oder Wiedervorlage</button></div><div class="panel">${fristList(a.fristen.map(f => ({...f, vorgang: a.titel, teilvorgang: teilName(f.teilvorgang_id)})), true)}</div>`;
  return head + body;
}
function teilSwitch() {
  const a = D.akte;
  if (!a.teilvorgaenge.length) return `<div class="teilbar"><span>Status <select data-change="v-status" aria-label="Status">${statusOptions(a.status)}</select></span>${a.zustaendig ? `<span>Zuständig: <strong>${esc(a.zustaendig)}</strong></span>` : ''}${a.naechster_schritt ? `<span>Nächster Schritt: <strong>${esc(a.naechster_schritt)}</strong></span>` : ''}</div>`;
  const btns = [`<button data-act="teil" data-id="all" class="${S.teil === 'all' ? 'on' : ''}"><b>Alle</b><small>${a.teilvorgaenge.length} Teilvorgänge</small></button>`,
    ...a.teilvorgaenge.map(t => `<button data-act="teil" data-id="${t.id}" class="${S.teil === t.id ? 'on' : ''}"><b>${esc(t.name)}</b><small class="st-${ST_KEY[t.status] || 'offen'}"><span class="dot"></span>${esc(stLabel(t.status))}</small></button>`)].join('');
  const t = a.teilvorgaenge.find(x => x.id === S.teil);
  const bar = t ? `<div class="teilbar"><span>Status <select data-change="t-status" data-id="${t.id}" aria-label="Status ${esc(t.name)}">${statusOptions(t.status)}</select></span><span>Zuständig: <strong>${esc(t.zustaendig || '–')}</strong></span><span>Nächster Schritt: <strong>${esc(t.naechster_schritt || '–')}</strong></span><button class="linkbtn" data-act="teil-edit" data-id="${t.id}">Bearbeiten</button></div>` : '';
  return `<div class="stack" style="gap:10px"><div class="seg" role="group" aria-label="Teilvorgang">${btns}</div>${bar}</div>`;
}
function fristCards() {
  const a = D.akte;
  const open = a.fristen.filter(f => !f.erledigt_am && (S.teil === 'all' || f.teilvorgang_id === S.teil || !f.teilvorgang_id)).sort((x, y) => x.faellig_am.localeCompare(y.faellig_am));
  if (!open.length) return '';
  const show = [open.find(f => f.art === 'frist'), open.find(f => f.art !== 'frist')].filter(Boolean).sort((x, y) => x.faellig_am.localeCompare(y.faellig_am));
  return `<div class="fcards">${show.map(f => `<div class="fcard ${f.art}"><span class="ic">${I(f.art === 'frist' ? 'para' : f.art === 'aufgabe' ? 'check' : 'cal')}</span>
   <div><b>${FK[f.art]} · <span class="num">${dt(f.faellig_am)}</span> <span class="muted" style="font-weight:400">(${relTage(f.faellig_am)})</span></b>${esc(f.titel)}
   <span class="q">${f.verlauf.length ? `Ursprünglich ${dt(f.verlauf[0].faellig_alt)} · ` : ''}${f.quelle_zitat || f.quelle_dokument_id ? `Quelle: ${f.quelle_dokument_id ? `<button class="linkbtn" data-act="quelle" data-doc="${f.quelle_dokument_id}">Dokument${f.quelle_seite ? ', S. ' + f.quelle_seite : ''}</button> ` : ''}${f.quelle_zitat ? '„' + esc(f.quelle_zitat) + '“' : ''}` : 'Selbst gesetzt'}${f.zustaendig ? ' · Zuständig: ' + esc(f.zustaendig) : ''}</span></div>
   <div class="acts"><button class="btn sm" data-act="f-done" data-id="${f.id}">Erledigt</button><button class="btn sm" data-act="f-move" data-id="${f.id}">Verschieben</button><button class="btn sm" data-act="f-zust" data-id="${f.id}">Zuständig</button></div></div>`).join('')}
   ${open.length > show.length ? `<button class="linkbtn" data-act="tab" data-id="fristen">+${open.length - show.length} weitere anzeigen</button>` : ''}</div>`;
}
function chronik() {
  const list = visibleEntries();
  let lastM = '';
  const rows = list.map(e => {
    const m = e.ereignis_datum.slice(0, 7); let mh = '';
    if (m !== lastM) { lastM = m; mh = `<li class="month">${MON[+m.slice(5) - 1]} ${m.slice(0, 4)}</li>`; }
    const k = e.typ ? [e.typ, KIND[e.art][1]] : KIND[e.art], badges = [];
    if (e.art === 'entwurf') badges.push(e.versendet_als ? '<span class="pill grey">Entwurf · versendet</span>' : '<span class="pill warn">Entwurf · nicht versendet</span>');
    if (e.versand) badges.push(`<span class="pill ok">${esc(e.versand.art)}</span>`);
    if (e.art === 'fehlt') badges.push('<span class="pill crit">Original fehlt</span>');
    if (e.nacherfasst) badges.push(`<span class="pill grey">nacherfasst ${dShort(e.erfasst_am.slice(0, 10))}</span>`);
    if (e.art === 'chat') badges.push(e.geprueft ? '<span class="pill ok">geprüft</span>' : '<span class="pill warn">ungeprüft</span>');
    const chips = D.akte.teilvorgaenge.length > 1 ? (S.teil === 'all' ? e.teile.map(t => `<span class="pill grey">${esc(teilName(t))}</span>`).join('')
      : e.teile.filter(t => t !== S.teil).map(t => `<button class="chip" data-act="teil" data-id="${t}">auch in ${esc(teilName(t))}</button>`).join('')) : '';
    const acts = e.art === 'entwurf' && !e.versendet_als ? `<button class="btn sm out" data-act="versand" data-id="${e.id}">${I('out')}Versand erfassen</button>` : '';
    const wer = e.kontakt_id ? ` · ${e.richtung || ''} ${esc(kontaktName(e.kontakt_id))}` : '';
    return mh + `<li class="ent k-${e.art} ${S.entry === e.id ? 'sel' : ''}"><span class="ico" title="${k[0]}">${I(k[1])}</span>
     <div class="card" data-act="entry" data-id="${e.id}" tabindex="0" role="button" aria-pressed="${S.entry === e.id}">
      <div class="row1"><span class="date num">${dt(e.ereignis_datum)}</span>${e.dokument_id ? typIcon(dokMime(e.dokument_id)) : ''}<span class="ttl">${esc(e.titel)}</span>${e.dokument_id ? `<span class="rowacts"><button class="iconbtn sm" data-act="doc-move" data-doc="${e.dokument_id}" title="In anderen Vorgang verschieben" aria-label="Dokument verschieben">${I('move')}</button><button class="iconbtn sm" data-act="doc-remove" data-doc="${e.dokument_id}" title="Aus diesem Vorgang löschen" aria-label="Dokument löschen">${I('trash')}</button></span>` : ''}</div>
      <div class="row2"><span>${k[0]}${wer}</span>${badges.join('')}</div>${chips || acts ? `<div class="row3">${chips}${acts}</div>` : ''}</div></li>`;
  }).join('');
  const types = [['alle','Alle Typen'],['eingang','Eingang'],['ausgang','Versendet'],['entwurf','Entwürfe'],['gespraech','Telefonate & Notizen'],['chat','Chat-Notizen'], ...[...new Set([...(D.arten || []), ...D.akte.eintraege.map(e => e.typ).filter(Boolean)])].map(t => ['typ:' + t, t])];
  return `<div class="stack" style="gap:6px"><div class="chron-h"><h2>Chronik</h2><span style="display:flex;gap:6px"><button class="btn out sm" data-act="claude" title="Den ganzen Vorgang mit Claude besprechen">${I('ki')}Claude</button><button class="btn out sm" data-act="compose">${I('draft')}Brief</button><button class="btn out sm" data-act="entry-add">${I('plus')}Eintrag</button><button class="btn out sm" data-act="ref-add">${I('plus')}Referenz</button></span></div>
   ${filterBlock([[{lbl: 'Typ', act: 'ktype', aktiv: S.ktype, opt: types}]], '', true)}
   <ul class="chron">${rows || '<li class="muted" style="padding:10px 0">Noch keine Einträge. Dokumente aus dem Posteingang zuordnen oder einen Eintrag anlegen.</li>'}</ul></div>`;
}
function preview() {
  const a = D.akte, e = a.eintraege.find(x => x.id === S.entry);
  if (!e) return '<p class="muted">Eintrag auswählen, um ihn hier zu sehen.</p>';
  const knoepfe = [];
  if (e.art === 'eingang') knoepfe.push(`<button class="btn sm pri" data-act="compose" data-bezug="${e.id}">${I('draft')}Antwort verfassen</button>`);
  if (e.art === 'entwurf' && !e.versendet_als) knoepfe.push(`<button class="btn sm" data-act="compose" data-edit="${e.id}">${I('draft')}Brief bearbeiten</button>`);
  if (e.brief) knoepfe.push(`<a class="btn sm" href="/api/eintraege/${e.id}/brief" target="_blank" rel="noopener">Drucken oder PDF</a>`);
  knoepfe.push(`<button class="btn sm ghost" data-act="entry-edit" data-id="${e.id}">Bearbeiten</button>`);
  const kopf = `<div class="pv-h"><div><h2>${esc(e.titel)}</h2><span class="muted">${esc(e.typ || KIND[e.art][0])}${e.kontakt_id ? ` · ${e.richtung || ''} ${esc(kontaktName(e.kontakt_id))}` : ''} · ${dt(e.ereignis_datum)}</span></div>
   <span style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">${knoepfe.join('')}</span></div>`;
  const vers = e.versand ? `<dl class="meta"><div class="wide"><dt>Versand · ${esc(e.versand.art)} am ${dt(e.versand.datum)}${e.versand.sendungsnummer ? ' · ' + esc(e.versand.sendungsnummer) : ''}</dt><dd class="addr">${esc(e.versand.empfaenger)}</dd>${e.versand.anschrift_geaendert ? `<div class="notice warn" style="margin:8px 0 0">${I('alert')}<p>Die Anschrift hat sich inzwischen geändert. Neue Schreiben gehen an die aktuelle Anschrift aus dem Adressbuch.</p></div>` : ''}</div></dl>` : '';
  if (e.brief) return kopf + vers + `<div class="frame" style="margin-top:12px"><iframe class="pvframe" src="/api/eintraege/${e.id}/brief" title="Brief ${esc(e.titel)}"></iframe></div>`;
  const text = e.text ? `<div class="notecard" style="margin-top:12px"><blockquote style="white-space:pre-line;margin:0">${esc(e.text)}</blockquote></div>` : '';
  if (!e.dokument_id) return kopf + vers + (text || `<p class="muted">${e.art === 'fehlt' ? 'Das Original fehlt noch in der Akte.' : 'Kein Dokument zu diesem Eintrag.'}</p>`);
  const d = a.dokumente.find(x => x.id === e.dokument_id) || {};
  const mail = d.mime === 'message/rfc822', modus = mail ? 'text' : S.pvMode;
  const info = S.pvInfo ? `<dl class="meta pvinfo">
    <div><dt>Titel</dt><dd>${esc(d.titel)} <button class="linkbtn" data-act="doc-rename" data-doc="${d.id}">ändern</button></dd></div>
    <div><dt>Datei</dt><dd>${esc(d.dateiname || '')}</dd></div>
    <div><dt>Titelquelle</dt><dd>${esc(d.titel_quelle || '')}${d.titel_seite ? ', Seite ' + d.titel_seite : ''}</dd></div>
    <div><dt>Text</dt><dd>${esc(d.ocr_status || '')}</dd></div><div><dt>Vorgänge</dt><dd>${d.vorgaenge || 1}</dd></div>
    ${d.gedreht ? `<div><dt>Lage</dt><dd>automatisch aufrecht gedreht · <a class="linkbtn" href="/api/documents/${d.id}/original?fassung=original" target="_blank" rel="noopener">Original ungedreht</a></dd></div>` : ''}</dl>` : '';
  return kopf + vers + `<div class="frame" style="margin-top:8px"><div class="tool pvtool">
    ${mail ? '<span class="muted" style="font-size:13px">E-Mail</span>' : `<span class="seg" role="group" aria-label="Ansicht"><button class="${modus === 'original' ? 'on' : ''}" data-act="pv-mode" data-id="original">Original</button><button class="${modus === 'text' ? 'on' : ''}" data-act="pv-mode" data-id="text">Text</button></span>`}
    <span class="pvname" title="${esc(d.dateiname || '')}">${esc(d.dateiname || '')}${d.gedreht ? ` <span class="pill grey" title="Automatisch aufrecht gedreht. Das Original bleibt unverändert.">gedreht</span>` : ''}</span>
    <span class="sp"></span>
    <button class="btn sm" data-act="claude" data-doc="${d.id}" data-entry="${e.id}" title="Schreiben mit Claude analysieren oder eine Antwort entwerfen lassen">${I('ki')}Claude</button>
    <button class="iconbtn ${S.pvInfo ? 'on' : ''}" data-act="pv-info" title="Dokumentdetails" aria-label="Dokumentdetails" aria-pressed="${!!S.pvInfo}">${I('info')}</button>
    ${mail ? '' : `<button class="iconbtn" data-act="ocr-retry" data-doc="${d.id}" title="Text neu erkennen" aria-label="Text neu erkennen">${I('refresh')}</button>`}
    ${mail ? '' : `<button class="iconbtn" data-act="drehen" data-grad="-90" data-doc="${d.id}" title="90° nach links drehen" aria-label="90 Grad nach links drehen">${I('rotl')}</button><button class="iconbtn" data-act="drehen" data-grad="90" data-doc="${d.id}" title="90° nach rechts drehen" aria-label="90 Grad nach rechts drehen">${I('rotr')}</button>`}
    <button class="iconbtn" data-act="doc-move" data-doc="${d.id}" title="In anderen Vorgang verschieben" aria-label="In anderen Vorgang verschieben">${I('move')}</button>
    <button class="iconbtn" data-act="doc-remove" data-doc="${d.id}" title="Aus diesem Vorgang löschen" aria-label="Aus diesem Vorgang löschen">${I('trash')}</button>
    <button class="iconbtn" data-act="view" data-doc="${d.id}" title="Groß öffnen" aria-label="Groß öffnen">${I('expand')}</button></div>${info}
    ${modus === 'text' ? `<div class="textpane" data-text="${d.id}" data-entry="${e.id}">Wird geladen …</div>` : originalHtml(d)}</div>
   ${modus === 'text' ? '<p class="muted" style="font-size:12.5px;margin:8px 2px 0">Text markieren, um ihn als Frist, Aktenzeichen, Dokumentdatum oder Notiz mit Fundstelle zu übernehmen.</p>' : ''}` + text;
}

// ---------- Text & Fundstellen ----------
const DATUM_RE = /\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b/;
const isoAus = s => { const m = s.match(DATUM_RE); return m ? `${m[3]}-${pad(m[2])}-${pad(m[1])}` : null; };
function fundstellen(seiten) {
  const items = [], seen = new Set();
  for (const s of seiten) for (const raw of s.text.split('\n')) {
    const z = raw.replace(/\s+/g, ' ').trim(); if (!z) continue;
    if (DATUM_RE.test(z) && !seen.has('d' + z)) { seen.add('d' + z); items.push({k: 'frist', lbl: /\b(bis|frist|spätestens|fällig|zahlbar)\b/i.test(z) ? 'Frist?' : 'Datum', t: z, s: s.nummer}); }
    for (const m of z.matchAll(/(aktenzeichen|az\.|ihr zeichen|schaden-?\s?(?:nummer|nr\.?)|kunden-?\s?(?:nummer|nr\.?)|rechnungs-?\s?(?:nummer|nr\.?)|steuer-?\s?(?:nummer|nr\.?)|vertrags-?\s?(?:nummer|nr\.?)|HR[AB])\s*[:.]?\s*([A-Z0-9][A-Z0-9/.\-]{2,24})/gi))
      if (/\d/.test(m[2]) && !seen.has('r' + m[2])) { seen.add('r' + m[2]); items.push({k: 'ref', lbl: m[1], t: m[2].replace(/[.\-]$/, ''), s: s.nummer}); }
    if (/\d{1,3}(?:\.\d{3})*,\d{2}\s?(€|EUR)/.test(z) && !seen.has('b' + z)) { seen.add('b' + z); items.push({k: 'notiz', lbl: 'Betrag', t: z, s: s.nummer}); }
  }
  return items.sort((x, y) => (y.lbl === 'Frist?') - (x.lbl === 'Frist?')).slice(0, 16);
}
async function textPanes() {
  for (const box of document.querySelectorAll('.textpane[data-text]')) {
    const doc = +box.dataset.text, entry = +box.dataset.entry; box.removeAttribute('data-text');
    try {
      const seiten = (await api(`documents/${doc}/pages`)).pages;
      const erkannt = seiten.length ? (await api(`dokumente/${doc}/fristen`).catch(() => ({fristen: []}))).fristen : [];
      if (!seiten.length) { box.innerHTML = '<p class="muted">Für dieses Dokument liegt kein Text vor.</p>'; continue; }
      const f = fundstellen(seiten).filter(x => x.lbl !== 'Frist?');
      box.innerHTML = (erkannt.length ? `<div class="fund" style="border-top:0;padding-top:0;margin-bottom:14px"><h4>Erkannte Fristen</h4><ul class="mini">${erkannt.map(x => `<li><span style="min-width:0;flex:1"><b class="num">${dt(x.faellig_am)}</b> · ${esc(x.titel)} <span class="muted" style="font-size:12px">· ${x.relativ ? 'berechnet aus' : 'aus'} „${esc(x.zitat.length > 110 ? x.zitat.slice(0, 110) + ' …' : x.zitat)}“ · S. ${x.seite}</span></span>
           <button class="btn sm pri" data-act="take" data-k="frist" data-t="${esc(x.zitat)}" data-datum="${x.faellig_am}" data-titel="${esc(x.titel)}" data-s="${x.seite}" data-doc="${doc}" data-entry="${entry}">Als Frist übernehmen</button></li>`).join('')}</ul></div>` : '') + seiten.map(s => `<div class="tseite" data-seite="${s.nummer}" data-doc="${doc}" data-entry="${entry}"><small class="muted">Seite ${s.nummer} · ${s.methode === 'ocr' ? 'Texterkennung' : s.methode === 'mail' ? 'E-Mail' : 'Textschicht'}</small><div class="ttext">${esc(s.text)}</div></div>`).join('')
        + (f.length ? `<div class="fund"><h4>Fundstellen</h4><ul class="mini">${f.map(x => `<li><span style="min-width:0;flex:1"><span class="pill grey" style="font-size:11.5px;padding:0 6px">${esc(x.lbl)}</span> ${esc(x.t.length > 110 ? x.t.slice(0, 110) + ' …' : x.t)} <span class="muted" style="font-size:12px">· S. ${x.s}</span></span>
           <span style="display:flex;gap:6px">${x.k !== 'notiz' ? `<button class="btn sm" data-act="take" data-k="${x.k}" data-t="${esc(x.t)}" data-s="${x.s}" data-doc="${doc}" data-entry="${entry}">${x.k === 'frist' ? 'Als Frist' : 'Als Aktenzeichen'}</button>` : ''}<button class="btn sm ghost" data-act="take" data-k="notiz" data-t="${esc(x.t)}" data-s="${x.s}" data-doc="${doc}" data-entry="${entry}">Als Notiz</button></span></li>`).join('')}</ul></div>` : '');
    } catch (err) { box.textContent = err.message; }
  }
}
let sel = null;
function zeigeAuswahl() {
  const s = getSelection(), pop = $('#selpop');
  const node = s && !s.isCollapsed && s.anchorNode ? (s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement) : null;
  const seite = node && node.closest('.tseite'), text = s ? s.toString().replace(/\s+/g, ' ').trim() : '';
  if (!seite || text.length < 2 || text.length > 300) { pop.hidden = true; return; }
  sel = {text, doc: +seite.dataset.doc, seite: +seite.dataset.seite, entry: +seite.dataset.entry};
  const r = s.getRangeAt(0).getBoundingClientRect(); pop.hidden = false;
  pop.style.left = Math.max(8, Math.min(innerWidth - pop.offsetWidth - 8, r.left + r.width / 2 - pop.offsetWidth / 2)) + 'px';
  pop.style.top = (r.bottom + 8 + pop.offsetHeight > innerHeight ? r.top - pop.offsetHeight - 8 : r.bottom + 8) + 'px';
}
document.addEventListener('mouseup', () => setTimeout(zeigeAuswahl, 10));
function uebernehmen(art, s) {
  $('#selpop').hidden = true; getSelection()?.removeAllRanges();
  const a = D.akte, e = a.eintraege.find(x => x.id === s.entry), quelle = `„${s.text}“, ${e ? e.titel : 'Dokument'}, S. ${s.seite}`;
  if (art === 'frist') {
    const iso = s.datum || isoAus(s.text) || plusTage(isoHeute(), 14);
    modal('Frist übernehmen', `<label>Titel<input id="m-ft" value="${esc(s.titel ? `${s.titel} (${e ? e.titel : 'Dokument'})` : 'Frist aus ' + (e ? e.titel : 'Dokument'))}"></label>
     <div class="two"><label>Art<select id="m-fa"><option value="frist">Verbindliche Frist</option><option value="wiedervorlage">Wiedervorlage</option><option value="aufgabe">Aufgabe</option></select></label><label>Fällig am<input id="m-ff" type="date" value="${iso}"></label></div>
     <div class="two">${teilSelect('m-fteil', e && e.teile[0], true)}<label>Zuständig<input id="m-fz" value="Ich"></label></div>
     <label>Fundstelle (wird gespeichert)</label><div class="src">${esc(quelle)}</div>${s.datum || isoAus(s.text) ? '' : '<p class="muted" style="margin:0;font-size:13px">In der Markierung steht kein Datum. Bitte das Fälligkeitsdatum prüfen.</p>'}`, async () => {
      await act(() => api(`akte/${a.id}/fristen`, {art: val('m-fa'), titel: val('m-ft'), faellig_am: val('m-ff'), zustaendig: val('m-fz'), teilvorgang_id: val('m-fteil') ? +val('m-fteil') : null,
        quelle_dokument_id: s.doc, quelle_seite: s.seite, quelle_zitat: s.text.slice(0, 480)}), 'Frist mit Fundstelle eingetragen.');
    }, 'Eintragen');
  } else if (art === 'ref') {
    modal('Aktenzeichen übernehmen', `<div class="two"><label>Bezeichnung<input id="m-rl" list="m-rll" value="Aktenzeichen"><datalist id="m-rll"><option value="Aktenzeichen"><option value="Schaden-Nr."><option value="Kundennr."><option value="Steuer-Nr."><option value="Vertrags-Nr."><option value="Rechnung"></datalist></label><label>Nummer<input id="m-rv" value="${esc(s.text)}"></label></div>
     <label>Geführt von<select id="m-rk"><option value="">–</option>${a.beteiligte.map(b => `<option value="${b.kontakt_id}" ${e && e.kontakt_id === b.kontakt_id ? 'selected' : ''}>${esc(b.kurzname || b.name)}</option>`).join('')}</select></label>`, async () => {
      await act(() => api(`akte/${a.id}/referenzen`, {bezeichnung: val('m-rl'), wert: val('m-rv'), kontakt_id: val('m-rk') ? +val('m-rk') : null}), 'Referenz übernommen.');
    }, 'Übernehmen');
  } else if (art === 'datum') {
    const iso = isoAus(s.text); if (!iso || !e) { toast('In der Markierung steht kein Datum.'); return; }
    act(() => api('eintraege/' + e.id, {datum: iso}), `Datum auf ${dt(iso)} gesetzt.`);
  } else {
    act(() => api(`akte/${a.id}/eintraege`, {art: 'notiz', titel: 'Notiz zu ' + (e ? e.titel : 'Dokument'), text: quelle, bezug_id: e ? e.id : null, teile: e ? e.teile : []}), 'Notiz mit Zitat angelegt.');
  }
}

// ---------- Briefe ----------
const VORLAGEN = {
  stellungnahme: ['Stellungnahme', 'Stellungnahme zu Ihrem Schreiben vom {bezug}', '{anrede}\n\nzu Ihrem Schreiben vom {bezug} nehme ich wie folgt Stellung:\n\n[Ihre Stellungnahme]\n\nIch bitte um Ihre Rückmeldung bis zum {frist2}.\n\nMit freundlichen Grüßen\n{name}'],
  verlaengerung: ['Bitte um Fristverlängerung', 'Bitte um Fristverlängerung – Ihr Schreiben vom {bezug}', '{anrede}\n\nfür meine Antwort auf Ihr Schreiben vom {bezug} bitte ich um Verlängerung der Frist bis zum {frist4}. Grund: [Grund angeben].\n\nBitte bestätigen Sie mir die Verlängerung kurz.\n\nMit freundlichen Grüßen\n{name}'],
  erinnerung: ['Erinnerung', 'Erinnerung: mein Schreiben vom {letzter}', '{anrede}\n\nauf mein Schreiben vom {letzter} habe ich bisher keine Antwort erhalten. Ich bitte Sie, mir bis zum {frist2} zu antworten.\n\nMit freundlichen Grüßen\n{name}'],
  eingang: ['Bitte um Eingangsbestätigung', 'Bitte um Eingangsbestätigung', '{anrede}\n\nbitte bestätigen Sie mir den Eingang meines Schreibens vom {letzter}.\n\nMit freundlichen Grüßen\n{name}'],
  leer: ['Freies Schreiben', '', '{anrede}\n\n\n\nMit freundlichen Grüßen\n{name}']};
const anredeFuer = person => { const m = (person || '').match(/^(Frau|Herr)\s+(?:Dr\.\s+)?(?:[A-ZÄÖÜ]\.\s+)?(.+)$/); return m ? `Sehr geehrte${m[1] === 'Herr' ? 'r' : ''} ${m[1]} ${m[2]},` : 'Sehr geehrte Damen und Herren,'; };
const flachText = t => String(t || '').toLowerCase().replace(/[\s\-_.–/]+/g, '');
async function compose(bezugId, editId, vorschlag) {
  const a = D.akte; if (D.eigene === undefined || D.eigene === '') D.eigene = (await api('einstellungen')).eigene_angaben;
  const edit = editId ? a.eintraege.find(e => e.id === editId) : null, bezug = bezugId ? a.eintraege.find(e => e.id === bezugId) : (edit && edit.bezug_id ? a.eintraege.find(e => e.id === edit.bezug_id) : null);
  if (!D.kontakte.length) D.kontakte = (await api('kontakte')).kontakte;
  // Empfänger: Kontakt des Bezugsschreibens, sonst Beteiligte, sonst Absender des letzten Eingangs
  const letzterEingang = [...a.eintraege].filter(e => e.art === 'eingang' && e.kontakt_id).sort((x, y) => y.ereignis_datum.localeCompare(x.ereignis_datum))[0];
  let kId = (edit || bezug || {}).kontakt_id || (a.beteiligte[0] || {}).kontakt_id || (letzterEingang || {}).kontakt_id || null;
  const zieleFuer = k => {
    if (!k) return [];
    const mitName = (zeilen, person) => { const z = zeilen.split('\n').filter(Boolean); if (!flachText(z[0]).includes(flachText(k.name).slice(0, 8))) z.unshift(k.name);
      if (person && !zeilen.includes(person)) z.splice(1, 0, 'z. Hd. ' + person); return z.join('\n'); };
    const liste = k.abteilungen.flatMap(ab => [...ab.anschriften.filter(r => !r.gueltig_bis).map(r => ({k: 'a' + r.id, text: mitName(r.zeilen, ab.ansprechpartner), person: ab.ansprechpartner})),
      ...(ab.email ? [{k: 'm' + ab.id, text: `${k.name}${ab.ansprechpartner ? '\nz. Hd. ' + ab.ansprechpartner : ''}\n${ab.email}`, person: ab.ansprechpartner}] : [])]);
    return liste.length ? liste : [{k: 'n', text: k.name + (k.abteilungen[0]?.ansprechpartner ? '\nz. Hd. ' + k.abteilungen[0].ansprechpartner : ''), person: k.abteilungen[0]?.ansprechpartner}];
  };
  let k = D.kontakte.find(x => x.id === kId), ziele = zieleFuer(k);
  const refFuer = id => a.referenzen.find(r => r.kontakt_id === id) || a.referenzen[0];
  const ref = refFuer(kId);
  const beteiligt = new Set(a.beteiligte.map(x => x.kontakt_id));
  const kontaktOptionen = [...D.kontakte].sort((x, y) => (beteiligt.has(y.id) - beteiligt.has(x.id)) || cmp(x.name, y.name))
    .map(x => `<option value="${x.id}" ${x.id === kId ? 'selected' : ''}>${esc(x.kurzname || x.name)}${beteiligt.has(x.id) ? ' · beteiligt' : ''}</option>`).join('');
  const zielOptionen = () => ziele.map(z => `<option value="${z.k}">${esc(z.text.replace(/\n/g, ', '))}</option>`).join('') + '<option value="frei">Andere Anschrift …</option>';
  const letzter = [...a.eintraege].filter(e => e.art === 'ausgang').sort((x, y) => y.ereignis_datum.localeCompare(x.ereignis_datum))[0];
  const eigName = (D.eigene || '').split('\n')[0] || '';
  const ctx = {bezug: bezug ? dt(bezug.ereignis_datum) : '[Datum]', letzter: letzter ? dt(letzter.ereignis_datum) : '[Datum]', frist2: dt(plusTage(isoHeute(), 14)), frist4: dt(plusTage(isoHeute(), 28)), name: eigName};
  const fill = (t, z) => t.replace(/\{(\w+)\}/g, (m, key) => key === 'anrede' ? anredeFuer(z && z.person) : ctx[key] ?? m);
  const anl = a.eintraege.filter(e => e.dokument_id && e.art !== 'entwurf');
  const b = edit && edit.brief || {};
  modal(edit ? 'Brief bearbeiten' : 'Brief verfassen', `<div class="compose"><div class="stack">
    <div class="cz-zeile">${edit ? '' : `<label>Vorlage<select id="m-tpl">${Object.entries(VORLAGEN).map(([key, t]) => `<option value="${key}">${t[0]}</option>`).join('')}</select></label>`}
     <label class="cz-schmal">Datum<input id="m-bdat" value="${esc(b.datum || dt(isoHeute()))}"></label></div>
    <div class="two"><label>Kontakt<select id="m-kontakt"><option value="">– ohne Adressbuch –</option>${kontaktOptionen}</select></label>
     <label>Anschrift<select id="m-to" ${ziele.length > 1 ? '' : 'hidden'}>${zielOptionen()}</select><span class="muted" id="m-tohint" style="font-size:12.5px" ${ziele.length > 1 ? 'hidden' : ''}>${k ? (ziele[0]?.k === 'n' ? 'Keine Anschrift hinterlegt – bitte ergänzen.' : 'Aktuelle Anschrift aus dem Adressbuch') : 'Kontakt wählen oder Anschrift eintragen'}</span></label></div>
    <label>Empfänger<textarea id="m-emp" rows="5" class="cz-emp">${esc(b.empfaenger || (ziele[0] ? ziele[0].text : ''))}</textarea></label>
    <div class="cz-zeile"><label class="cz-schmal">Ihr Zeichen<input id="m-zeichen" value="${esc(b.zeichen || (ref ? ref.wert : ''))}"></label>
     <label>Betreff<input id="m-subj" value="${esc(b.betreff || '')}"></label></div>
    <div class="ck-brief"><span class="ck-brief-t">${I('ki')}Claude</span>
     <button type="button" class="btn sm" data-kib="bewerten">1 · Analysieren &amp; bewerten</button>
     <button type="button" class="btn sm" data-kib="${bezug ? 'antwort' : 'schreiben'}" data-stufe2 disabled title="Zuerst analysieren und eine Option wählen">2 · ${bezug ? 'Antwort' : 'Schreiben'} entwerfen</button>
     <button type="button" class="btn sm ghost" data-kib="ueberarbeiten">Text überarbeiten</button>
     <input id="m-kianw" placeholder="Vorgabe (optional), z. B. „Ton freundlicher“ oder „Ratenzahlung über 3 Monate anbieten“"></div>
    <div id="m-kibew" class="kibew" hidden></div>
    <label>Brieftext<textarea id="m-body" class="cz-body">${esc(edit ? edit.text || '' : '')}</textarea></label>
    ${anl.length ? `<label>Anlagen</label><div class="stack" style="gap:4px">${anl.map(e => `<label class="chk"><input type="checkbox" class="m-att" value="${esc(e.titel)}" ${(b.anlagen || []).includes(e.titel) ? 'checked' : ''}>${esc(e.titel)} vom ${dt(e.ereignis_datum)}</label>`).join('')}</div>` : ''}
    <div class="notecard" id="m-kihinweis" style="margin:0;font-size:13px" ${vorschlag && vorschlag.hinweise ? '' : 'hidden'}>${vorschlag && vorschlag.hinweise ? `${I('ki')} <b>Hinweise von Claude:</b> ${esc(vorschlag.hinweise)}` : ''}</div>
    ${edit && edit.versendet_als ? '' : `<div class="stack" style="gap:4px"><label class="chk"><input type="checkbox" id="m-print">Nach dem Speichern drucken</label>
     <label class="chk"><input type="checkbox" id="m-sent">Als versendet in der Chronik erfassen</label>
     <span id="m-sentopt" class="two" hidden><label>Versandart<select id="m-sva">${VERSAND.map(v => `<option>${v}</option>`).join('')}</select></label><label>Versanddatum<input id="m-svd" type="date" value="${isoHeute()}"></label></span></div>`}
    <p class="muted" style="margin:0;font-size:12.5px">Ihr Absender kommt aus Einstellungen → Eigene Angaben. Platzhalter in eckigen Klammern bitte ersetzen.</p></div>
   <div class="cz-rechts"><div class="cz-pvkopf"><span>Vorschau · DIN A4, Anschrift im Sichtfenster</span><span class="sp"></span>
    <button type="button" class="btn sm ghost" data-pvz="-1" title="Kleiner">−</button><button type="button" class="btn sm ghost" data-pvz="1" title="Größer">＋</button></div>
    <div class="pv" id="m-pv" aria-label="Vorschau"></div></div></div>`, async () => {
    const body = $('#m-body') ? $('#m-body').value : val('m-body');
    if (/\[[^\]]{3,40}\]/.test(body) && !S.platzhalterOk) { S.platzhalterOk = true; toast('Der Text enthält noch Platzhalter in eckigen Klammern. Erneut speichern, um trotzdem fortzufahren.'); return false; }
    S.platzhalterOk = false;
    const brief = {empfaenger: val('m-emp'), betreff: val('m-subj'), zeichen: val('m-zeichen'), datum: val('m-bdat'), bezug_datum: bezug ? dt(bezug.ereignis_datum) : null,
      anlagen: [...document.querySelectorAll('.m-att:checked')].map(x => x.value)};
    const titel = val('m-subj') || 'Brief';
    const drucken = $('#m-print')?.checked, versand = $('#m-sent')?.checked ? {art: val('m-sva'), datum: val('m-svd'), empfaenger: brief.empfaenger} : null;
    if (versand && !versand.empfaenger.trim()) { toast('Für den Versand bitte den Empfänger eintragen.'); $('#m-emp').focus(); return false; }
    const fenster = drucken ? window.open('about:blank', '_blank') : null;  // jetzt öffnen, sonst blockiert der Browser das Fenster
    closeModal();
    let entwurfId = edit ? edit.id : null;
    const nachher = async () => {
      if (fenster) fenster.location.href = `/api/eintraege/${entwurfId}/brief?drucken=1`;
      if (versand) { const r = await api(`eintraege/${entwurfId}/versand`, versand); S.entry = r.id; }
    };
    await act(async () => {
      if (edit) { await api('eintraege/' + edit.id, {titel, text: body, brief}); await nachher(); return; }
      const teile = bezug ? bezug.teile : (S.teil !== 'all' ? [S.teil] : []);
      const r = await api(`akte/${a.id}/eintraege`, {art: 'entwurf', titel, text: body, brief, kontakt_id: kId || null, richtung: kId ? 'an' : null, bezug_id: bezug ? bezug.id : null, teile});
      S.entry = entwurfId = r.id;
      if (teile.length) for (const t of teile) { const tv = a.teilvorgaenge.find(x => x.id === t); if (tv && tv.status !== 'Erledigt') await api('teilvorgaenge/' + t, {status: 'Schreiben verfassen'}); }
      else if (a.status !== 'Erledigt') await api('akte/' + a.id, {status: 'Schreiben verfassen'});
      await nachher();
    }, versand ? 'Brief gespeichert und als versendet erfasst. Status: Schreiben abgeschickt.' : edit ? 'Brief gespeichert.' : 'Entwurf angelegt. Status: Verfassen.');
    if (fenster && !entwurfId) fenster.close();
    return false;
  }, edit ? 'Speichern' : 'Entwurf anlegen', 'wide brief');
  const absender = (D.eigene || '').split('\n').filter(Boolean);
  const upd = () => {
    const absaetze = val('m-body').split(/\n\s*\n/).filter(x => x.trim()).map(x => `<p>${esc(x).replace(/\n/g, '<br>')}</p>`).join('');
    const anlagen = [...document.querySelectorAll('.m-att:checked')].map(x => esc(x.value));
    const kopf = absender.length ? `<b>${esc(absender[0])}</b><br>${absender.slice(1).map(esc).join('<br>')}` : '';
    const info = [[val('m-zeichen') && 'Ihr Zeichen', val('m-zeichen')], [bezug && 'Ihr Schreiben vom', bezug && dt(bezug.ereignis_datum)], ['Datum', val('m-bdat')]].filter(x => x[0]);
    const teile = val('m-body').split(/\n\s*\n/).filter(x => x.trim()), gruss = teile.length > 1 && /(Grüßen?|Gruß|Hochachtungsvoll)\W*$/.test(teile[teile.length - 2].trim());
    const absaetze2 = teile.map((x, i) => `<p${gruss && i === teile.length - 1 ? ' class="name"' : ''}>${esc(x.trim()).replace(/\n/g, '<br>')}</p>`).join('');
    $('#m-pv').innerHTML = `<div class="a4"><div class="a4-kopf">${kopf}</div><div class="a4-rs">${esc(absender.join(' · '))}</div>
      <div class="a4-an">${esc(val('m-emp').split('\n').map(z => z.trim()).filter(Boolean).join('\n'))}</div>
      <div class="a4-info">${info.map(([k, v]) => `<span>${k}</span><span>${esc(v)}</span>`).join('')}</div>
      <i class="a4-m" style="top:calc(105 * var(--mm))"></i><i class="a4-m l" style="top:calc(148.5 * var(--mm))"></i><i class="a4-m" style="top:calc(210 * var(--mm))"></i>
      <div class="a4-inhalt"><p class="a4-betreff">${esc(val('m-subj'))}</p>${absaetze2}${anlagen.length ? `<p class="a4-anl"><b>Anlagen</b><br>${anlagen.join('<br>')}</p>` : ''}</div></div>`;
  };
  const vorlage = () => { const t = VORLAGEN[val('m-tpl')], z = ziele.find(x => x.k === val('m-to')) || ziele[0]; $('#m-subj').value = fill(t[1], z); $('#m-body').value = fill(t[2], z); upd(); };
  const box = document.querySelector('.modal');
  box.addEventListener('input', ev => {
    if (ev.target.id === 'm-tpl') vorlage();
    else if (ev.target.id === 'm-kontakt') {
      kId = ev.target.value ? +ev.target.value : null; k = D.kontakte.find(x => x.id === kId); ziele = zieleFuer(k);
      const sel = $('#m-to'); sel.innerHTML = zielOptionen(); sel.hidden = ziele.length <= 1;
      const hint = $('#m-tohint'); hint.hidden = ziele.length > 1; hint.textContent = k ? (ziele[0]?.k === 'n' ? 'Keine Anschrift hinterlegt – bitte ergänzen.' : 'Aktuelle Anschrift aus dem Adressbuch') : 'Kontakt wählen oder Anschrift eintragen';
      $('#m-emp').value = ziele[0] ? ziele[0].text : '';
      const r = refFuer(kId); if (r && !$('#m-zeichen').value) $('#m-zeichen').value = r.wert;
      if (!$('#m-body').dataset.touched && $('#m-tpl')) vorlage(); else upd();
    }
    else if (ev.target.id === 'm-to') { const z = ziele.find(x => x.k === ev.target.value); $('#m-emp').value = z ? z.text : ''; if (!$('#m-body').dataset.touched && $('#m-tpl')) vorlage(); else upd(); }
    else { if (ev.target.id === 'm-body') ev.target.dataset.touched = '1'; upd(); }
  });
  const bewKey = `${a.id}:${bezug ? bezug.id : 'v'}`;
  S.kiBewertung = S.kiBewertung || {};
  const zeigeBewertung = r => {  // Schritt 1: Bewertung mit Optionen anzeigen, Schritt 2 freigeben
    const el = $('#m-kibew'), bw = r.bewertung; el.hidden = false;
    if (!bw) { el.innerHTML = `<div class="ck-text">${claudeText(r.text)}</div>`; }
    else el.innerHTML = `<p><b>Worum es geht:</b> ${esc(bw.zusammenfassung)}</p>
      <details open><summary>Rechtliche Bewertung</summary><div class="ck-text">${claudeText(bw.rechtliche_bewertung)}</div></details>
      ${bw.fristen.length ? `<p><b>Fristen:</b></p><ul class="kifr">${bw.fristen.map(f => `<li><b>${esc(f.datum)}</b> – ${esc(f.was)}</li>`).join('')}</ul>` : ''}
      ${bw.risiken ? `<p><b>Risiken:</b> ${esc(bw.risiken)}</p>` : ''}
      ${bw.fehlende_angaben ? `<p class="kiwarn">${I('alert')} <b>Fehlt noch:</b> ${esc(bw.fehlende_angaben)}</p>` : ''}
      <p style="margin-top:10px"><b>Wie möchten Sie vorgehen?</b></p>
      <div class="kiopt">${bw.optionen.map((o, i) => `<label class="kio"><input type="radio" name="m-kio" value="${i}" ${o.empfohlen ? 'checked' : ''}>
        <span><b>${esc(o.titel)}</b>${o.empfohlen ? ' <span class="pill">Empfohlen</span>' : ''}<br>${esc(o.beschreibung)}
        <small>＋ ${esc(o.vorteile)}</small><small>－ ${esc(o.nachteile)}</small></span></label>`).join('')}
        <label class="kio"><input type="radio" name="m-kio" value="eigen"><span><b>Eigene Linie</b><br>Beschreiben Sie Ihr Vorgehen im Feld „Vorgabe“ oben.</span></label></div>`;
    el.innerHTML += kontextHinweis(r.kontext) + `<div style="display:flex;gap:6px;margin-top:8px"><button type="button" class="btn sm ghost" data-kinotiz>Bewertung als Notiz speichern</button>
      <button type="button" class="btn sm ghost" data-kizit title="Zitierte Paragrafen am amtlichen Wortlaut prüfen (ca. 1 Cent)">Zitate prüfen</button></div><div class="ck-zit" hidden></div>`;
    box.querySelector('[data-stufe2]').disabled = false; box.querySelector('[data-stufe2]').title = '';
  };
  if (S.kiBewertung[bewKey]) zeigeBewertung(S.kiBewertung[bewKey]);
  const pvZoom = z => { S.pvZoom = Math.min(1, Math.max(0.6, z)); $('#m-pv').style.setProperty('--pvz', S.pvZoom); };
  pvZoom(S.pvZoom || 1);
  box.addEventListener('click', async ev => {
    const zb = ev.target.closest('[data-pvz]'); if (zb) { pvZoom((S.pvZoom || 1) + 0.1 * +zb.dataset.pvz); return; }
    if (ev.target.closest('[data-kizit]')) { await zitatePruefen(S.kiBewertung[bewKey].text, $('#m-kibew .ck-zit'), ev.target.closest('[data-kizit]')); return; }
    if (ev.target.closest('[data-kinotiz]')) {
      const r = S.kiBewertung[bewKey], knopf = ev.target.closest('[data-kinotiz]');
      try { await api(`akte/${a.id}/eintraege`, {art: 'notiz', titel: 'Rechtliche Bewertung (Claude)' + (bezug ? ' – ' + bezug.titel : ''), text: r.text, bezug_id: bezug ? bezug.id : null, teile: bezug ? bezug.teile : []});
        knopf.disabled = true; knopf.textContent = 'In der Chronik gespeichert'; } catch (err) { toast(err.message); }
      return;
    }
    const k = ev.target.closest('[data-kib]'); if (!k || box.dataset.ki) return;
    if (!D.claude) D.claude = await api('claude');
    if (!D.claude.eingerichtet) { toast('Claude ist noch nicht eingerichtet: Einstellungen → Claude (KI-Analyse).'); return; }
    const aufgabe = k.dataset.kib, knoepfe = box.querySelectorAll('[data-kib]'), alt = k.innerHTML;
    const bew = S.kiBewertung[bewKey];
    let option = '';
    if (aufgabe === 'antwort' || aufgabe === 'schreiben') {
      const wahl = box.querySelector('input[name=m-kio]:checked')?.value;
      if (wahl === 'eigen') { if (!val('m-kianw').trim()) { toast('Bitte im Feld „Vorgabe“ beschreiben, wie Sie vorgehen möchten.'); $('#m-kianw').focus(); return; } }
      else if (bew && bew.bewertung && wahl !== undefined) { const o = bew.bewertung.optionen[+wahl]; option = `${o.titel}: ${o.beschreibung}`; }
      if ($('#m-body').dataset.touched && !confirm('Den bisherigen Brieftext durch einen Entwurf von Claude ersetzen?')) return;
    }
    const zweiter = box.querySelector('[data-stufe2]'), war2 = zweiter.disabled;
    box.dataset.ki = '1'; knoepfe.forEach(b => b.disabled = true);
    k.innerHTML = `<span class="spin"></span>${aufgabe === 'bewerten' ? 'Claude prüft die Akte …' : 'Claude schreibt …'}`;
    try {
      const r = await api('claude/fragen', {vorgang_id: a.id, dokument_id: bezug ? bezug.dokument_id : null, verlauf: [], aufgabe,
        anweisung: val('m-kianw'), entwurf: val('m-body'), empfaenger: val('m-emp'), bewertung: bew ? bew.text : '', option});
      if (!document.body.contains(box)) return;
      if (aufgabe === 'bewerten') { S.kiBewertung[bewKey] = r; zeigeBewertung(r); $('#m-kibew').scrollIntoView({block: 'nearest'}); throw null; }
      if (r.betreff) $('#m-subj').value = r.betreff;
      $('#m-body').value = r.brieftext || r.text; $('#m-body').dataset.touched = '1'; upd();
      const h = $('#m-kihinweis'); h.hidden = !(r.hinweise || r.kontext); h.innerHTML = (r.hinweise ? `${I('ki')} <b>Hinweise von Claude:</b> ${esc(r.hinweise)}` : '') + kontextHinweis(r.kontext);
    } catch (err) { if (err) toast(err.message); }
    delete box.dataset.ki; knoepfe.forEach(b => b.disabled = false); k.innerHTML = alt;
    zweiter.disabled = war2 && !S.kiBewertung[bewKey];
  });
  box.addEventListener('change', ev => { if (ev.target.classList.contains('m-att')) upd(); if (ev.target.id === 'm-sent') $('#m-sentopt').hidden = !ev.target.checked; });
  if (edit) upd(); else vorlage();
  if (vorschlag) { if (vorschlag.betreff) $('#m-subj').value = vorschlag.betreff; $('#m-body').value = vorschlag.brieftext || ''; $('#m-body').dataset.touched = '1'; upd(); }
}

// ---------- Abschluss, Export, Chat-Notizen, Sicherung ----------
async function statusSetzen(teilId, status, zurueck) {
  const a = D.akte;
  const speichern = () => teilId ? api('teilvorgaenge/' + teilId, {status}) : api('akte/' + a.id, {status});
  if (status !== 'Erledigt') return act(speichern, 'Status geändert.');
  const o = await api(`akte/${a.id}/offen${teilId ? '?teil=' + teilId : ''}`);
  const n = o.fristen.length + o.entwuerfe.length + o.fehlende_originale.length + o.ungepruefte_chats.length;
  const insArchiv = ok => { if (ok && !teilId) location.hash = 'archiv'; };
  if (!n) return insArchiv(await act(speichern, teilId ? 'Teilvorgang erledigt. Seine Dokumente stehen im Archiv.' : 'Erledigt. Der Vorgang ist aus der Liste entfernt, die Dokumente stehen im Archiv.'));
  const li = (ic, t) => `<li>${I(ic)}<span>${esc(t)}</span></li>`;
  modal(`${teilId ? teilName(teilId) : a.titel} abschließen?`, `<p style="margin:0">Vor dem Abschluss ist noch Folgendes offen:</p><ul class="openlist">
    ${o.fristen.map(f => li('cal', `${FK[f.art]} ${dt(f.faellig_am)}: ${f.titel}`)).join('')}${o.entwuerfe.map(e => li('draft', 'Entwurf nicht versendet: ' + e.titel)).join('')}
    ${o.fehlende_originale.map(e => li('alert', 'Original fehlt: ' + e.titel)).join('')}${o.ungepruefte_chats.map(e => li('chat', 'Chat-Notiz ungeprüft: ' + e.titel)).join('')}</ul>
    ${o.fristen.length ? '<label class="chk"><input type="checkbox" id="m-frdone" checked>Offene Fristen und Wiedervorlagen als erledigt markieren</label>' : ''}`, async () => {
    const alle = $('#m-frdone') ? $('#m-frdone').checked : false; closeModal();
    insArchiv(await act(async () => { if (alle) for (const f of o.fristen) await api('fristen/' + f.id, {erledigt: true}); await speichern(); }, 'Erledigt. Der Vorgang ist aus der Liste entfernt, die Dokumente stehen im Archiv.'));
    return false;
  }, 'Trotzdem abschließen');
  const abbruch = () => { if (zurueck) zurueck(); };
  document.querySelector('#modalroot [data-act=m-close]').addEventListener('click', abbruch, {once: true});
}
function exportDialog() {
  const a = D.akte;
  modal('Akte exportieren', `<p style="margin:0">Die ZIP-Datei enthält die Chronik als PDF, die Akte als Datensatz (akte.json) und die ausgewählten Originale.</p>
   <div class="stack" style="gap:4px;max-height:300px;overflow:auto">${a.dokumente.map(d => `<label class="chk"><input type="checkbox" class="m-xd" value="${d.id}" checked>${esc(d.titel)} <span class="muted">(${esc(d.dateiname)})</span></label>`).join('') || '<span class="muted">Keine Dokumente.</span>'}</div>`, async () => {
    const ids = [...document.querySelectorAll('.m-xd:checked')].map(x => x.value);
    closeModal(); location.href = `/api/akte/${a.id}/export?docs=${ids.length === a.dokumente.length ? 'alle' : ids.join(',') || '0'}`; toast('ZIP wird erstellt und heruntergeladen.'); return false;
  }, 'ZIP herunterladen');
}
// ---------- Aus ChatGPT übernehmen (Lesezeichen) ----------
let EMPFANG = null;
const EMPF_ERLAUBT = /\.(pdf|jpe?g|png|tiff?|docx|eml)$/i;
const ENDUNG = {'application/pdf': '.pdf', 'image/jpeg': '.jpg', 'image/png': '.png', 'image/tiff': '.tif', 'image/webp': '.webp', 'image/gif': '.gif', 'message/rfc822': '.eml',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx'};
function empfangVorbereiten(paket) {
  paket.dateien = (paket.dateien || []).map((d, i) => {
    let name = (d.name || '').trim() || `Datei ${i + 1}`;
    if (!/\.[a-z0-9]{2,5}$/i.test(name) && ENDUNG[(d.mime || '').split(';')[0]]) name += ENDUNG[(d.mime || '').split(';')[0]];
    const bild = /^image\/(webp|gif|heic|avif)/.test(d.mime || '') || /\.(webp|gif|heic|avif)$/i.test(name);
    return {...d, name, umwandeln: bild && !!d.daten, an: !!d.daten && (EMPFANG_OK(name) || bild)};
  });
  return paket;
}
const EMPFANG_OK = name => EMPF_ERLAUBT.test(name);
addEventListener('message', ev => {
  if (!/^https:\/\/(chatgpt\.com|chat\.openai\.com)$/.test(ev.origin) || !ev.data || ev.data.documanager !== 'chat') return;
  try { ev.source.postMessage({documanager: 'erhalten'}, ev.origin); } catch (e) { /* Absender schon geschlossen */ }
  if (EMPFANG && EMPFANG.url === ev.data.url) return;  // dieselbe Sendung, wiederholt
  EMPFANG = empfangVorbereiten(ev.data);
  if (location.hash !== '#chatempfang') location.hash = 'chatempfang'; else render();
});
function empfangAusDatei(text) {
  const p = JSON.parse(text);
  if (p.documanager !== 'chat') throw new Error('Keine DocuManager-Datei aus ChatGPT.');
  p.dateien = (p.dateien || []).map(d => d.daten ? {...d, daten: Uint8Array.from(atob(d.daten), c => c.charCodeAt(0)).buffer} : d);
  EMPFANG = empfangVorbereiten(p);
  if (location.hash !== '#chatempfang') location.hash = 'chatempfang'; else render();
}
function vEmpfang() {
  if (!EMPFANG) return `<h1>Aus ChatGPT übernehmen</h1><div class="panel stack" style="margin-top:16px"><p style="margin:0">Warte auf Daten aus ChatGPT … Öffnen Sie in ChatGPT den gewünschten Chat und klicken Sie in der Lesezeichenleiste auf <b>„→ DocuManager“</b>.</p>
    <p class="muted" style="margin:0;font-size:13px">Das Lesezeichen richten Sie unter <a href="#einstellungen">Einstellungen → ChatGPT-Lesezeichen</a> ein. Hat das Lesezeichen eine Datei <code>….documanager.json</code> gespeichert, ziehen Sie sie hierher.</p></div>`;
  const e = EMPFANG, mitDaten = e.dateien.filter(d => d.daten);
  return `<h1>Aus ChatGPT übernehmen</h1><p class="muted" style="margin:6px 0 16px">Chat <b>${esc(e.titel)}</b> · ${e.nachrichten.length} Beiträge · ${mitDaten.length} von ${e.dateien.length} Datei(en) erhalten</p>
  <div class="panel stack">
   <label class="stack" style="gap:5px;font-size:13px;color:var(--muted)">Ablegen in<select id="em-ziel" class="inp" style="max-width:420px"><option value="">Posteingang (später zuordnen)</option>${vorgangOptionen('')}<option value="__new">+ Neuer Vorgang …</option></select></label>
   <div><h3 style="margin:6px 0">Dateien</h3>${e.dateien.length ? `<div class="stack" style="gap:6px">${e.dateien.map((d, i) => `<label class="chk"><input type="checkbox" class="em-datei" value="${i}" ${d.an ? 'checked' : ''} ${d.daten && (EMPFANG_OK(d.name) || d.umwandeln) ? '' : 'disabled'}>
      ${typIcon(d.mime)} ${esc(d.name)} <span class="muted" style="font-size:12px">${d.daten ? groesse(d.daten.byteLength) : ''}${d.fehler ? ' · ' + esc(d.fehler) + ' (ChatGPT gibt die Datei nicht heraus)' : !EMPFANG_OK(d.name) && !d.umwandeln ? ' · Format wird nicht unterstützt' : d.umwandeln ? ' · wird als PNG übernommen' : ''}</span></label>`).join('')}</div>` : '<p class="muted" style="margin:0">In diesem Chat wurden keine Dateien hochgeladen.</p>'}</div>
   <label class="chk"><input type="checkbox" id="em-notiz" ${e.nachrichten.length ? 'checked' : 'disabled'}>Chatverlauf als Chat-Notiz im Vorgang speichern <span class="muted" style="font-size:12px">(nur mit Vorgang)</span></label>
   <div style="display:flex;gap:8px"><button class="btn pri" data-act="em-los">Übernehmen</button><button class="btn ghost" data-act="em-verwerfen">Verwerfen</button></div></div>`;
}
// ---------- Dokumente kombinieren (pdf-lib, im Browser) ----------
const kombinierbar = p => !!p && (p.mime === 'application/pdf' || /^image\//.test(p.mime || ''));
const skripte = {};
function skriptLaden(src, name) {
  if (window[name]) return Promise.resolve(window[name]);
  return skripte[src] || (skripte[src] = new Promise((ok, fehler) => { const s = document.createElement('script'); s.src = src; s.onload = () => ok(window[name]); s.onerror = () => fehler(new Error('Bibliothek nicht ladbar')); document.head.append(s); }));
}
async function alsPng(bytes, mime) {  // Bildformate, die pdf-lib nicht direkt einbettet (z. B. TIFF, WebP)
  const bild = await createImageBitmap(new Blob([bytes], {type: mime || 'image/tiff'}));
  const c = document.createElement('canvas'); c.width = bild.width; c.height = bild.height; c.getContext('2d').drawImage(bild, 0, 0);
  return new Uint8Array(await (await new Promise(r => c.toBlob(r, 'image/png'))).arrayBuffer());
}
async function kombinieren(ids, titel) {
  const {PDFDocument, degrees} = await skriptLaden('/pdflib/pdf-lib.min.js', 'PDFLib');
  const ziel = await PDFDocument.create();
  for (const id of ids) {
    const p = D.inbox.find(x => x.id === id), rot = (p && p.drehung_manuell) || 0;
    const res = await holen(`/api/documents/${id}/original`); if (!res.ok) throw new Error(`„${p ? p.titel : id}“ nicht lesbar`);
    const bytes = new Uint8Array(await res.arrayBuffer()), typ = res.headers.get('content-type') || p.mime;
    if (bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46) {  // %PDF
      const quelle = await PDFDocument.load(bytes, {ignoreEncryption: true});
      for (const seite of await ziel.copyPages(quelle, quelle.getPageIndices())) {
        if (rot) seite.setRotation(degrees((seite.getRotation().angle + rot) % 360));
        ziel.addPage(seite);
      }
    } else {  // Bild auf eine A4-Seite (hoch oder quer) einpassen
      const bild = bytes[0] === 0xFF && bytes[1] === 0xD8 ? await ziel.embedJpg(bytes) : bytes[0] === 0x89 && bytes[1] === 0x50 ? await ziel.embedPng(bytes) : await ziel.embedPng(await alsPng(bytes, typ));
      const quer = bild.width > bild.height, B = quer ? 842 : 595, H = quer ? 595 : 842, f = Math.min(B / bild.width, H / bild.height);
      const seite = ziel.addPage([B, H]);
      seite.drawImage(bild, {x: (B - bild.width * f) / 2, y: (H - bild.height * f) / 2, width: bild.width * f, height: bild.height * f});
      if (rot) seite.setRotation(degrees(rot));
    }
  }
  ziel.setTitle(titel);
  const datei = new File([await ziel.save()], titel.replace(/[\\/:*?"<>|]+/g, '-').slice(0, 120) + '.pdf', {type: 'application/pdf'});
  const r = await upload('posteingang/dokumente', datei);
  await api(`documents/${r.id}/title`, {title: titel});
  for (const id of ids) await api(`dokument/${id}/loeschen`, {});
  return r.id;
}
async function alsDatei(d) {
  if (!d.umwandeln) return new File([d.daten], d.name, {type: d.mime || ''});
  const bild = await createImageBitmap(new Blob([d.daten], {type: d.mime || 'image/webp'}));
  const c = document.createElement('canvas'); c.width = bild.width; c.height = bild.height; c.getContext('2d').drawImage(bild, 0, 0);
  const png = await new Promise(r => c.toBlob(r, 'image/png'));
  return new File([png], d.name.replace(/\.[a-z0-9]+$/i, '') + '.png', {type: 'image/png'});
}
async function empfangUebernehmen(vorgang) {
  const e = EMPFANG, gewaehlt = [...document.querySelectorAll('.em-datei:checked')].map(x => e.dateien[+x.value]);
  const notiz = $('#em-notiz')?.checked && vorgang;
  if (!gewaehlt.length && !notiz) { toast('Bitte eine Datei wählen oder einen Vorgang für die Chat-Notiz.'); return; }
  let neu = 0; const fehler = [];
  for (const d of gewaehlt) {
    toast(`„${d.name}“ wird abgelegt …`);
    try { const r = await upload(vorgang ? `cases/${vorgang}/documents` : 'posteingang/dokumente', await alsDatei(d)); if (r.created) neu++; }
    catch (err) { fehler.push(`${d.name}: ${err.message}`); }
  }
  if (notiz) {
    const text = e.nachrichten.map(n => `${n.rolle === 'user' ? 'Ich' : 'ChatGPT'}: ${n.text}`).join('\n\n').slice(0, 19500);
    const erste = e.nachrichten.find(n => n.zeit);
    try { await api(`akte/${vorgang}/chatnotiz`, {titel: e.titel.slice(0, 200), quelle: 'ChatGPT: ' + e.url, datum: erste ? new Date(erste.zeit * 1000).toISOString().slice(0, 10) : isoHeute(), text}); }
    catch (err) { fehler.push('Chat-Notiz: ' + err.message); }
  }
  toast(`${neu} Datei(en) übernommen${notiz ? ', Chatverlauf als Chat-Notiz gespeichert' : ''}${fehler.length ? ' · ' + fehler.join(' · ') : ''}.`);
  EMPFANG = null;
  if (vorgang) { S.v = +vorgang; S.tab = 'chronik'; S.teil = 'all'; S.entry = null; location.hash = 'akte-' + vorgang; } else location.hash = 'posteingang';
}
function vChat() {
  return `<div class="head" style="justify-content:space-between"><h1>Chat-Notizen</h1><span style="display:flex;gap:8px"><button class="btn" data-act="chat-export">ChatGPT-Export importieren …</button><button class="btn pri" data-act="chat-new">${I('plus')}Chat-Notiz übernehmen</button></span></div>
  <p class="muted" style="margin:6px 0 16px;max-width:75ch">Zusammenfassungen und Auszüge aus Chats, etwa aus ChatGPT, mit Quellenhinweis. Sie bleiben als ungeprüft gekennzeichnet, bis Sie sie mit den Originalen abgeglichen haben. Im Text erwähnte Schreiben, die in der Akte fehlen, werden als „Original fehlt“ vermerkt.</p>
  <div class="panel">${D.chats.length ? D.chats.map(c => `<div class="frow" style="grid-template-columns:minmax(0,1fr) auto"><div style="min-width:0"><div class="t"><a href="#akte-${c.vorgang_id}">${esc(c.titel)}</a></div>
    <div class="m"><span>${esc(c.vorgang)}</span><span>· ${dt(c.ereignis_datum)}</span><span>· ${esc(c.quelle || '')}</span></div><div class="m" style="margin-top:4px;color:var(--fg)">${esc(c.auszug || '')}</div></div>
    <div class="acts">${c.geprueft ? '<span class="pill ok">geprüft</span>' : `<span class="pill warn">ungeprüft</span><button class="btn sm" data-act="chat-ok" data-id="${c.id}">Geprüft</button>`}</div></div>`).join('') : '<p class="muted" style="margin:0">Noch keine Chat-Notizen.</p>'}</div>
  ${D.threads.length ? `<h2 style="margin:24px 0 8px">Importierte ChatGPT-Unterhaltungen</h2><p class="muted" style="margin:0 0 10px">Aus der bisherigen Ansicht importiert. Übernehmen Sie die relevanten Teile als Chat-Notiz in einen Vorgang.</p>
   <div class="panel">${D.threads.map(t => `<div class="frow" style="grid-template-columns:minmax(0,1fr) auto"><div class="t">${esc(t.titel || t.id)}</div><div class="acts"><button class="btn sm" data-act="chat-thread" data-id="${esc(t.id)}">In Vorgang übernehmen</button></div></div>`).join('')}</div>` : ''}`;
}
function chatModal(text, quelle) {
  modal('Chat-Notiz übernehmen', `<label>Vorgang<select id="m-cv">${aktiv().map(c => `<option value="${c.id}">${esc(c.titel)}</option>`).join('')}</select></label>
   <div class="two"><label>Titel<input id="m-ct" placeholder="z. B. Einschätzung zur Kündigung"></label><label>Datum des Chats<input id="m-cd" type="date" value="${isoHeute()}"></label></div>
   <label>Quelle<input id="m-cq" value="${esc(quelle || '')}" placeholder="z. B. ChatGPT-Verlauf „Unitask Rechnung“"></label>
   <label>Zusammenfassung oder relevanter Auszug<textarea id="m-cx" rows="9">${esc(text || '')}</textarea></label>`, async () => {
    if (!val('m-ct').trim()) { $('#m-ct').focus(); return false; }
    closeModal();
    try { const r = await api(`akte/${val('m-cv')}/chatnotiz`, {titel: val('m-ct'), datum: val('m-cd'), quelle: val('m-cq'), text: val('m-cx')});
      toast(`Chat-Notiz übernommen.${r.fehlend ? ` ${r.fehlend} erwähnte${r.fehlend === 1 ? 's Schreiben fehlt' : ' Schreiben fehlen'} in der Akte.` : ''}`); location.hash = 'akte-' + val('m-cv'); await render(); } catch (e) { toast(e.message); }
    return false;
  }, 'Übernehmen');
}
function docTable() {
  const a = D.akte, so = S.sortD;
  const key = {titel: d => d.titel, datei: d => d.dateiname, datum: d => d.angelegt_am, text: d => d.ocr_status}[so.k];
  const rows = [...a.dokumente].sort((x, y) => cmp(key(x), key(y)) * so.d).map(d => `<tr data-act="doc-open" data-doc="${d.id}"><td><span class="docname" style="align-items:center">${typIcon(d.mime)}<b>${esc(d.titel)}</b></span></td><td>${esc(d.dateiname)}</td><td class="num">${dt(d.angelegt_am)}</td><td>${esc(d.ocr_status)}</td>
    <td style="white-space:nowrap"><button class="iconbtn sm" data-act="doc-move" data-doc="${d.id}" title="In anderen Vorgang verschieben" aria-label="${esc(d.titel)} verschieben">${I('move')}</button><button class="iconbtn sm" data-act="doc-remove" data-doc="${d.id}" title="Aus diesem Vorgang löschen" aria-label="${esc(d.titel)} löschen">${I('trash')}</button></td></tr>`).join('');
  return `<div style="margin-top:18px" class="tbl-wrap"><table><thead><tr>${sortTh('D','titel','Dokument')}${sortTh('D','datei','Datei')}${sortTh('D','datum','Abgelegt')}${sortTh('D','text','Text')}<th><span class="sr">Aktionen</span></th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="muted">Noch keine Dokumente.</td></tr>'}</tbody></table></div>`;
}
function beteiligteTab() {
  const a = D.akte;
  return `<div class="filters" style="margin:18px 0 12px"><button class="btn" data-act="bet-add">${I('plus')}Beteiligten hinzufügen</button><button class="btn" data-act="ref-add">${I('plus')}Referenz hinzufügen</button><button class="btn" data-act="tags">Schlagwörter</button></div>
  ${a.referenzen.length ? `<div class="panel" style="margin-bottom:16px"><h3>Referenzen</h3><ul class="mini" style="margin-top:6px">${a.referenzen.map(r => `<li><span><span class="muted">${esc(r.bezeichnung)}</span> <b class="num">${esc(r.wert)}</b></span><button class="btn sm ghost" data-act="ref-del" data-id="${r.id}">Entfernen</button></li>`).join('')}</ul></div>` : ''}
  <div class="grid2">${a.beteiligte.map(b => `<div class="panel stack"><div><h3>${esc(b.name)}</h3><span class="muted">${esc(b.rolle || b.typ || '')}</span></div>
   <div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn sm" data-act="contact" data-id="${b.kontakt_id}">Im Adressbuch öffnen</button><button class="btn sm ghost" data-act="bet-del" data-id="${b.kontakt_id}">Entfernen</button></div></div>`).join('') || '<p class="muted">Noch keine Beteiligten.</p>'}</div>`;
}

// ---------- Fristen ----------
function fristRow(f, inV) {
  const n = tage(f.faellig_am), u = f.erledigt_am ? '' : n < 0 ? 'crit' : n <= 7 ? 'warn' : '';
  return `<div class="frow ${f.erledigt_am ? 'done' : ''}"><div class="fdate ${u}"><b class="num">${dShort(f.faellig_am)}</b><small>${WD[new Date(f.faellig_am + 'T12:00').getDay()]} · ${f.faellig_am.slice(0, 4)}</small></div>
   <div style="min-width:0"><div class="t">${esc(f.titel)}</div><div class="m"><span class="pill ${FKC[f.art]}" style="font-size:12px;padding:1px 7px">${FK[f.art]}</span>
    ${inV ? '' : `<a href="#akte-${f.vorgang_id}">${esc(f.vorgang)}</a>`}${f.teilvorgang ? `<span>· ${esc(f.teilvorgang)}</span>` : ''}${f.zustaendig ? `<span>· Zuständig: ${esc(f.zustaendig)}</span>` : ''}<span>· ${f.erledigt_am ? 'erledigt' : relTage(f.faellig_am)}</span></div>
    ${f.verlauf && f.verlauf.length ? `<div class="m" style="margin-top:2px">Ursprünglich fällig ${dt(f.verlauf[0].faellig_alt)} · ${f.verlauf.length}× verschoben</div>` : ''}
    <div class="m" style="margin-top:2px">Quelle: ${f.quelle_zitat ? '„' + esc(f.quelle_zitat) + '“' : f.quelle_dokument_id ? 'Dokument' : 'selbst gesetzt'}</div></div>
   <div class="acts">${f.erledigt_am ? `<button class="btn sm" data-act="f-undo" data-id="${f.id}">Wieder öffnen</button>` : `<button class="btn sm" data-act="f-done" data-id="${f.id}">Erledigt</button><button class="btn sm" data-act="f-move" data-id="${f.id}">Verschieben</button>`}</div></div>`;
}
function fristList(list, inV) {
  const open = list.filter(f => !f.erledigt_am), done = list.filter(f => f.erledigt_am);
  const g = [['Überfällig', open.filter(f => tage(f.faellig_am) < 0)], ['Nächste 14 Tage', open.filter(f => tage(f.faellig_am) >= 0 && tage(f.faellig_am) <= 14)], ['Später', open.filter(f => tage(f.faellig_am) > 14)], ['Erledigt', done]].filter(x => x[1].length);
  return g.length ? g.map(([t, l]) => `<div class="grp">${t}</div><div>${l.map(f => fristRow(f, inV)).join('')}</div>`).join('') : '<p class="muted">Keine Fristen.</p>';
}
function vFristen() {
  const all = D.fristen.filter(f => S.fFilter === 'alle' || f.art === S.fFilter);
  const cnt = k => D.fristen.filter(f => !f.erledigt_am && (k === 'alle' || f.art === k)).length;
  return `<div class="head" style="justify-content:space-between"><h1>Fristen</h1><button class="btn pri" data-act="f-neu">${I('plus')}Neue Frist</button></div><p class="muted" style="margin:6px 0 0">Verbindliche Fristen tragen immer eine Fundstelle. Wiedervorlagen und Aufgaben setzen Sie selbst.</p>
  ${filterBlock([[{lbl: 'Art', act: 'ffilter', aktiv: S.fFilter, opt: [['alle','Alle'],['frist','Verbindliche Fristen'],['wiedervorlage','Wiedervorlagen'],['aufgabe','Aufgaben']].map(([k, l]) => [k, `${l} (${cnt(k)})`])}]])}
  <div class="panel">${fristList(all, false)}</div>`;
}

// ---------- Archiv ----------
function vArchiv() {
  const q = S.aText.toLowerCase();
  const jahre = [...new Set(D.archiv.map(d => d.datum.slice(0, 4)))].sort().reverse();
  const bereiche = [...new Set(D.archiv.flatMap(d => d.bereiche || [d.bereich]))].sort(cmp);
  const typName = d => d.typ || (KIND[d.art] || ['Ohne Typ'])[0];
  const typen = [...new Set([...['eingang', 'ausgang', 'entwurf', 'nachweis'].map(k => KIND[k][0]), ...(D.arten || []), ...D.archiv.map(typName)])];
  if (S.aTyp && S.aTyp !== 'alle' && !typen.includes(S.aTyp)) S.aTyp = 'alle';
  let list = D.archiv.filter(d => (S.aBereich === 'alle' || (d.bereiche || [d.bereich]).includes(S.aBereich)) && (S.aJahr === 'alle' || d.datum.startsWith(S.aJahr))
    && (!S.aTyp || S.aTyp === 'alle' || typName(d) === S.aTyp)
    && (!q || [d.titel, d.dateiname, d.vorgang, d.absender].join(' ').toLowerCase().includes(q)));
  const so = S.sortA, key = {titel: d => d.titel, datum: d => d.datum, absender: d => d.absender || '~', vorgang: d => d.vorgang, groesse: d => d.groesse || 0}[so.k];
  list.sort((x, y) => (so.k === 'groesse' ? key(x) - key(y) : cmp(key(x), key(y))) * so.d);
  // Bei mehreren Bereichen erscheint ein Dokument in jeder seiner Bereichsgruppen
  const gkey = {vorgang: d => [d.vorgang], bereich: d => d.bereiche || [d.bereich], typ: d => [typName(d)], absender: d => [d.absender || 'Absender unbekannt'], empfaenger: d => [empfaengerVon(d) || 'Empfänger unbekannt'], jahr: d => [d.datum.slice(0, 4)], keine: () => ['']}[S.aGroup];
  const groups = [];
  for (const d of list) for (const k of gkey(d)) { let g = groups.find(x => x.k === k); if (!g) groups.push(g = {k, items: []}); g.items.push(d); }
  if (S.aGroup === 'jahr') groups.sort((x, y) => cmp(y.k, x.k)); else if (S.aGroup !== 'keine') groups.sort((x, y) => cmp(x.k, y.k));
  const row = d => `<tr data-act="arch-edit" data-doc="${d.id}" title="Klicken zum Bearbeiten"><td><div class="docname"><button class="docico" data-act="view" data-doc="${d.id}" title="${TYP_NAME[TYP(d.mime)[0]]} ansehen" aria-label="${esc(d.titel)} ansehen">${typIcon(d.mime)}</button><div style="min-width:0"><b>${esc(d.titel)}</b><div class="muted" style="font-size:12.5px">${esc(d.dateiname)}</div></div></div></td><td class="num">${dt(d.datum)}<div class="muted" style="font-size:12px">${esc(typName(d))}</div></td><td>${esc(d.absender || '–')}${empfaengerVon(d) ? `<div class="muted" style="font-size:12.5px">an ${esc(empfaengerVon(d))}</div>` : ''}${(d.kontakte || []).length ? `<div class="muted" style="font-size:12.5px">+ ${esc(d.kontakte.map(k => k.name).join(', '))}</div>` : ''}</td><td>${esc(d.vorgang)}<div class="muted" style="font-size:12.5px">${esc((d.bereiche || [d.bereich]).join(', '))}</div></td><td class="num">${groesse(d.groesse)}</td>
    <td style="white-space:nowrap"><button class="iconbtn lg" data-act="arch-move" data-doc="${d.id}" data-v="${d.vorgang_id}" data-t="${esc(d.titel)}" title="Einem Vorgang zuordnen" aria-label="${esc(d.titel)} einem Vorgang zuordnen">${I('move')}</button><button class="iconbtn lg" data-act="arch-del" data-doc="${d.id}" data-v="${d.vorgang_id}" data-t="${esc(d.titel)}" title="Löschen" aria-label="${esc(d.titel)} löschen">${I('trash')}</button></td></tr>`;
  const thead = `<thead><tr>${sortTh('A','titel','Dokument')}${sortTh('A','datum','Datum')}${sortTh('A','absender','Absender')}${sortTh('A','vorgang','Vorgang')}${sortTh('A','groesse','Größe')}<th><span class="sr">Aktionen</span></th></tr></thead>`;
  return `<h1>Archiv</h1><p class="muted" style="margin:6px 0 0">${D.archiv.length} archivierte Dokumente. Wird ein Vorgang erledigt, verschwindet er aus „Vorgänge“; seine Dokumente stehen hier. ${list.length !== D.archiv.length ? `${list.length} passen zu den Filtern.` : ''}</p>

  ${filterBlock([[{lbl: 'Gruppieren', act: 'agroup', aktiv: S.aGroup, opt: [['vorgang','Vorgang'],['bereich','Bereich'],['typ','Typ'],['absender','Absender'],['empfaenger','Empfänger'],['jahr','Jahr'],['keine','Keine']]},
      {lbl: 'Bereich', act: 'abereich', aktiv: S.aBereich, opt: ['alle', ...bereiche].map(b => [b, b === 'alle' ? 'Alle' : b])}],
    [{lbl: 'Typ', act: 'atyp', aktiv: S.aTyp || 'alle', opt: ['alle', ...typen].map(t => [t, t === 'alle' ? 'Alle' : t])},
      {lbl: 'Jahr', act: 'ajahr', aktiv: S.aJahr, opt: ['alle', ...jahre].map(j => [j, j === 'alle' ? 'Alle' : j])}]],
    `<input class="inp" id="atext" type="search" placeholder="Im Archiv filtern" value="${esc(S.aText)}" style="max-width:220px" aria-label="Im Archiv filtern">`)}
  ${groups.length ? groups.map(g => `${S.aGroup !== 'keine' ? `<div class="agrp"><h3>${esc(g.k)}</h3><span class="muted num">${g.items.length}</span></div>` : ''}<div class="tbl-wrap" style="margin-bottom:16px"><table>${thead}<tbody>${g.items.map(row).join('')}</tbody></table></div>`).join('') : '<div class="panel muted">Keine Dokumente für diese Filter.</div>'}`;
}

// ---------- Adressbuch ----------
function vAb() {
  const q = S.abq.toLowerCase();
  const list = D.kontakte.filter(k => !q || [k.name, k.kurzname, k.typ, ...k.abteilungen.map(a => [a.name, a.ansprechpartner, a.email].join(' '))].join(' ').toLowerCase().includes(q));
  const k = D.kontakte.find(x => x.id === S.contact) || list[0];
  return `<div class="head" style="justify-content:space-between"><h1>Adressbuch</h1><button class="btn" data-act="k-new">${I('plus')}Neuer Kontakt</button></div>
  <div class="ab" style="margin-top:16px"><div class="stack" style="gap:8px"><input class="inp" id="abq" type="search" placeholder="Kontakt suchen" value="${esc(S.abq)}" aria-label="Kontakt suchen">
   <div class="ablist">${list.map(x => `<button data-act="contact" data-id="${x.id}" class="${k && x.id === k.id ? 'on' : ''}">${esc(x.name)}<small>${esc(x.typ || '')}${x.vorgaenge.length ? ` · ${x.vorgaenge.length} Vorgänge` : ''}</small></button>`).join('') || '<span class="muted" style="padding:8px">Keine Kontakte.</span>'}</div></div>
   ${k ? `<div class="stack"><div class="panel"><div class="chron-h"><h2>${esc(k.name)}</h2><span style="display:flex;gap:4px"><button class="iconbtn" data-act="k-edit" data-id="${k.id}" title="Kontakt bearbeiten" aria-label="Kontakt bearbeiten">${I('draft')}</button><button class="iconbtn" data-act="k-del" data-id="${k.id}" title="Kontakt löschen" aria-label="Kontakt löschen">${I('trash')}</button></span></div><span class="muted">${esc([k.typ, k.notiz].filter(Boolean).join(' · '))}</span></div>
    ${k.abteilungen.map(a => `<div class="panel stack"><div class="chron-h"><h3>${esc(a.name || 'Kontakt')}</h3><button class="btn sm" data-act="adr-new" data-id="${a.id}">Neue Anschrift</button></div>
     <dl class="dl">${a.ansprechpartner ? `<dt>Ansprechpartner</dt><dd>${esc(a.ansprechpartner)}</dd>` : ''}${a.email ? `<dt>E-Mail</dt><dd>${esc(a.email)}</dd>` : ''}${a.telefon ? `<dt>Telefon</dt><dd>${esc(a.telefon)}</dd>` : ''}</dl>
     ${a.anschriften.length ? `<div class="adrbox">${a.anschriften.map(r => `<div class="adr ${r.gueltig_bis ? 'old' : ''}"><b style="font-size:12px;text-transform:uppercase;letter-spacing:.05em">${r.gueltig_bis ? `Frühere Anschrift · bis ${dt(r.gueltig_bis)}` : `Aktuelle Anschrift · seit ${dt(r.gueltig_von)}`}</b><div class="lines">${esc(r.zeilen)}</div>${r.verwendet ? `<small>Bei ${r.verwendet} Versand${r.verwendet === 1 ? '' : 'en'} verwendet</small>` : ''}</div>`).join('')}</div>` : '<p class="muted" style="margin:0">Noch keine Anschrift.</p>'}</div>`).join('')}
    <div class="panel"><h3>Vorgänge</h3><ul class="mini" style="margin-top:6px">${k.vorgaenge.map(v => `<li><a href="#akte-${v.id}">${esc(v.titel)}</a><span class="muted">${esc(v.rolle)}</span></li>`).join('') || '<li class="muted">Keine.</li>'}</ul></div></div>` : '<div class="panel muted">Noch keine Kontakte. Sie entstehen auch beim Zuordnen aus dem Posteingang.</div>'}</div>`;
}

// ---------- Papierkorb & Einstellungen ----------
function vTrash() {
  return `<h1>Papierkorb</h1><p class="muted" style="margin:6px 0 16px">Gelöschte Vorgänge, Dokumente, Einträge, Fristen und Kontakte lassen sich hier wiederherstellen.</p>
  <div class="panel">${D.trash.length ? D.trash.map(t => `<div class="frow" style="grid-template-columns:minmax(0,1fr) auto"><div style="min-width:0"><div class="t">${esc(t.bezeichnung)}</div><div class="m"><span class="pill grey" style="font-size:12px;padding:1px 7px">${esc({vorgang:'Vorgang',dokument:'Dokument',eintrag:'Eintrag',frist:'Frist',kontakt:'Kontakt'}[t.typ])}</span>${t.vorgang ? `<span>aus ${esc(t.vorgang)}</span>` : ''}<span>· gelöscht am ${dt(t.geloescht_am)}</span></div></div>
   <div class="acts"><button class="btn sm" data-act="t-restore" data-typ="${t.typ}" data-id="${t.id}">${I('restore')}Wiederherstellen</button>${['eintrag','frist'].includes(t.typ) ? `<button class="btn sm ghost" data-act="t-purge" data-typ="${t.typ}" data-id="${t.id}">Endgültig löschen</button>` : ''}</div></div>`).join('') : '<p class="muted" style="margin:0">Der Papierkorb ist leer.</p>'}</div>`;
}
function vSettings() {
  return `<h1>Einstellungen</h1><div class="grid2" style="margin-top:16px">
   <div class="panel stack"><div class="chron-h"><h2>Bereiche</h2><button class="btn sm" data-act="b-add">${I('plus')}Bereich</button></div>
    <ul class="mini">${D.groups.map(b => { const n = D.cases.filter(c => c.bereich === b).length; return `<li><span>${esc(b)} <span class="muted">· ${n} ${n === 1 ? 'Vorgang' : 'Vorgänge'}</span></span><span style="display:flex;gap:6px"><button class="iconbtn sm" data-act="b-hoch" data-b="${esc(b)}" title="Nach oben" aria-label="${esc(b)} nach oben">↑</button><button class="iconbtn sm" data-act="b-runter" data-b="${esc(b)}" title="Nach unten" aria-label="${esc(b)} nach unten">↓</button><button class="btn sm ghost" data-act="b-ren" data-b="${esc(b)}">Umbenennen</button>${n ? '' : `<button class="btn sm ghost" data-act="b-del" data-b="${esc(b)}">Entfernen</button>`}</span></li>`; }).join('')}</ul></div>
   <div class="panel stack"><div class="chron-h"><h2>Eintragsarten</h2><button class="btn sm" data-act="art-neu">${I('plus')}Art</button></div>
    <p style="margin:0" class="muted">Eigene Arten für die Chronik, z. B. Besprechung oder Ortstermin. Die eingebauten Arten (Eingang, Versendet, Telefonat, Notiz …) bleiben immer.</p>
    <ul class="mini">${(D.arten || []).map(t => `<li><span>${esc(t)}</span><button class="btn sm ghost" data-act="art-del" data-name="${esc(t)}">Entfernen</button></li>`).join('') || '<li class="muted">Noch keine eigenen Arten.</li>'}</ul></div>
   <div class="panel stack"><h2>ChatGPT-Lesezeichen</h2><p style="margin:0">Übernimmt den in ChatGPT geöffneten Chat samt hochgeladener Dateien. Einrichten: Lesezeichenleiste einblenden (Safari: Darstellung → Favoritenleiste einblenden; Chrome: ⇧⌘B), dann den Knopf hineinziehen.</p>
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><a class="btn pri" id="lz-link" href="#" onclick="event.preventDefault();toast('Bitte in die Lesezeichenleiste ziehen, nicht anklicken.')">→ DocuManager</a><button class="btn sm ghost" data-act="lz-kopieren">Adresse kopieren</button></div>
    <p class="muted" style="margin:0;font-size:12.5px">Benutzung: Chat in ChatGPT im Browser öffnen (nicht in der ChatGPT-App), Lesezeichen anklicken, im DocuManager-Fenster Vorgang und Dateien wählen. Klappt das Ziehen nicht: „Adresse kopieren“, ein beliebiges Lesezeichen anlegen und dessen Adresse durch die kopierte ersetzen.</p></div>
   <div class="panel stack"><h2>Zulässige Empfänger</h2><p style="margin:0">Für wen Post ankommt, z. B. Ihre Firma und Sie persönlich, ein Name pro Zeile. Die Erkennung ordnet jedes Schreiben dem Empfänger zu, der im Anschriftenfeld steht; im Archiv lässt sich danach gruppieren.</p>
    <textarea id="empflist" class="inp" rows="3" placeholder="Orbit Cross media e.K.&#10;Sven Muster">${esc((D.empfaenger || []).join('\n'))}</textarea><div><button class="btn" data-act="empf-save">Speichern</button></div></div>
   <div class="panel stack"><h2>Claude (KI-Analyse)</h2><p style="margin:0">Mit einem eigenen Zugangsschlüssel von Anthropic analysiert Claude Schreiben und entwirft Antworten – direkt im Vorgang über die Schaltfläche „Claude“. Den Schlüssel erstellen Sie unter <b>console.anthropic.com</b> → API Keys (Guthaben nötig; eine Analyse kostet meist wenige Cent).</p>
    ${D.claude && D.claude.eingerichtet ? `<p style="margin:0">${I('check')} Eingerichtet · Schlüssel endet auf <code>…${esc(D.claude.endung)}</code></p><div style="display:flex;gap:8px"><button class="btn" data-act="claude-key">Schlüssel ändern</button><button class="btn ghost" data-act="claude-key-del">Entfernen</button></div>`
      : `<div style="display:flex;gap:8px;flex-wrap:wrap"><input id="claudekey" class="inp" type="password" autocomplete="off" placeholder="sk-ant-…" style="flex:1;min-width:240px"><button class="btn" data-act="claude-key-save">Speichern</button></div>`}
    ${D.claude && D.claude.eingerichtet ? `<label class="chk" style="flex-direction:column;align-items:flex-start;gap:4px">Qualität und Kosten<select id="claudestufe" class="inp" style="max-width:420px">${[['gruendlich', 'Gründlich – Standard, bestes Ergebnis für Rechtsfragen'], ['ausgewogen', 'Ausgewogen – etwa halber Preis'], ['sparsam', 'Sparsam – sehr günstig, nur für einfache Zusammenfassungen']].map(([k, l]) => `<option value="${k}" ${D.claude.stufe === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>` : ''}
    <p class="muted" style="margin:0;font-size:12.5px">Kosten sparen: Die Akte wird nach der ersten Anfrage 5 Minuten zwischengespeichert. Bewertung, Entwurf und Folgefragen kurz hintereinander kosten deshalb nur einen Bruchteil. Unter jeder Antwort steht, was sie gekostet hat.</p>
    <p class="muted" style="margin:0;font-size:12.5px">Übertragen wird nur, wenn Sie Claude fragen: der Text des gewählten Dokuments, gekürzte Texte der übrigen Dokumente und die Chronik des Vorgangs. Der Schlüssel liegt nur auf diesem Mac in <code>Daten/claude_schluessel</code> und ist nicht Teil der Datensicherung.</p></div>
   <div class="panel stack"><h2>Eigene Angaben</h2><p style="margin:0">Ihr Name und Ihre Anschrift, eine Angabe pro Zeile. Die Absendererkennung schlägt diese Angaben nie als Absender vor.</p>
    <textarea id="eigene" class="inp" rows="4">${esc(D.eigene)}</textarea><div><button class="btn" data-act="eigene-save">Speichern</button></div></div>
   <div class="panel stack"><h2>Apple Mail</h2><p style="margin:0">„Aus Mail holen“ übernimmt alle E-Mails mit dieser Markierung samt Anlagen in den Posteingang. Die Markierung in Mail bleibt; jede E-Mail wird nur einmal übernommen, auch wenn sie in mehreren Postfächern liegt.</p>
    <label class="chk" style="flex-direction:column;align-items:flex-start;gap:4px">Markierung<select id="mailflag" class="inp" style="max-width:240px">${Object.entries(D.mail.farben).map(([k, l]) => `<option value="${k}" ${+k === D.mail.markierung ? 'selected' : ''}>${esc(l)}${+k === 6 ? ' (bei Ihnen „Erfasster Beleg“)' : ''}</option>`).join('')}</select></label>
    <p class="muted" style="margin:0;font-size:12.5px">${D.mail.uebernommen} E-Mails übernommen${D.mail.zuletzt ? ', zuletzt am ' + dt(D.mail.zuletzt) : ''}.${D.mail.letzter_abruf ? ` Letzter Abruf: ${dt(D.mail.letzter_abruf.zeit.slice(0, 10))}, ${D.mail.letzter_abruf.zeit.slice(11, 16)} Uhr (${D.mail.letzter_abruf.neu} neu).` : ''}${D.mail.verfuegbar ? '' : ' Nur auf dem Mac verfügbar.'} Beim ersten Abruf fragt macOS, ob die Anwendung Mail steuern darf.</p>
    <div><button class="btn" data-act="mail-get">${I('mail')}Jetzt aus Mail holen</button></div></div>
   <div class="panel stack"><h2>Scannen</h2><p style="margin:0">Erscheint Ihr Scanner im Scan-Dialog nicht, scannen Sie mit „Digitale Bilder“ von macOS oder der Software des Herstellers in diesen Ordner. Neue Dateien darin kommen nach wenigen Sekunden in den Posteingang und werden danach in „Übernommen“ verschoben.</p>
    <div class="src">${esc(D.scanordner ? D.scanordner.pfad : '')}</div><div><button class="btn" data-act="scan-folder">Ordner im Finder öffnen</button></div></div>
   <div class="panel stack"><h2>Datensicherung</h2><p style="margin:0">Eine Sicherung enthält Datenbank, alle Originale und Chat-Anlagen sowie eine Prüfliste. Es gibt immer nur eine Sicherungsdatei: Eine neue ersetzt die vorige. Sie liegt in <code>Daten/Sicherungen</code>; laden Sie sie herunter und kopieren Sie sie auf ein NAS oder einen externen Datenträger.</p>
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" data-act="backup">Sicherung erstellen</button><button class="btn" data-act="restore-file">${I('restore')}Sicherung wiederherstellen …</button></div>
    ${D.sicherungen && D.sicherungen.length ? `<ul class="mini">${D.sicherungen.map(b => `<li><span>${esc(b.name.replace('Korrespondenz-Sicherung_', '').replace('.zip', '').replace('_', ' '))} <span class="muted">· ${groesse(b.groesse)}</span></span><span style="display:flex;gap:6px"><button class="btn sm ghost" data-act="backup-check" data-name="${esc(b.name)}">Prüfen</button><button class="btn sm ghost" data-act="restore-list" data-name="${esc(b.name)}">Wiederherstellen</button><a class="btn sm" href="/api/sicherungen/${esc(b.name)}">Herunterladen</a></span></li>`).join('')}</ul>` : '<p class="muted" style="margin:0">Noch keine Sicherung.</p>'}
    <p class="muted" style="margin:0;font-size:12.5px">„Sicherung wiederherstellen …“ lädt eine Sicherungsdatei (.zip) von Ihrem Mac, zum Beispiel vom externen Datenträger.</p></div></div>`;
}

// ---------- Dialoge, Meldungen, Originalansicht ----------
let modalSave = null;
function modal(title, html, onSave, saveLabel = 'Speichern', cls = '') {
  $('#modalroot').innerHTML = `<div class="ovl" data-act="m-bg"><div class="modal ${cls}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><h2>${esc(title)}</h2>${html}<div class="foot"><button class="btn" data-act="m-close">Abbrechen</button>${onSave ? `<button class="btn pri" data-act="m-save">${saveLabel}</button>` : ''}</div></div></div>`;
  modalSave = onSave; setTimeout(() => document.querySelector('.modal input,.modal select,.modal textarea')?.focus(), 20);
}
const closeModal = () => { $('#modalroot').innerHTML = ''; modalSave = null; };
let toastTimer;
let toastAktion = null;
function toast(m, aktion, fn) {
  const t = $('#toast'); t.textContent = m; toastAktion = null;
  if (aktion && fn) { toastAktion = fn; const b = document.createElement('button'); b.className = 'toastknopf'; b.dataset.act = 'toast-aktion'; b.textContent = aktion; t.append(' ', b); }
  t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; toastAktion = null; }, aktion ? 7000 : 3800);
}
const istMail = id => [...D.inbox, ...(D.akte?.dokumente || []), ...D.archiv].some(d => d.id === +id && d.mime === 'message/rfc822');
async function mailTexte() {  // E-Mails zeigen ihren Text statt der Rohdatei
  for (const box of document.querySelectorAll('.mailtext[data-mail]')) {
    const id = box.dataset.mail; box.removeAttribute('data-mail');
    try { const r = await api(`documents/${id}/pages`); box.textContent = r.pages.map(p => p.text).join('\n\n'); } catch (e) { box.textContent = e.message; }
  }
}
function openViewer(docId, title) {
  if (istMail(docId)) { modal(title || 'E-Mail', `<div class="notecard mailtext" data-mail="${docId}" style="white-space:pre-wrap;max-height:65vh;overflow:auto">Wird geladen …</div><div><a class="btn sm" href="/api/documents/${docId}/original" download>Original (.eml) speichern</a></div>`, null, '', 'wide'); mailTexte(); return; }
  const w = $('#viewer');
  w.innerHTML = `<div class="vbar"><b>${esc(title || 'Original')}</b><a class="btn sm" href="/api/documents/${docId}/original" target="_blank" rel="noopener">In neuem Fenster</a><button class="btn sm" data-act="vw-close">Schließen</button></div>
   <div class="vbody" style="padding:0">${(() => { const d = [...D.inbox, ...(D.akte?.dokumente || []), ...D.archiv].find(x => x.id === +docId);
     return d && d.mime === 'application/pdf' ? `<div class="seiten" data-pdf="${docId}" data-rot="0">Wird geladen …</div>` : originalHtml(d || {id: docId}, 'Original', true); })()}</div>`;
  w.hidden = false; w.querySelector('[data-act=vw-close]').focus();
  const d = [...D.inbox, ...(D.akte?.dokumente || []), ...D.archiv].find(x => x.id === +docId);
  requestAnimationFrame(() => { drehungAnwenden(w); const box = w.querySelector('.seiten'); if (box) seitenAnzeigen(box, `/api/documents/${docId}/original`, d?.drehung_manuell || 0); });
}
const closeViewer = () => { const w = $('#viewer'); w.hidden = true; w.innerHTML = ''; };
const bereichSelect = (id, cur) => `<label>Bereich<select id="${id}">${D.groups.map(b => `<option ${b === cur ? 'selected' : ''}>${esc(b)}</option>`).join('')}</select></label>`;
const teilSelect = (id, cur, mitAlle) => D.akte && D.akte.teilvorgaenge.length ? `<label>Teilvorgang<select id="${id}">${mitAlle ? '<option value="">Ganzer Vorgang</option>' : ''}${D.akte.teilvorgaenge.map(t => `<option value="${t.id}" ${t.id === cur ? 'selected' : ''}>${esc(t.name)}</option>`).join('')}</select></label>` : '';

async function act(fn, msg) { try { await fn(); if (msg) toast(msg); await render(); return true; } catch (e) { toast(e.message); return false; } }

function newVorgang(after) {
  modal('Neuer Vorgang', `<label>Titel<input id="m-vt" maxlength="160" placeholder="z. B. Einkommensteuer 2026"></label><div class="two">${bereichSelect('m-vb', 'Anderes')}<label>Status<select id="m-vs">${statusOptions('Offen')}</select></label></div>
   <label>Beschreibung (optional)<textarea id="m-vd" rows="2"></textarea></label>`, async () => {
    const titel = val('m-vt').trim(); if (!titel) { $('#m-vt').focus(); return false; }
    try { const r = await api('cases', {title: titel, group: val('m-vb'), status: val('m-vs'), description: val('m-vd')}); closeModal(); if (after) await after(r.id); else { location.hash = 'akte-' + r.id; } toast('Vorgang angelegt.'); }
    catch (e) { toast(e.message); }
    return false;
  }, 'Anlegen');
}
function entryModal(bezugId) {
  const a = D.akte, bezug = bezugId ? a.eintraege.find(e => e.id === bezugId) : null;
  modal(bezug ? 'Antwort-Entwurf anlegen' : 'Eintrag hinzufügen', `${bezug ? `<div class="src">Bezug: ${esc(bezug.titel)} vom ${dt(bezug.ereignis_datum)}</div>` : ''}
   <div class="two"><label>Art<select id="m-ea">${(bezug ? [['entwurf','Entwurf']] : [['telefonat','Telefonat'],['notiz','Notiz'],['entscheidung','Entscheidung'],['entwurf','Entwurf'],['fehlt','Original fehlt'],['chat','Chat-Notiz'], ...(D.arten || []).map(t => ['typ:' + t, t]), ['__neu', '+ Neue Art …']]).map(([k, l]) => `<option value="${esc(k)}">${esc(l)}</option>`).join('')}</select></label><label>Ereignisdatum<input id="m-ed" type="date" value="${isoHeute()}"></label></div>
   <label>Titel<input id="m-et" maxlength="200" value="${bezug ? esc('Antwort: ' + bezug.titel) : ''}"></label><label>Inhalt<textarea id="m-ex" rows="5"></textarea></label>
   <div class="two">${a.teilvorgaenge.length ? `<label>Teilvorgang<select id="m-etl"><option value="">Ganzer Vorgang</option>${a.teilvorgaenge.map(t => `<option value="${t.id}" ${(bezug ? bezug.teile[0] : S.teil) === t.id ? 'selected' : ''}>${esc(t.name)}</option>`).join('')}</select></label>` : ''}
   <label>Beteiligter<select id="m-ek"><option value="">–</option>${a.beteiligte.map(b => `<option value="${b.kontakt_id}" ${bezug && bezug.kontakt_id === b.kontakt_id ? 'selected' : ''}>${esc(b.kurzname || b.name)}</option>`).join('')}</select></label></div>
   <p class="muted" style="margin:0;font-size:13px">Liegt das Ereignisdatum in der Vergangenheit, wird der Eintrag als nacherfasst gekennzeichnet.</p>`, async () => {
    const titel = val('m-et').trim(); if (!titel) { $('#m-et').focus(); return false; }
    const wahl = val('m-ea'), k = val('m-ek'), typ = wahl.startsWith('typ:') ? wahl.slice(4) : null, art = typ ? 'notiz' : wahl;
    if (wahl === '__neu') { toast('Bitte zuerst die neue Art benennen.'); return false; }
    const body = {art, typ, titel, datum: val('m-ed'), text: val('m-ex'), teile: val('m-etl') ? [+val('m-etl')] : [], kontakt_id: k ? +k : null,
      richtung: k ? (art === 'entwurf' ? 'an' : 'mit') : null, bezug_id: bezug ? bezug.id : null, quelle: art === 'chat' ? 'Chat' : null};
    closeModal(); await act(async () => { const r = await api(`akte/${a.id}/eintraege`, body); S.entry = r.id; }, 'Eintrag angelegt.');
    return false;
  }, 'Anlegen');
}
// ---------- Claude: Analyse und Textvorschläge ----------
const CLAUDE_AKTIONEN = [['zusammenfassen', 'Zusammenfassen'], ['fristen', 'Fristen & Pflichten'], ['pruefen', 'Prüfen & Einschätzen'], ['antwort', 'Antwort entwerfen']];
const CLAUDE_FRAGEN = {zusammenfassen: 'Bitte zusammenfassen.', fristen: 'Welche Fristen und Pflichten ergeben sich?', pruefen: 'Bitte kritisch prüfen und einschätzen.', antwort: 'Bitte eine Antwort entwerfen.'};
// Zitierte Vorschriften anklickbar machen (gleiche Gesetzesliste wie gesetze.py)
const NORM_RE = /(?:§§?|Art\.|Artikel)\s*\d+[a-z]?(?:\s*(?:Abs\.|Absatz|S\.|Satz|Nr\.|Ziff\.|lit\.|,|und|bis|–|-|\/)\s*\d+[a-z]?)*\s*(?:ff?\.\s*)?(?:HeizkostenV|KraftStG|SGB VIII|SGB III|SGB VII|SGB XII|ErbStG|BetrKV|EntgFG|SGB II|SGB IV|SGB VI|SGB IX|SGB XI|EGBGB|EGZPO|FamFG|VwVfG|GrStG|PflVG|GmbHG|PAngV|BauGB|TDDDG|KSchG|ArbGG|TzBfG|BUrlG|MiLoG|SGB I|SGB V|SGB X|InsO|JVEG|VwGO|VwZG|EStG|UStG|StGB|StPO|OWiG|StVG|StVO|BDSG|EnWG|GewO|BEEG|BKGG|WoGG|IfSG|BGB|ZPO|GVG|ZVG|GKG|RVG|FGO|VVG|HGB|UWG|WEG|TKG|SGG|GG|AO)(?![A-Za-zÄÖÜäöü])/g;
const normLinks = h => h.replace(NORM_RE, z => `<button type="button" class="norm" data-act="norm" data-z="${z}" title="Gesetzestext anzeigen">${z}</button>`);
function claudeText(t) {  // knappe Darstellung von Markdown: Absätze, Listen, Fett, Gesetzeszitate als Verweis
  return normLinks(esc(t).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/^#{1,4} (.+)$/gm, '<b>$1</b>').replace(/^[-*] /gm, '• '));
}
async function normZeigen(zitat) {  // Gesetzestext im Seitenfenster, ohne den offenen Dialog zu schließen
  let p = $('#normpop');
  if (!p) { p = document.createElement('aside'); p.id = 'normpop'; p.setAttribute('aria-label', 'Gesetzestext'); document.body.append(p); }
  p.hidden = false; p.innerHTML = `<div class="np-kopf"><b>${esc(zitat)}</b><button type="button" class="iconbtn" data-act="norm-zu" aria-label="Schließen">✕</button></div><p class="muted">Wird geladen …</p>`;
  try {
    const r = await api('gesetze', {text: zitat});
    p.innerHTML = `<div class="np-kopf"><b>${esc(zitat)}</b><button type="button" class="iconbtn" data-act="norm-zu" aria-label="Schließen">✕</button></div>` + (r.vorschriften.map(v => `<section>
      <h4>${esc(v.titel || v.norm + ' ' + v.gesetz)} <span class="muted">${esc(v.gesetz)}</span></h4>
      ${v.fehler ? `<p class="kiwarn">${esc(v.fehler)}</p>` : v.absaetze.map(a => `<p class="${v.absatz && a.startsWith('(' + v.absatz + ')') ? 'np-treffer' : ''}">${esc(a)}</p>`).join('')}
      ${v.veraltet ? '<p class="muted">Gespeicherter Stand, aktueller Abruf nicht möglich.</p>' : ''}
      <a href="${esc(v.url)}" target="_blank" rel="noopener">Auf gesetze-im-internet.de öffnen</a></section>`).join('') || '<p class="muted">Keine Vorschrift erkannt.</p>')
      + '<p class="muted np-quelle">Quelle: gesetze-im-internet.de (Bundesministerium der Justiz). Amtlicher Wortlaut, ohne Rechtsprechung.</p>';
  } catch (e) { p.querySelector('.muted').textContent = e.message; }
}
function zitatErgebnis(r) {  // Ergebnis der Gegenprüfung
  const sym = {passt: ['✓', 'ok'], teilweise: ['!', 'teil'], 'passt nicht': ['✗', 'falsch'], unklar: ['?', 'teil']};
  const fehlt = r.vorschriften.filter(v => v.fehler);
  return `<div class="zitpruef"><b>Zitate am Gesetzestext geprüft</b>${r.pruefungen.map(p => `<div class="zp ${(sym[p.ergebnis] || sym.unklar)[1]}">
    <span class="zp-sym">${(sym[p.ergebnis] || sym.unklar)[0]}</span><span>${normLinks(esc(p.vorschrift))} – <b>${esc(p.ergebnis)}</b>: ${esc(p.begruendung)}</span></div>`).join('')}
    ${fehlt.length ? `<p class="muted">Nicht abrufbar: ${fehlt.map(v => esc(v.norm + ' ' + v.gesetz)).join(', ')}</p>` : ''}
    ${r.kosten_usd !== undefined ? `<p class="muted">Kosten ca. ${r.kosten_usd < 0.01 ? 'unter 1 Cent' : (r.kosten_usd * 100).toFixed(1).replace('.', ',') + ' Cent'}</p>` : ''}</div>`;
}
async function zitatePruefen(text, ziel, knopf) {
  const alt = knopf.innerHTML; knopf.disabled = true; knopf.innerHTML = '<span class="spin"></span>Prüfe Zitate …';
  try { const r = await api('claude/zitate', {text}); ziel.innerHTML = zitatErgebnis(r); ziel.hidden = false; }
  catch (e) { toast(e.message); }
  knopf.disabled = false; knopf.innerHTML = alt;
}
function kontextHinweis(k) {  // zeigt, welche Teile der Akte Claude vorlagen
  if (!k) return '';
  const teile = [`${k.eintraege} Einträge der Akte`, `${k.eigene_schreiben} eigene Schreiben`, `${k.dokumente} Dokumente im Volltext`];
  const warn = [];
  if (k.gekuerzt && k.gekuerzt.length) warn.push(`Wegen der Größe der Akte nur gekürzt: ${k.gekuerzt.map(esc).join(', ')}`);
  if (k.ohne_text) warn.push(`${k.ohne_text} Dokument(e) ohne erkannten Text – Inhalt lag Claude nicht vor`);
  const kosten = k.kosten_usd !== undefined ? ` <span class="ck-kosten">· ${esc(k.stufe || '')}, Kosten ca. ${k.kosten_usd < 0.01 ? 'unter 1 Cent' : (k.kosten_usd * 100).toFixed(1).replace('.', ',') + ' Cent'}${k.aus_speicher ? ', Akte aus dem Zwischenspeicher' : ''}</span>` : '';
  return `<p class="ck-kontext ${warn.length ? 'warn' : ''}">${warn.length ? I('alert') : I('check')}<span>Berücksichtigt: ${teile.join(' · ')}${warn.length ? '. ' + warn.join('. ') + '.' : ' – vollständig.'}${kosten}</span></p>`;
}
async function claudeDialog(docId, entryId) {
  const a = D.akte;
  if (!D.claude) D.claude = await api('claude');
  if (!D.claude.eingerichtet) {
    modal('Claude einrichten', `<p style="margin:0">Für die Analyse mit Claude brauchen Sie einen eigenen Zugangsschlüssel von Anthropic (console.anthropic.com → API Keys).</p>
      <label>Zugangsschlüssel<input id="m-ck" type="password" autocomplete="off" placeholder="sk-ant-…"></label>
      <p class="muted" style="margin:0;font-size:12.5px">Der Schlüssel bleibt auf diesem Mac. Übertragen wird nur, wenn Sie Claude etwas fragen.</p>`, async () => {
      try { D.claude = await api('claude/schluessel', {schluessel: val('m-ck')}); } catch (e) { toast(e.message); return false; }
      closeModal(); claudeDialog(docId, entryId); return false;
    }, 'Speichern und weiter');
    return;
  }
  const d = docId ? a.dokumente.find(x => x.id === docId) : null, e = entryId ? a.eintraege.find(x => x.id === entryId) : null;
  const verlauf = [];  // {rolle, text, anzeige, brief}
  modal('Claude · ' + (d ? d.titel : a.titel), `<div class="claude">
    <p class="muted" style="margin:0;font-size:12.5px">Grundlage: die ganze Akte „${esc(a.titel)}“ in zeitlicher Reihenfolge – alle Schreiben im Volltext, Ihre eigenen Briefe und Entwürfe, Notizen und Telefonate${d ? `; im Mittelpunkt „${esc(d.titel)}“` : ''}. Claude kann sich irren – Fristen und Beträge bitte am Original prüfen.</p>
    <div class="claude-akt">${CLAUDE_AKTIONEN.map(([k, l]) => `<button class="btn sm" data-ck="${k}">${l}</button>`).join('')}</div>
    <div class="claude-verlauf" id="ck-verlauf"><p class="muted" style="margin:auto;text-align:center">Wählen Sie oben eine Aufgabe oder stellen Sie unten eine eigene Frage.</p></div>
    <div class="claude-ein"><textarea id="ck-frage" rows="2" placeholder="Eigene Frage, z. B. „Muss ich zahlen?“ oder „Formuliere den zweiten Absatz freundlicher.“"></textarea><button class="btn pri" data-ck="frage">Fragen</button></div></div>`, null, '', 'wide');
  const box = document.querySelector('.modal'), feld = $('#ck-verlauf');
  const zeigen = () => {
    feld.innerHTML = verlauf.map((n, i) => n.rolle === 'user' ? `<div class="ck-frage">${esc(n.anzeige || n.text)}</div>`
      : `<div class="ck-antwort"><div class="ck-text">${claudeText(n.text)}</div><div class="ck-knoepfe">
          <button class="btn sm ghost" data-ckn="notiz" data-i="${i}">Als Notiz speichern</button>
          <button class="btn sm ghost" data-ckn="brief" data-i="${i}">${I('draft')}Als Brief übernehmen</button>
          <button class="btn sm ghost" data-ckn="kopie" data-i="${i}">Kopieren</button>
          ${NORM_RE.test(n.text) && !(NORM_RE.lastIndex = 0) ? `<button class="btn sm ghost" data-ckn="zitate" data-i="${i}">Zitate prüfen</button>` : ''}</div>
          <div class="ck-zit" data-zit="${i}" ${n.zitate ? '' : 'hidden'}>${n.zitate || ''}</div>${kontextHinweis(n.kontext)}</div>`).join('')
      + (box.dataset.laeuft ? '<div class="ck-antwort muted"><span class="spin"></span> Claude denkt nach … (kann bis zu einer Minute dauern)</div>' : '');
    feld.scrollTop = feld.scrollHeight;
  };
  const fragen = async (aufgabe) => {
    if (box.dataset.laeuft) return;
    let text = aufgabe === 'frage' ? $('#ck-frage').value.trim() : CLAUDE_FRAGEN[aufgabe];
    if (!text) { $('#ck-frage').focus(); return; }
    const gesendet = verlauf.filter(n => !n.fehler).map(n => ({rolle: n.rolle, text: n.text}));
    if (aufgabe === 'frage') gesendet.push({rolle: 'user', text});
    verlauf.push({rolle: 'user', text, anzeige: text}); if (aufgabe === 'frage') $('#ck-frage').value = '';
    box.dataset.laeuft = '1'; zeigen();
    try {
      const r = await api('claude/fragen', {vorgang_id: a.id, dokument_id: docId, verlauf: gesendet, aufgabe});
      verlauf.push({rolle: 'assistant', text: r.text, kontext: r.kontext, brief: r.brieftext ? {betreff: r.betreff, brieftext: r.brieftext, hinweise: r.hinweise} : null});
      if (aufgabe !== 'frage') verlauf[verlauf.length - 2].text = text;  // im Verlauf für Folgefragen steht die eigentliche Aufgabe
    } catch (err) { verlauf.pop(); toast(err.message); }
    delete box.dataset.laeuft; if (document.body.contains(feld)) zeigen();
  };
  box.addEventListener('click', async ev => {
    const k = ev.target.closest('[data-ck]'), n = ev.target.closest('[data-ckn]');
    if (k) fragen(k.dataset.ck);
    if (!n) return;
    const m = verlauf[+n.dataset.i];
    if (n.dataset.ckn === 'zitate') { const ziel = feld.querySelector(`[data-zit="${n.dataset.i}"]`); await zitatePruefen(m.text, ziel, n); m.zitate = ziel.innerHTML; return; }
    if (n.dataset.ckn === 'kopie') { try { await navigator.clipboard.writeText(m.text); toast('Kopiert.'); } catch (_) { toast('Kopieren nicht möglich.'); } }
    else if (n.dataset.ckn === 'notiz') {
      try { await api(`akte/${a.id}/eintraege`, {art: 'notiz', titel: ('Claude: ' + (verlauf[+n.dataset.i - 1]?.anzeige || 'Analyse') + (d ? ' – ' + d.titel : '')).slice(0, 190), text: m.text, bezug_id: e ? e.id : null, teile: e ? e.teile : []});
        toast('Als Notiz in der Chronik gespeichert.'); n.disabled = true; await render(); } catch (err) { toast(err.message); }
    } else if (n.dataset.ckn === 'brief') {
      const v = m.brief || {betreff: '', brieftext: m.text, hinweise: ''};
      closeModal(); compose(e && e.art === 'eingang' ? e.id : null, null, v);
    }
  });
  box.addEventListener('keydown', ev => { if (ev.target.id === 'ck-frage' && ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) fragen('frage'); });
}
function versandModal(e) {
  const a = D.akte, k = D.kontakte.find(x => x.id === e.kontakt_id);
  const ziele = k ? k.abteilungen.flatMap(ab => ab.anschriften.filter(r => !r.gueltig_bis).map(r => ({id: r.id, text: r.zeilen}))) : [];
  modal('Versand erfassen', `<div class="two"><label>Versandart<select id="m-va">${VERSAND.map(v => `<option>${v}</option>`).join('')}</select></label><label>Versanddatum<input id="m-vd" type="date" value="${isoHeute()}"></label></div>
   <label>Sendungsnummer (optional)<input id="m-vn"></label><label>Empfänger</label>
   ${ziele.map((z, i) => `<label class="radio"><input type="radio" name="m-adr" value="${z.id}" ${i === 0 ? 'checked' : ''}><span class="lines">${esc(z.text)}</span></label>`).join('')}
   <label class="radio"><input type="radio" name="m-adr" value="frei" ${ziele.length ? '' : 'checked'}><span style="flex:1">Andere Anschrift oder E-Mail<textarea id="m-vf" rows="3" class="inp" style="margin-top:6px"></textarea></span></label>
   <p class="muted" style="margin:0;font-size:13px">Die verwendete Anschrift wird mit dem Versand gespeichert und bleibt erhalten, auch wenn sie sich im Adressbuch später ändert.</p>`, async () => {
    const wahl = document.querySelector('input[name=m-adr]:checked').value;
    const body = {art: val('m-va'), datum: val('m-vd'), sendungsnummer: val('m-vn')};
    if (wahl === 'frei') { body.empfaenger = val('m-vf'); if (!body.empfaenger.trim()) { $('#m-vf').focus(); return false; } } else body.anschrift_id = +wahl;
    closeModal(); await act(async () => { const r = await api(`eintraege/${e.id}/versand`, body); S.entry = r.id; }, 'Versand erfasst. Status: Schreiben abgeschickt.');
    return false;
  }, 'Versand speichern');
}
function dokVerschieben(docId, vonId, titel) {
  modal('Vorgang ändern', `<p style="margin:0">„${esc(titel || 'Dokument')}“ samt Chronik-Eintrag in einen anderen Vorgang verschieben.</p>
   <label>Neuer Vorgang<select id="m-mv">${vorgangOptionen(null, vonId)}<option value="__new">+ Neuer Vorgang …</option><option value="ablage">Ohne Vorgang (nur Archiv)</option></select></label>
   <p class="muted" style="margin:0;font-size:12.5px">Fristen aus diesem Dokument bleiben im bisherigen Vorgang. Ist der Ziel-Vorgang erledigt, steht das Dokument im Archiv.</p>`, async () => {
    const ziel = val('m-mv'); closeModal();
    if (ziel === '__new') { newVorgang(async nv => { try { await api(`dokumente/${docId}/verschieben`, {von_vorgang_id: vonId, vorgang_id: nv}); toast('In den neuen Vorgang verschoben.'); S.v = nv; S.tab = 'chronik'; S.teil = 'all'; S.entry = null; location.hash = 'akte-' + nv; } catch (e) { toast(e.message); } }); return false; }
    try {
      const r = await api(`dokumente/${docId}/verschieben`, ziel === 'ablage' ? {von_vorgang_id: vonId, ablage: true} : {von_vorgang_id: vonId, vorgang_id: +ziel});
      toast(r.ablage ? 'Ohne Vorgang ins Archiv gelegt.' : r.archiviert ? 'Verschoben. Der Vorgang ist erledigt, das Dokument steht im Archiv.' : 'In den Vorgang verschoben.');
      if (!r.ablage && !r.archiviert) { S.v = r.vorgang_id; S.tab = 'chronik'; S.teil = 'all'; S.entry = null; location.hash = 'akte-' + r.vorgang_id; } else await render();
    } catch (e) { toast(e.message); }
    return false;
  }, 'Verschieben');
}
function neuerKontakt(docId) {
  const p = D.inbox.find(x => x.id === docId), vor = p?.vorschlag?.absender;
  modal('Neuer Kontakt', `<label>Name der Organisation oder Person<input id="m-nkn" maxlength="160" value="${esc(vor ? vor.name : '')}"></label>
   <div class="two"><label>Ansprechpartner<input id="m-nkp"></label><label>E-Mail<input id="m-nke" type="email" value="${esc(vor?.email || '')}"></label></div>
   <label>Anschrift<textarea id="m-nka" rows="3">${esc(vor?.anschrift || '')}</textarea></label>`, async () => {
    const name = val('m-nkn').trim(); if (!name) { $('#m-nkn').focus(); return false; }
    closeModal();
    try { const r = await api('kontakte', {name, abteilungen: [{ansprechpartner: val('m-nkp'), email: val('m-nke'), anschrift: val('m-nka')}]});
      D.kontakte = (await api('kontakte')).kontakte; if (draft[docId]) draft[docId].kontakt = String(r.id); toast(`Kontakt „${name}“ angelegt und als Absender gewählt.`); await render(); }
    catch (e) { toast(e.message); }
    return false;
  }, 'Anlegen');
  const sel = document.querySelector(`select[data-ib=kontakt][data-id="${docId}"]`); if (sel) sel.value = draft[docId]?.kontakt || '';
}
function archivBearbeiten(docId) {
  const d = D.archiv.find(x => x.id === docId); if (!d) return;
  const kontakte = [...D.kontakte].sort((x, y) => cmp(x.name, y.name));
  modal('Dokument bearbeiten', `<label>Titel<input id="m-at" maxlength="160" value="${esc(d.titel)}"></label>
   <label>Dateiname<input id="m-an" maxlength="200" value="${esc(d.dateiname)}"></label>
   <div class="two"><label>Dokumentdatum<input id="m-ad" type="date" value="${esc(d.dokument_datum || d.datum || '')}"></label>
    <label>Absender<select id="m-ak"><option value="">– unbekannt –</option>${kontakte.map(k => `<option value="${k.id}" ${k.id === d.kontakt_id ? 'selected' : ''}>${esc(k.kurzname || k.name)}</option>`).join('')}</select></label></div>
   <label>Bereiche <small class="muted">· leer = Bereiche des Vorgangs${d.system === 'ablage' ? '' : ` (${esc((d.bereiche || []).join(', '))})`}</small></label>${mehrfach('m-abs', D.groups.map(b => [b, b]), d.eigene_bereiche || [], 'Bereich')}
   <label>Weitere Kontakte</label>${mehrfach('m-aks', kontaktOpt(), (d.kontakte || []).map(k => k.id), 'Kontakt')}
   <label>Empfänger <small class="muted">· zulässige Empfänger pflegen Sie in den Einstellungen</small><input id="m-aemp" list="m-aempl" maxlength="160" value="${esc(d.empfaenger || '')}"><datalist id="m-aempl">${(D.empfaenger || []).map(e => `<option value="${esc(e)}">`).join('')}</datalist></label>
   <div class="src" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><span style="flex:1;min-width:0">Vorgang: <b>${d.system === 'ablage' ? 'ohne Vorgang' : esc(d.vorgang)}</b>${d.system === 'ablage' ? '' : ` · <button class="linkbtn" data-act="arch-akte" data-v="${d.vorgang_id}" data-doc="${d.id}">Akte öffnen</button>`}</span>
    <button class="btn sm pri" data-act="arch-zuordnen" data-doc="${d.id}" data-v="${d.vorgang_id}" data-t="${esc(d.titel)}">${I('move')}Einem Vorgang zuordnen …</button><button class="btn sm" data-act="view" data-doc="${d.id}">Ansehen</button></div>
   <p class="muted" style="margin:0;font-size:12.5px">Die Originaldatei bleibt unverändert; der Dateiname gilt für Anzeige und Export.</p>`, async () => {
    const titel = val('m-at').trim(); if (!titel) { $('#m-at').focus(); return false; }
    try { await api(`dokumente/${docId}/aendern`, {titel, dateiname: val('m-an').trim(), datum: val('m-ad') || null, empfaenger: val('m-aemp').trim(), kontakt_id: val('m-ak') ? +val('m-ak') : null, bereiche: multiWert('m-abs'), kontakte: multiWert('m-aks').map(Number)}); closeModal(); toast('Gespeichert.'); await render(); }
    catch (e) { toast(e.message); }
    return false;
  }, 'Speichern');
}
function dokEntfernen(docId, vonId, titel) {
  const v = D.cases.find(c => c.id === vonId);
  modal('Dokument löschen', `<p style="margin:0">„${esc(titel || 'Dokument')}“ aus ${v ? `dem Vorgang „${esc(v.titel)}“` : 'dem Archiv'} löschen?</p>
   <p class="muted" style="margin:0;font-size:13px">Gehört es noch zu einem anderen Vorgang, bleibt es dort. Sonst kommt es in den Papierkorb und lässt sich von dort wiederherstellen.</p>`, async () => {
    closeModal();
    try { const r = await api(`dokumente/${docId}/entfernen`, {vorgang_id: vonId}); if (S.entry && D.akte?.eintraege.find(e => e.id === S.entry)?.dokument_id === docId) S.entry = null;
      toast(r.papierkorb ? 'In den Papierkorb verschoben.' : 'Aus diesem Vorgang entfernt; in den anderen Vorgängen bleibt es.'); await render(); } catch (e) { toast(e.message); }
    return false;
  }, 'Löschen');
}
function wiederherstellenFrage(name, datei) {
  modal('Sicherung wiederherstellen', `<p style="margin:0">Den Datenbestand durch die Sicherung <b>${esc(name || datei.name)}</b> ersetzen?</p>
   <div class="notice warn" style="margin:0">${I('alert')}<p>Alles, was nach dieser Sicherung erfasst wurde, ist danach nicht mehr in der Anwendung. Die bisherige Datenbank wird vorher als Kopie in <code>Daten/Sicherungen</code> abgelegt.</p></div>`, async () => {
    closeModal(); toast('Sicherung wird geprüft und wiederhergestellt …');
    try {
      let r;
      if (datei) { const res = await holen('/api/sicherungen/wiederherstellen', {method: 'POST', body: datei, headers: {'X-Korrespondenz': 'lokal'}}); r = await res.json(); if (!res.ok) throw new Error(r.error || 'Wiederherstellen fehlgeschlagen.'); }
      else r = await api(`sicherungen/${name}/wiederherstellen`, {});
      toast(`Wiederhergestellt: ${r.anzahl.vorgang} Vorgänge, ${r.anzahl.dokument} Dokumente.`); setTimeout(() => location.reload(), 1200);
    } catch (e) { toast(e.message); }
    return false;
  }, 'Wiederherstellen');
}
function fristNeu() {
  if (!aktiv().length) { toast('Legen Sie zuerst einen Vorgang an.'); return; }
  modal('Neue Frist', `<label>Vorgang<select id="m-nv">${aktiv().sort((x, y) => cmp(x.titel, y.titel)).map(c => `<option value="${c.id}">${esc(c.titel)}</option>`).join('')}</select></label>
   <div class="two"><label>Art<select id="m-fa"><option value="wiedervorlage">Wiedervorlage</option><option value="aufgabe">Aufgabe</option><option value="frist">Verbindliche Frist</option></select></label><label>Fällig am<input id="m-ff" type="date" value="${plusTage(isoHeute(), 14)}"></label></div>
   <label>Titel<input id="m-ft" maxlength="200"></label><label>Zuständig<input id="m-fz" value="Ich"></label>
   <label>Fundstelle oder Quellenvermerk (Pflicht bei verbindlicher Frist)<input id="m-fq" placeholder="z. B. „Stellungnahme bis zum 16.12.2026“, Schreiben vom 18.11., S. 1"></label>`, async () => {
    const titel = val('m-ft').trim(); if (!titel) { $('#m-ft').focus(); return false; }
    try { await api(`akte/${val('m-nv')}/fristen`, {art: val('m-fa'), titel, faellig_am: val('m-ff'), zustaendig: val('m-fz'), quelle_zitat: val('m-fq') || null}); closeModal(); toast('Frist eingetragen.'); await render(); } catch (e) { toast(e.message); }
    return false;
  }, 'Eintragen');
}
function fristModal() {
  const a = D.akte;
  modal('Frist oder Wiedervorlage', `<div class="two"><label>Art<select id="m-fa"><option value="wiedervorlage">Wiedervorlage</option><option value="aufgabe">Aufgabe</option><option value="frist">Verbindliche Frist</option></select></label><label>Fällig am<input id="m-ff" type="date" value="${plusTage(isoHeute(), 14)}"></label></div>
   <label>Titel<input id="m-ft" maxlength="200"></label><div class="two">${teilSelect('m-fteil', S.teil, true)}<label>Zuständig<input id="m-fz" value="Ich"></label></div>
   <label>Fundstelle oder Quellenvermerk (Pflicht bei verbindlicher Frist)<input id="m-fq" placeholder="z. B. „Stellungnahme bis zum 16.12.2026“, Schreiben vom 18.11., S. 1"></label>`, async () => {
    const titel = val('m-ft').trim(); if (!titel) { $('#m-ft').focus(); return false; }
    const body = {art: val('m-fa'), titel, faellig_am: val('m-ff'), zustaendig: val('m-fz'), quelle_zitat: val('m-fq') || null, teilvorgang_id: val('m-fteil') ? +val('m-fteil') : null};
    if (S.entry) { const e = a.eintraege.find(x => x.id === S.entry); if (e && e.dokument_id && body.quelle_zitat) body.quelle_dokument_id = e.dokument_id; }
    try { await api(`akte/${a.id}/fristen`, body); closeModal(); toast('Frist eingetragen.'); await render(); } catch (e) { toast(e.message); }
    return false;
  }, 'Eintragen');
}

// ---------- Aktionen ----------
document.addEventListener('click', async ev => {
  const el = ev.target.closest('[data-act]');
  if (!ev.target.closest('.search')) { const r = $('#results'); if (r) r.hidden = true; if (!$('#q')?.value) document.querySelector('#werkzeuge .search')?.classList.remove('offen'); }
  if (!ev.target.closest('.imp')) { $('#impmenu').hidden = true; $('#impbtn').setAttribute('aria-expanded', 'false'); }
  if (!el) return;
  const a = el.dataset.act, id = el.dataset.id ? (isNaN(+el.dataset.id) ? el.dataset.id : +el.dataset.id) : null;
  switch (a) {
  case 'import': { const m = $('#impmenu'); m.hidden = !m.hidden; el.setAttribute('aria-expanded', String(!m.hidden)); break; }
  case 'imp-file': $('#impmenu').hidden = true; $('#fileinp').dataset.ziel = S.view === 'archiv' ? 'archiv' : ''; $('#fileinp').click(); break;
  case 'arch-import': $('#fileinp').dataset.ziel = 'archiv'; $('#fileinp').click(); break;
  case 'doc-add': $('#fileinp').dataset.ziel = String(D.akte.id); $('#fileinp').click(); break;
  case 'imp-scan': $('#impmenu').hidden = true; scan(S.view === 'archiv', true); break;
  case 'imp-scan-dialog': $('#impmenu').hidden = true; scan(S.view === 'archiv', false); break;
  case 'scan-folder': $('#impmenu').hidden = true; try { const r = await api('scanordner/oeffnen', {}); toast(`Ordner „${r.pfad.split('/').pop()}“ (in Ihrem Benutzerordner) geöffnet. Was Sie dort hineinscannen oder ablegen, kommt automatisch in den Posteingang.`); } catch (e) { toast(e.message); } break;
  case 'ib-open': if (S.kombi) { const p = D.inbox.find(x => x.id === id); if (!kombinierbar(p)) { toast('Kombinieren geht nur mit PDFs und Bildern.'); break; }
      S.kombi = S.kombi.includes(id) ? S.kombi.filter(x => x !== id) : [...S.kombi, id]; zeichne(vInbox); break; } S.ibSel = S.ibSel === id ? null : id; zeichne(vInbox); if (S.ibSel) $('#it-' + S.ibSel)?.scrollIntoView({behavior: 'smooth', block: 'nearest'}); break;
  case 'ib-close': S.ibSel = null; zeichne(vInbox); break;
  case 'tile-kombi': { const p = D.inbox.find(x => x.id === id);
    if (!kombinierbar(p)) { toast('Kombinieren geht nur mit PDFs und Bildern.'); break; }
    if (!S.kombi) { S.kombi = [id]; S.ibSel = null; } else if (!S.kombi.includes(id)) S.kombi.push(id); else S.kombi = S.kombi.filter(x => x !== id);
    zeichne(vInbox); break; }
  case 'kombi-ab': S.kombi = null; zeichne(vInbox); break;
  case 'kombi-los': { const ids = [...S.kombi], erstes = D.inbox.find(x => x.id === ids[0]);
    modal('Zu einem PDF kombinieren', `<p style="margin:0">${ids.length} Dokumente werden in dieser Reihenfolge zu einem PDF zusammengefügt:</p>
      <ol style="margin:0;padding-left:20px">${ids.map(i => `<li>${esc(D.inbox.find(x => x.id === i)?.titel || '')}</li>`).join('')}</ol>
      <label>Titel des neuen Dokuments<input id="m-kt" maxlength="160" value="${esc(erstes ? erstes.titel : 'Kombiniertes Dokument')}"></label>
      <p class="muted" style="margin:0;font-size:12.5px">Die einzelnen Dokumente kommen danach in den Papierkorb und lassen sich von dort wiederherstellen.</p>`, async () => {
      const titel = val('m-kt').trim() || 'Kombiniertes Dokument'; closeModal();
      try { toast('Dokumente werden kombiniert …'); const neu = await kombinieren(ids, titel); S.kombi = null; S.ibSel = null; await render();
        toast(`„${titel}“ erstellt (${ids.length} Teile).`, 'Rückgängig', async () => { for (const i of ids) await api(`dokument/${i}/wiederherstellen`, {}); await api(`dokument/${neu}/loeschen`, {}); toast('Kombinieren rückgängig gemacht.'); await render(); }); }
      catch (e) { toast('Kombinieren fehlgeschlagen: ' + e.message); }
      return false; }, 'Kombinieren'); break; }
  case 'tile-view': { const p = D.inbox.find(x => x.id === id); openViewer(id, p ? p.titel : 'Dokument'); break; }
  case 'tile-del': {  // ohne Rückfrage: in den Papierkorb, mit „Rückgängig“ in der Meldung
    const p = D.inbox.find(x => x.id === id);
    try { await api(`dokument/${id}/loeschen`, {}); } catch (e) { toast(e.message); break; }
    D.inbox = D.inbox.filter(x => x.id !== id); if (S.ibSel === id) S.ibSel = null; zeichne(vInbox); nav();
    toast(`„${p ? p.titel : 'Dokument'}“ gelöscht.`, 'Rückgängig', async () => { await api(`dokument/${id}/wiederherstellen`, {}); toast('Wiederhergestellt.'); await render(); });
    break; }
  case 'toast-aktion': { const f = toastAktion; toastAktion = null; $('#toast').hidden = true; if (f) try { await f(); } catch (e) { toast(e.message); } break; }
  case 'ib-del': await act(() => api(`dokument/${id}/loeschen`, {}), 'In den Papierkorb verschoben.'); break;
  case 'ib-assign': try { await assign(id, el.dataset.v); } catch (e) { toast(e.message); } break;
  case 'ib-archiv': try { await assign(id, 'ablage'); } catch (e) { toast(e.message); } break;
  case 'ib-fadd': { const d = draft[id]; d.fristen.push({titel: '', faellig_am: plusTage(isoHeute(), 14), an: true}); await render(); const f = document.querySelectorAll(`[data-fr=titel][data-id="${id}"]`); f[f.length - 1]?.focus(); break; }
  case 'doc-move': ev.stopPropagation(); dokVerschieben(+el.dataset.doc, D.akte.id, D.akte.dokumente.find(x => x.id === +el.dataset.doc)?.titel); break;
  case 'doc-remove': ev.stopPropagation(); dokEntfernen(+el.dataset.doc, D.akte.id, D.akte.dokumente.find(x => x.id === +el.dataset.doc)?.titel); break;
  case 'arch-zuordnen': closeModal(); dokVerschieben(+el.dataset.doc, +el.dataset.v, el.dataset.t); break;
  case 'empf-save': await act(() => api('empfaenger', {empfaenger: val('empflist').split('\n').map(x => x.trim()).filter(Boolean)}), 'Gespeichert. Die Empfänger der Dokumente wurden neu zugeordnet.'); break;
  case 'arch-del': dokEntfernen(+el.dataset.doc, +el.dataset.v, el.dataset.t); break;
  case 'beenden': modal('DocuManager beenden?', '<p style="margin:0">Die Anwendung wird beendet. Starten Sie sie wieder über das Programm „DocuManager“.</p>', async () => {
      closeModal(); try { await api('beenden', {}); } catch (e) { /* Server bereits weg */ }
      document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;font:16px system-ui;color:#999;background:#111">DocuManager ist beendet. Sie können dieses Fenster schließen.</div>'; return false; }, 'Beenden'); break;
  case 'drehen': { const doc = +el.dataset.doc; try { const r = await api(`dokumente/${doc}/drehen`, {grad: +el.dataset.grad});
      for (const liste of [D.akte?.dokumente || [], D.archiv, D.inbox]) for (const x of liste) if (x.id === doc) x.drehung_manuell = r.drehung;
      if (S.view === 'akte') paintAkte(); else drehungAnwenden(); } catch (e) { toast(e.message); } break; }
  case 'k-edit': { const k = D.kontakte.find(x => x.id === id); modal('Kontakt bearbeiten', `<label>Name<input id="m-kn" maxlength="160" value="${esc(k.name)}"></label>
      <div class="two"><label>Kurzname<input id="m-kk" value="${esc(k.kurzname || '')}"></label><label>Art<input id="m-kt" value="${esc(k.typ || '')}" placeholder="z. B. Versicherung, Behörde"></label></div>
      <label>Notiz<textarea id="m-kno" rows="2">${esc(k.notiz || '')}</textarea></label>`, async () => {
      if (!val('m-kn').trim()) { $('#m-kn').focus(); return false; }
      closeModal(); await act(() => api('kontakte/' + k.id, {name: val('m-kn'), kurzname: val('m-kk'), typ: val('m-kt'), notiz: val('m-kno')}), 'Kontakt gespeichert.'); return false; }); break; }
  case 'chat-export': $('#chatinp').click(); break;
  case 'b-hoch': case 'b-runter': { const n = [...D.groups], i = n.indexOf(el.dataset.b), j = i + (el.dataset.act === 'b-hoch' ? -1 : 1);
      if (j < 0 || j >= n.length) break; [n[i], n[j]] = [n[j], n[i]]; await act(() => api('bereiche/reihenfolge', {namen: n})); break; }
  case 'art-del': await act(() => api('eintragsarten/entfernen', {name: el.dataset.name}), 'Art entfernt. Bestehende Einträge behalten ihre Bezeichnung.'); break;
  case 'art-neu': { const name = prompt('Name der neuen Eintragsart:'); if (name && name.trim()) await act(() => api('eintragsarten', {name: name.trim()}), 'Art angelegt.'); break; }
  case 'pv-info': S.pvInfo = !S.pvInfo; paintAkte(); break;
  case 'restore-file': $('#restoreinp').click(); break;
  case 'restore-list': wiederherstellenFrage(el.dataset.name, null); break;
  case 'heute': { const inp = el.previousElementSibling; if (inp) { inp.value = isoHeute(); inp.dispatchEvent(new Event('input', {bubbles: true})); inp.dispatchEvent(new Event('change', {bubbles: true})); } break; }
  case 'arch-move': dokVerschieben(+el.dataset.doc, +el.dataset.v, el.dataset.t); break;
  case 'f-neu': fristNeu(); break;
  case 'ib-manual': { const v = val('mv-' + id); if (v === '__new') newVorgang(nv => assign(id, nv)); else try { await assign(id, v); } catch (e) { toast(e.message); } break; }
  case 'view': openViewer(el.dataset.doc, el.closest('tr')?.querySelector('b')?.textContent || D.inbox.find(p => p.id === +el.dataset.doc)?.titel); break;
  case 'vw-close': closeViewer(); break;
  case 'tsort': { const k = 'sort' + el.dataset.t, cur = S[k]; S[k] = cur.k === el.dataset.k ? {k: cur.k, d: -cur.d} : {k: el.dataset.k, d: 1}; await render(); break; }
  case 'suche-auf': { const box = el.closest('.search'); box.classList.add('offen'); $('#q').focus(); break; }
  case 'filteransicht': try { D.ui = await api('oberflaeche', {filteransicht: (D.ui || {}).filteransicht === 'menue' ? 'chips' : 'menue'}); } catch (e) { toast(e.message); }
    if (S.view === 'akte') paintAkte(); else await render(); break;
  case 'em-verwerfen': EMPFANG = null; await render(); break;
  case 'em-los': { const ziel = val('em-ziel'); if (ziel === '__new') newVorgang(nv => empfangUebernehmen(nv)); else await empfangUebernehmen(ziel); break; }
  case 'lz-kopieren': try { await navigator.clipboard.writeText($('#lz-link').href); toast('Lesezeichen-Adresse kopiert.'); } catch (e) { toast('Kopieren nicht möglich. Bitte den Knopf in die Lesezeichenleiste ziehen.'); } break;
  case 'vgroup': S.vGroup = el.dataset.id; await render(); break;
  case 'vb': S.vb = id === null ? 'alle' : String(el.dataset.id); await render(); break;
  case 'vs': S.vs = el.dataset.id; await render(); break;
  case 'open-v': location.hash = 'akte-' + id; break;
  case 'new-vorgang': newVorgang(); break;
  case 'v-del': modal('Vorgang löschen?', '<p style="margin:0">Der Vorgang wird in den Papierkorb verschoben und lässt sich dort wiederherstellen.</p>', async () => {
      closeModal(); await act(() => api(`vorgang/${id}/loeschen`, {}), 'Vorgang in den Papierkorb verschoben.'); if (S.view === 'akte') location.hash = 'vorgaenge'; return false; }, 'In den Papierkorb'); break;
  case 'v-edit': await vorgangBearbeiten(el.dataset.id ? +el.dataset.id : D.akte.id); break;
  case 'multi-del': { const w = multiWert(el.dataset.multi).filter(x => x !== el.dataset.v); multiSetzen(el.dataset.multi, w); break; }
  case 'tab': S.tab = el.dataset.id; await render(); break;
  case 'teil': S.teil = el.dataset.id === 'all' ? 'all' : +el.dataset.id; S.entry = null; paintAkte(); break;
  case 'ktype': S.ktype = el.dataset.id; S.entry = null; paintAkte(); break;
  case 'entry': if (S.entry !== id) { S.entry = id; paintAkte(); if (innerWidth <= 1100) document.querySelector('.akte .r')?.scrollIntoView({behavior: 'smooth'}); } break;
  case 'teil-add': modal('Teilvorgang hinzufügen', `<label>Name<input id="m-tn" maxlength="120" placeholder="z. B. Heckschaden"></label><div class="two"><label>Status<select id="m-ts">${statusOptions('Offen')}</select></label><label>Zuständig<input id="m-tz" value="Ich"></label></div><label>Nächster Schritt<input id="m-tx"></label>`, async () => {
      if (!val('m-tn').trim()) { $('#m-tn').focus(); return false; }
      closeModal(); await act(async () => { const r = await api(`akte/${D.akte.id}/teilvorgaenge`, {name: val('m-tn'), status: val('m-ts'), zustaendig: val('m-tz'), naechster_schritt: val('m-tx')}); S.teil = r.id; }, 'Teilvorgang angelegt.'); return false; }, 'Anlegen'); break;
  case 'teil-edit': { const t = D.akte.teilvorgaenge.find(x => x.id === id); modal('Teilvorgang bearbeiten', `<label>Name<input id="m-tn" value="${esc(t.name)}"></label><div class="two"><label>Status<select id="m-ts">${statusOptions(t.status)}</select></label><label>Zuständig<input id="m-tz" value="${esc(t.zustaendig || '')}"></label></div><label>Nächster Schritt<input id="m-tx" value="${esc(t.naechster_schritt || '')}"></label><div><button class="btn sm" data-act="teil-del" data-id="${t.id}" style="color:var(--crit)">Teilvorgang entfernen</button></div>`, async () => {
      closeModal(); await act(() => api('teilvorgaenge/' + t.id, {name: val('m-tn'), status: val('m-ts'), zustaendig: val('m-tz'), naechster_schritt: val('m-tx')}), 'Gespeichert.'); return false; }); break; }
  case 'teil-del': closeModal(); await act(async () => { await api(`teilvorgaenge/${id}/entfernen`, {}); S.teil = 'all'; }, 'Teilvorgang entfernt.'); break;
  case 'ref-add': modal('Referenz hinzufügen', `<div class="two"><label>Bezeichnung<input id="m-rl" list="m-rll" value="Aktenzeichen"><datalist id="m-rll"><option value="Aktenzeichen"><option value="Schaden-Nr."><option value="Kundennr."><option value="Steuer-Nr."><option value="Vertrags-Nr."><option value="Rechnung"></datalist></label><label>Nummer<input id="m-rv"></label></div>
      <label>Geführt von<select id="m-rk"><option value="">–</option>${D.akte.beteiligte.map(b => `<option value="${b.kontakt_id}">${esc(b.kurzname || b.name)}</option>`).join('')}</select></label>`, async () => {
      if (!val('m-rv').trim()) { $('#m-rv').focus(); return false; }
      closeModal(); await act(() => api(`akte/${D.akte.id}/referenzen`, {bezeichnung: val('m-rl'), wert: val('m-rv'), kontakt_id: val('m-rk') ? +val('m-rk') : null}), 'Referenz hinzugefügt.'); return false; }, 'Hinzufügen'); break;
  case 'ref-del': await act(() => api(`referenzen/${id}/entfernen`, {}), 'Referenz entfernt.'); break;
  case 'bet-add': modal('Beteiligten hinzufügen', `<label>Kontakt<select id="m-bk">${D.kontakte.filter(k => !D.akte.beteiligte.some(b => b.kontakt_id === k.id)).map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join('')}</select></label><label>Rolle<input id="m-br" placeholder="z. B. Gegnerische Versicherung"></label><p class="muted" style="margin:0;font-size:13px">Fehlt der Kontakt, legen Sie ihn zuerst im Adressbuch an.</p>`, async () => {
      if (!val('m-bk')) return false; closeModal(); await act(() => api(`akte/${D.akte.id}/beteiligte`, {kontakt_id: +val('m-bk'), rolle: val('m-br')}), 'Beteiligter hinzugefügt.'); return false; }, 'Hinzufügen'); break;
  case 'bet-del': await act(() => api(`akte/${D.akte.id}/beteiligte/${id}/entfernen`, {}), 'Beteiligter entfernt.'); break;
  case 'tags': modal('Schlagwörter', `<label>Durch Komma getrennt<input id="m-tg" value="${esc(D.akte.schlagwoerter.join(', '))}"></label>`, async () => {
      closeModal(); await act(() => api(`akte/${D.akte.id}/schlagwoerter`, {namen: val('m-tg').split(',').map(s => s.trim()).filter(Boolean)}), 'Gespeichert.'); return false; }); break;
  case 'entry-add': entryModal(el.dataset.bezug ? +el.dataset.bezug : null); break;
  case 'entry-edit': { const e = D.akte.eintraege.find(x => x.id === id); const frei = ['eingang','ausgang','telefonat','notiz','entscheidung','fehlt'].includes(e.art);
    modal('Eintrag bearbeiten', `<div class="two"><label>Titel<input id="m-et" value="${esc(e.titel)}"></label><label>Ereignisdatum<input id="m-ed" type="date" value="${e.ereignis_datum}"></label></div>
      <div class="two">${frei ? `<label>Art<select id="m-eart">${[['eingang','Eingang'],['ausgang','Versendet'],['telefonat','Telefonat'],['notiz','Notiz'],['entscheidung','Entscheidung'],['fehlt','Original fehlt'], ...(D.arten || []).map(t => ['typ:' + t, t])].map(([k, l]) => `<option value="${esc(k)}" ${(e.typ ? 'typ:' + e.typ : e.art) === k ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>` : `<label>Art<input value="${esc(e.typ || KIND[e.art][0])}" disabled></label>`}
       <label>Beteiligter<select id="m-ekon"><option value="">–</option>${D.kontakte.map(k => `<option value="${k.id}" ${e.kontakt_id === k.id ? 'selected' : ''}>${esc(k.kurzname || k.name)}</option>`).join('')}</select></label></div>
      <label>Dokument<select id="m-edok"><option value="">– kein Dokument –</option>${D.akte.dokumente.map(d => `<option value="${d.id}" ${e.dokument_id === d.id ? 'selected' : ''}>${esc(d.titel)} (${esc(d.dateiname)})</option>`).join('')}<option value="__datei">+ Datei hochladen und zuweisen …</option></select><input type="file" id="m-edatei" hidden accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff,.docx,.eml"></label>
      ${D.akte.teilvorgaenge.length ? `<label>Gehört zu</label><div style="display:flex;gap:14px;flex-wrap:wrap">${D.akte.teilvorgaenge.map(t => `<label class="chk"><input type="checkbox" class="m-etk" value="${t.id}" ${e.teile.includes(t.id) ? 'checked' : ''}>${esc(t.name)}</label>`).join('')}</div>` : ''}
      <label>Inhalt<textarea id="m-ex" rows="4">${esc(e.text || '')}</textarea></label>${e.art === 'chat' ? `<label class="chk"><input type="checkbox" id="m-eg" ${e.geprueft ? 'checked' : ''}>Inhalt geprüft</label>` : ''}
      <label>Zusätzlich in Vorgang zeigen<select id="m-ev"><option value="">–</option>${e.dokument_id ? aktiv().filter(c => c.id !== D.akte.id).map(c => `<option value="${c.id}">${esc(c.titel)}</option>`).join('') : ''}</select></label>
      <div><button class="btn sm" data-act="entry-del" data-id="${e.id}">${I('trash')}In den Papierkorb</button></div>`, async () => {
      const body = {titel: val('m-et'), datum: val('m-ed'), text: val('m-ex'), kontakt_id: val('m-ekon') ? +val('m-ekon') : null};
      if (val('m-edok') !== '__datei') body.dokument_id = val('m-edok') ? +val('m-edok') : null;
      if ($('#m-eart') || snap['m-eart']) { const w = val('m-eart'); if (w.startsWith('typ:')) { body.art = 'notiz'; body.typ = w.slice(4); } else { body.art = w; body.typ = null; } }
      if (D.akte.teilvorgaenge.length) body.teile = [...document.querySelectorAll('.m-etk:checked')].map(x => +x.value);
      if ($('#m-eg')) body.geprueft = $('#m-eg').checked;
      if (val('m-ev')) body.auch_in_vorgang = +val('m-ev');
      closeModal(); await act(() => api('eintraege/' + e.id, body), 'Gespeichert.'); return false; }); break; }
  case 'entry-del': closeModal(); await act(() => api(`eintrag/${id}/loeschen`, {}), 'In den Papierkorb verschoben.'); break;
  case 'versand': versandModal(D.akte.eintraege.find(x => x.id === id)); break;
  case 'doc-rename': { const d = D.akte.dokumente.find(x => x.id === +el.dataset.doc); modal('Titel ändern', `<label>Titel<input id="m-dt" value="${esc(d.titel)}" maxlength="160"></label>`, async () => {
      closeModal(); await act(() => api(`documents/${d.id}/title`, {title: val('m-dt')}), 'Titel gespeichert.'); return false; }); break; }
  case 'doc-text': { const r = await api(`documents/${el.dataset.doc}/pages`); modal('Erkannter Text', `<pre class="ocrd" style="white-space:pre-wrap;max-height:60vh;overflow:auto;font-family:inherit">${esc(r.pages.map(p => `— Seite ${p.nummer} · ${p.methode === 'ocr' ? 'OCR' : 'Textschicht'} —\n${p.text}`).join('\n\n')) || 'Kein Text gespeichert.'}</pre>`, null); break; }
  case 'ocr-retry': await act(() => api(`documents/${el.dataset.doc}/ocr`, {}), 'Texterkennung gestartet.'); break;
  case 'doc-open': { const e = D.akte.eintraege.find(x => x.dokument_id === +el.dataset.doc); if (e) { S.tab = 'chronik'; S.entry = e.id; S.teil = 'all'; S.ktype = 'alle'; await render(); } else openViewer(el.dataset.doc); break; }
  case 'd-del': await act(() => api(`dokument/${el.dataset.doc}/loeschen`, {}), 'Dokument in den Papierkorb verschoben.'); break;
  case 'quelle': openViewer(el.dataset.doc, 'Fundstelle'); break;
  case 'f-add': fristModal(); break;
  case 'f-done': await act(() => api('fristen/' + id, {erledigt: true}), 'Als erledigt markiert.'); break;
  case 'f-undo': await act(() => api('fristen/' + id, {erledigt: false})); break;
  case 'f-move': { const f = (D.akte?.fristen || D.fristen).find(x => x.id === id) || D.fristen.find(x => x.id === id); modal('Frist verschieben', `<p style="margin:0"><b>${esc(f.titel)}</b><br><span class="muted">bisher fällig am ${dt(f.faellig_am)}</span></p><label>Neues Datum<input id="m-fd" type="date" value="${plusTage(f.faellig_am, 7)}"></label><label>Grund<input id="m-fg" placeholder="z. B. Verlängerung telefonisch bestätigt"></label>
      ${f.art === 'frist' ? '<div class="notice warn" style="margin:0"><p>Eine verbindliche Frist verschiebt sich nur, wenn die Gegenseite zugestimmt hat. Das bisherige Datum bleibt im Verlauf sichtbar.</p></div>' : ''}`, async () => {
      closeModal(); await act(() => api('fristen/' + f.id, {faellig_am: val('m-fd'), grund: val('m-fg')}), 'Verschoben.'); return false; }, 'Verschieben'); break; }
  case 'f-zust': { const f = D.akte.fristen.find(x => x.id === id); modal('Zuständig', `<label>Zuständige Person oder Stelle<input id="m-fz" value="${esc(f.zustaendig || '')}"></label>`, async () => {
      closeModal(); await act(() => api('fristen/' + f.id, {zustaendig: val('m-fz')}), 'Gespeichert.'); return false; }); break; }
  case 'ffilter': S.fFilter = el.dataset.id; zeichne(vFristen); break;
  case 'agroup': S.aGroup = el.dataset.id; zeichne(vArchiv); break;
  case 'abereich': S.aBereich = el.dataset.id; zeichne(vArchiv); break;
  case 'ajahr': S.aJahr = el.dataset.id; zeichne(vArchiv); break;
  case 'atyp': S.aTyp = el.dataset.id; zeichne(vArchiv); break;
  case 'arch-edit': if (ev.target.closest('[data-act=view], [data-act=arch-move], [data-act=arch-del]')) break; archivBearbeiten(+el.dataset.doc); break;
  case 'arch-akte': closeModal(); S.v = +el.dataset.v; S.tab = 'chronik'; S.teil = 'all'; S.ktype = 'alle';
    S.entry = null; location.hash = 'akte-' + el.dataset.v; setTimeout(() => { const e = D.akte?.eintraege.find(x => x.dokument_id === +el.dataset.doc); if (e) { S.entry = e.id; paintAkte(); } }, 400); break;
  case 'contact': S.contact = id; S.abq = ''; if (location.hash !== '#adressbuch') location.hash = 'adressbuch'; else await render(); break;
  case 'k-new': modal('Neuer Kontakt', `<label>Name der Organisation oder Person<input id="m-kn" maxlength="160"></label><div id="m-kd"></div><div class="two"><label>Kurzname<input id="m-kk"></label><label>Art<input id="m-kt" placeholder="z. B. Versicherung, Behörde"></label></div>
      <div class="two"><label>Abteilung<input id="m-ka"></label><label>Ansprechpartner<input id="m-kp"></label></div><div class="two"><label>E-Mail<input id="m-km" type="email"></label><label>Telefon<input id="m-kf"></label></div><label>Anschrift (eine Zeile pro Zeile)<textarea id="m-kr" rows="4"></textarea></label>`, async () => {
      if (!val('m-kn').trim()) { $('#m-kn').focus(); return false; }
      closeModal(); await act(async () => { const r = await api('kontakte', {name: val('m-kn'), kurzname: val('m-kk'), typ: val('m-kt'), abteilungen: [{name: val('m-ka'), ansprechpartner: val('m-kp'), email: val('m-km'), telefon: val('m-kf'), anschrift: val('m-kr') || null}]}); S.contact = r.id; }, 'Kontakt angelegt.'); return false; }, 'Anlegen'); break;
  case 'k-del': await act(() => api(`kontakt/${id}/loeschen`, {}), 'Kontakt in den Papierkorb verschoben.'); S.contact = null; break;
  case 'adr-new': modal('Neue Anschrift', `<label>Anschrift (eine Zeile pro Zeile)<textarea id="m-az" rows="4"></textarea></label><label>Gültig ab<input id="m-av" type="date" value="${isoHeute()}"></label><p class="muted" style="margin:0;font-size:13px">Die bisherige Anschrift endet am Vortag und bleibt bei früheren Schreiben sichtbar.</p>`, async () => {
      if (!val('m-az').trim()) { $('#m-az').focus(); return false; } closeModal(); await act(() => api(`abteilungen/${id}/anschrift`, {zeilen: val('m-az'), gueltig_von: val('m-av')}), 'Anschrift gespeichert.'); return false; }); break;
  case 't-restore': await act(() => api(`${el.dataset.typ}/${id}/wiederherstellen`, {}), 'Wiederhergestellt.'); break;
  case 't-purge': if (el.dataset.sure !== '1') { el.dataset.sure = '1'; el.textContent = 'Endgültig? Erneut klicken'; el.style.color = 'var(--crit)'; break; } await act(() => api(`${el.dataset.typ}/${id}/endgueltig`, {}), 'Endgültig gelöscht.'); break;
  case 'b-add': modal('Bereich hinzufügen', '<label>Name<input id="m-bn" maxlength="80" placeholder="z. B. Wohnen und Miete"></label>', async () => {
      if (!val('m-bn').trim()) return false; closeModal(); await act(() => api('bereiche', {name: val('m-bn')}), 'Bereich angelegt.'); return false; }, 'Anlegen'); break;
  case 'b-ren': modal('Bereich umbenennen', `<label>Name<input id="m-bn" value="${esc(el.dataset.b)}"></label>`, async () => {
      closeModal(); await act(() => api('bereiche/umbenennen', {alt: el.dataset.b, neu: val('m-bn')}), 'Umbenannt.'); return false; }); break;
  case 'b-del': await act(() => api('bereiche/entfernen', {name: el.dataset.b}), 'Bereich entfernt.'); break;
  case 'mail-get': $('#impmenu').hidden = true; await mailHolen(S.view === 'archiv' && !el.closest('.view')); break;
  case 'compose': compose(el.dataset.bezug ? +el.dataset.bezug : null, el.dataset.edit ? +el.dataset.edit : null); break;
  case 'pv-mode': S.pvMode = el.dataset.id; paintAkte(); break;
  case 'take': uebernehmen(el.dataset.k, {text: el.dataset.t, doc: +el.dataset.doc, seite: +el.dataset.s, entry: +el.dataset.entry, datum: el.dataset.datum, titel: el.dataset.titel}); break;
  case 'sel': if (sel) uebernehmen(el.dataset.k, sel); break;
  case 'export': exportDialog(); break;
  case 'chat-new': chatModal('', ''); break;
  case 'chat-ok': await act(() => api('eintraege/' + id, {geprueft: true}), 'Als geprüft markiert.'); break;
  case 'chat-thread': { const r = await api('chat/threads/' + encodeURIComponent(el.dataset.id)); const t = D.threads.find(x => String(x.id) === el.dataset.id);
    chatModal((r.notes || []).map(n => `${n.rolle === 'user' ? 'Ich' : 'ChatGPT'}: ${n.text}`).join('\n\n').slice(0, 19000), `ChatGPT-Verlauf „${t ? t.titel : el.dataset.id}“`); break; }
  case 'backup': toast('Sicherung wird erstellt …'); try { const r = await api('sicherungen', {}); toast(r.pruefung.ok ? `Sicherung erstellt und geprüft: ${r.pruefung.anzahl.vorgang} Vorgänge, ${r.pruefung.dateien} Dateien.` : 'Sicherung erstellt, Prüfung meldet Fehler: ' + r.pruefung.fehler.join('; ')); await render(); } catch (e) { toast(e.message); } break;
  case 'backup-check': { const r = await api(`sicherungen/${el.dataset.name}/pruefen`, {}); toast(r.ok ? `In Ordnung: ${r.anzahl.vorgang} Vorgänge, ${r.anzahl.dokument} Dokumente, ${r.dateien} Dateien.` : 'Fehler: ' + r.fehler.join('; ')); break; }
  case 'norm': normZeigen(el.dataset.z); break;
  case 'norm-zu': $('#normpop').hidden = true; break;
  case 'claude': claudeDialog(el.dataset.doc ? +el.dataset.doc : null, el.dataset.entry ? +el.dataset.entry : null); break;
  case 'claude-key': D.claude.eingerichtet = false; await render(); $('#claudekey')?.focus(); break;
  case 'claude-key-save': await act(async () => { D.claude = await api('claude/schluessel', {schluessel: val('claudekey')}); }, 'Zugangsschlüssel gespeichert.'); break;
  case 'claude-key-del': await act(async () => { D.claude = await api('claude/schluessel', {schluessel: ''}); }, 'Zugangsschlüssel entfernt.'); break;
  case 'eigene-save': await act(() => api('einstellungen', {eigene_angaben: val('eigene')}), 'Gespeichert.'); break;
  case 'hit': $('#results').hidden = true; S.v = +el.dataset.v; S.tab = 'chronik'; S.teil = 'all'; S.ktype = 'alle'; S.entry = null; location.hash = 'akte-' + el.dataset.v;
    if (el.dataset.e) setTimeout(() => { S.entry = +el.dataset.e; if (D.akte) paintAkte(); }, 400); break;
  case 'm-close': closeModal(); break;
  case 'm-bg': if (ev.target === el) closeModal(); break;
  case 'm-save': if (modalSave) {
    snap = Object.fromEntries([...document.querySelectorAll('#modalroot [id]')].map(e => [e.id, e.value]));
    const r = await modalSave(); if (r !== false) closeModal(); } break;
  }
});
document.addEventListener('change', async ev => {
  const el = ev.target;
  if (el.dataset.change === 'v-status') await statusSetzen(null, el.value, render);
  if (el.dataset.change === 't-status') await statusSetzen(+el.dataset.id, el.value, render);
  if (el.id === 'claudestufe') await act(async () => { D.claude = await api('claude/stufe', {stufe: el.value}); }, 'Gespeichert.');
  if (el.id === 'mailflag') await act(() => api('mail/markierung', {markierung: +el.value}), 'Markierung gespeichert.');
  if (el.id === 'fileinp') { const files = [...el.files]; el.value = ''; await importFiles(files, el.dataset.ziel === 'archiv' ? 'archiv' : el.dataset.ziel ? +el.dataset.ziel : null); }
  if (el.id === 'm-ea' && el.value === '__neu') { const name = prompt('Name der neuen Eintragsart (z. B. Besprechung, Ortstermin):'); el.value = 'notiz';
    if (name && name.trim()) { try { const r = await api('eintragsarten', {name: name.trim()}); D.arten = [...(D.arten || []), r.name]; el.insertAdjacentHTML('beforeend', `<option value="${esc('typ:' + r.name)}">${esc(r.name)}</option>`); el.value = 'typ:' + r.name; toast(`Art „${r.name}“ angelegt.`); } catch (e) { toast(e.message); } } }
  if (el.id === 'm-edok' && el.value === '__datei') $('#m-edatei').click();
  if (el.id === 'm-edatei' && el.files[0]) { const f = el.files[0]; el.value = ''; try { const r = await upload(`cases/${D.akte.id}/documents`, f);
      D.akte.dokumente.unshift({id: r.id, titel: f.name.replace(/\.[^.]+$/, ''), dateiname: f.name}); const sel = $('#m-edok');
      sel.insertAdjacentHTML('afterbegin', `<option value="${r.id}">${esc(f.name)}</option>`); sel.value = String(r.id); toast('Datei hochgeladen; beim Speichern wird sie dem Eintrag zugewiesen.'); } catch (e) { toast(e.message); $('#m-edok').value = ''; } }
  if (el.dataset.fsel) {  // Ausklappmenü-Filter: wie ein Klick auf die entsprechende Schaltfläche
    const opt = el.selectedOptions[0], knopf = document.createElement('button');
    knopf.dataset.act = opt.dataset.neu || el.dataset.fsel; knopf.dataset.id = el.value; knopf.hidden = true;
    el.after(knopf); knopf.click(); knopf.remove();
  }
  if (el.classList.contains('madd') && el.value) { const id = el.dataset.multi; multiSetzen(id, [...multiWert(id), el.value]); }
  if (el.id === 'chatinp' && el.files[0] && /\.documanager\.json$/i.test(el.files[0].name)) { const f = el.files[0]; el.value = ''; try { empfangAusDatei(await f.text()); } catch (err) { toast(err.message); } return; }
  if (el.id === 'chatinp' && el.files[0]) { const f = el.files[0]; el.value = ''; toast('Export wird gelesen …');
    try { const res = await holen('/api/chat/preview', {method: 'POST', body: f, headers: {'X-Korrespondenz': 'lokal'}}); const r = await res.json(); if (!res.ok) throw new Error(r.error || 'Export nicht lesbar.');
      modal(`ChatGPT-Export · ${r.threads.length} Unterhaltungen`, `<p style="margin:0">Unterhaltungen auswählen (bis zu 100). Bereits importierte werden aktualisiert.</p>
        <input class="inp" id="m-cfil" type="search" placeholder="Titel filtern">
        <div class="stack" id="m-cliste" style="gap:4px;max-height:50vh;overflow:auto">${r.threads.map(t => `<label class="chk" data-t="${esc(t.title.toLowerCase())}"><input type="checkbox" class="m-cth" value="${esc(t.id)}">${esc(t.title)} <span class="muted" style="font-size:12px">${t.date ? dt(new Date(t.date * 1000).toISOString().slice(0, 10)) : ''}${t.known ? ' · bereits importiert' : ''}</span></label>`).join('')}</div>`, async () => {
        const ids = [...document.querySelectorAll('.m-cth:checked')].map(x => x.value); if (!ids.length) { toast('Bitte mindestens eine Unterhaltung wählen.'); return false; }
        closeModal(); try { const z = await api('chat/import', {token: r.token, threads: ids}); toast(`${ids.length} Unterhaltung(en) importiert: ${z.notes} neue Beiträge${z.missing ? `, ${z.missing} Anlagen fehlen` : ''}.`); await render(); } catch (e) { toast(e.message); }
        return false; }, 'Importieren', 'wide');
    } catch (e) { toast(e.message); } }
  if (el.id === 'm-cfil') { const q = el.value.toLowerCase(); for (const l of document.querySelectorAll('#m-cliste [data-t]')) l.hidden = !l.dataset.t.includes(q); }
  if (el.id === 'restoreinp') { const f = el.files[0]; el.value = ''; if (f) wiederherstellenFrage(null, f); }
  if (el.dataset.ib && el.value !== '__neu') { const d = draft[+el.dataset.id]; if (d) d[el.dataset.ib] = el.value; }
  if (el.dataset.fr) { const f = draft[+el.dataset.id]?.fristen[+el.dataset.i]; if (f) f[el.dataset.fr] = el.type === 'checkbox' ? el.checked : el.value; }
});
document.addEventListener('input', ev => {
  const el = ev.target;
  if (el.id === 'm-cfil') { const q = el.value.toLowerCase(); for (const l of document.querySelectorAll('#m-cliste [data-t]')) l.hidden = !l.dataset.t.includes(q); }
  if (el.dataset.ib === 'kontakt' && el.value === '__neu') { neuerKontakt(+el.dataset.id); return; }
  if (el.dataset.ib === 'empfaenger' && el.value === '__neu') {  // neuer zulässiger Empfänger, gleich gewählt
    const docId = +el.dataset.id, name = (prompt('Name des neuen Empfängers (z. B. Ihre Firma oder eine Person):') || '').trim();
    el.value = draft[docId]?.empfaenger || '';
    if (name) api('empfaenger', {empfaenger: [...(D.empfaenger || []), name]}).then(r => { D.empfaenger = r.empfaenger; if (draft[docId]) draft[docId].empfaenger = name; zeichne(vInbox); toast(`Empfänger „${name}“ angelegt.`); }).catch(e => toast(e.message));
    return;
  }
  if (el.dataset.ib) { const d = draft[+el.dataset.id]; if (d) d[el.dataset.ib] = el.value; }
  if (el.dataset.fr) { const f = draft[+el.dataset.id]?.fristen[+el.dataset.i]; if (f) f[el.dataset.fr] = el.type === 'checkbox' ? el.checked : el.value; }
  if (el.id === 'q') search(el.value.trim());
  if (el.id === 'abq') { S.abq = el.value; const p = el.selectionStart; zeichne(vAb); const i = $('#abq'); i.focus(); i.setSelectionRange(p, p); }
  if (el.id === 'atext') { S.aText = el.value; const p = el.selectionStart; zeichne(vArchiv); const i = $('#atext'); i.focus(); i.setSelectionRange(p, p); }
  if (el.id === 'm-kn') dubletten(el.value);
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') { if (!$('#viewer').hidden) closeViewer(); else closeModal(); $('#results').hidden = true; }
  if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches('.card[data-act], .tile[data-act]')) { ev.preventDefault(); ev.target.click(); }
});
let dubTimer;
function dubletten(name) { clearTimeout(dubTimer); dubTimer = setTimeout(async () => { const box = $('#m-kd'); if (!box) return;
  const r = name.trim().length >= 3 ? (await api('kontakte/dubletten?name=' + encodeURIComponent(name))).dubletten : [];
  box.innerHTML = r.length ? `<div class="notice warn" style="margin:0">${I('alert')}<p>Mögliche Dublette: ${r.map(k => `<b>${esc(k.name)}</b>`).join(', ')}</p></div>` : ''; }, 250); }
let searchTimer;
function search(q) {
  clearTimeout(searchTimer); const box = $('#results');
  if (q.length < 2) { box.hidden = true; return; }
  searchTimer = setTimeout(async () => {
    const r = (await api('suche?q=' + encodeURIComponent(q))).treffer;
    const mark = s => esc(s).replace(/\[/g, '<mark>').replace(/\]/g, '</mark>');
    box.innerHTML = r.length ? r.slice(0, 10).map(t => `<button class="res" data-act="hit" data-v="${t.vorgang_id}" data-e="${t.eintrag_id || ''}"><b>${esc(t.titel)}</b><span>${esc(t.vorgang)}${t.seite ? ' · Seite ' + t.seite : ''}</span>${t.ausschnitt ? `<span class="snip">${mark(t.ausschnitt)}</span>` : ''}</button>`).join('')
      : '<div class="res"><b>Keine Treffer</b><span>Gesucht wird in Titeln, Aktenzeichen, Notizen und Dokumenttexten.</span></div>';
    box.hidden = false;
  }, 200);
}

// ---------- Import und Scan ----------
async function importFiles(files, vorgangId) {
  if (!files.length) return;
  let neu = 0, vorhanden = 0; const fehler = [];
  for (const f of files) {
    toast(`„${f.name}“ wird abgelegt …`);
    try { const r = await upload(vorgangId === 'archiv' ? 'archiv/dokumente' : vorgangId ? `cases/${vorgangId}/documents` : 'posteingang/dokumente', f); r.created ? neu++ : vorhanden++; }
    catch (e) { fehler.push(f.name + ': ' + e.message); }
  }
  if (vorgangId === 'archiv') { toast(`${neu} im Archiv abgelegt${vorhanden ? ` · ${vorhanden} bereits vorhanden` : ''}. Die Texterkennung läuft; Titel, Datum und Absender werden ergänzt.${fehler.length ? ' · ' + fehler.join(' · ') : ''}`); await render(); return; }
  toast(`${neu} abgelegt${vorhanden ? ` · ${vorhanden} bereits vorhanden` : ''}${fehler.length ? ' · ' + fehler.join(' · ') : ''}`);
  if (!vorgangId && location.hash !== '#posteingang') location.hash = 'posteingang'; else await render();
}
async function mailHolen(insArchiv) {
  toast('E-Mails werden aus Apple Mail geholt …');
  try {
    let gesamt = 0, r;
    do { r = await api('mail/abholen', insArchiv ? {ziel: 'archiv'} : {}); gesamt += r.neu; } while (r.weitere && r.neu);
    if (insArchiv) { toast(gesamt ? `${gesamt} E-Mail${gesamt === 1 ? '' : 's'} samt Anlagen im Archiv abgelegt.` : 'Keine neuen markierten E-Mails.'); await render(); return; }
    toast(gesamt ? `${gesamt} neue E-Mail${gesamt === 1 ? '' : 's'} übernommen${r.fehler.length ? ' · ' + r.fehler.join(' · ') : ''}` : 'Keine neuen markierten E-Mails. Bereits übernommene werden nicht erneut geholt.');
    if (location.hash !== '#posteingang') location.hash = 'posteingang'; else await render();
  } catch (e) { toast(e.message); }
}
async function scan(insArchiv, direkt) {
  try {
    const job = await api(insArchiv ? 'archiv/scan' : 'posteingang/scan', {direkt: !!direkt});
    toast(direkt ? 'Scanner wird gestartet … Das Dokument landet danach von selbst im ' + (insArchiv ? 'Archiv.' : 'Posteingang.') : 'Scannen Sie im Scan-Dialog; der Scan wird danach automatisch übernommen.');
    let r; do { await new Promise(res => setTimeout(res, 1200)); r = await api(`scans/${job.id}/poll`, {}); } while (r.state === 'open');
    if (r.state === 'digitale-bilder') {
      modal('Scannen mit „Digitale Bilder“', `<ol style="margin:0;padding-left:20px;line-height:1.6"><li>In „Digitale Bilder“ links den Scanner wählen.</li>
        <li>Unten bei <b>„Scannen nach“</b> auf <b>„Andere …“</b> gehen und den Ordner <b>„DocuManager Scans“</b> in Ihrem Benutzerordner wählen (einmalig, wird gemerkt).</li>
        <li>Scannen. Die Scans erscheinen nach wenigen Sekunden von selbst im Posteingang.</li></ol>`, null, '');
      return;
    }
    toast(r.state === 'done' ? `${r.imported} Scan(s) ${insArchiv ? 'im Archiv abgelegt' : 'im Posteingang'}${r.errors.length ? ' · ' + r.errors.join(' · ') : ''}` : 'Scan abgebrochen.');
    if (!insArchiv) location.hash = 'posteingang'; await render();
  } catch (e) { toast(e.message); }
}
addEventListener('dragover', e => { if ([...(e.dataTransfer?.types || [])].includes('Files')) { e.preventDefault(); document.body.classList.add('dragging'); } });
addEventListener('dragleave', e => { if (!e.relatedTarget) document.body.classList.remove('dragging'); });
addEventListener('drop', e => { document.body.classList.remove('dragging'); const fs = [...(e.dataTransfer?.files || [])];
  const paket = fs.find(f => /\.documanager\.json$/i.test(f.name));
  if (paket) { e.preventDefault(); paket.text().then(empfangAusDatei).catch(err => toast(err.message)); return; }
  if (e.dataTransfer?.files?.length) { e.preventDefault(); importFiles([...e.dataTransfer.files], S.view === 'akte' ? D.akte.id : S.view === 'archiv' ? 'archiv' : null); } });
addEventListener('hashchange', route);
route();
})();

// „Heute“ neben jedem Datumsfeld
function heuteKnoepfe(root) {
  for (const inp of root.querySelectorAll('input[type=date]:not([data-heute])')) {
    inp.dataset.heute = '1';
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'heute'; b.dataset.act = 'heute'; b.textContent = 'Heute'; b.title = 'Heutiges Datum einsetzen';
    const feld = document.createElement('span'); feld.className = 'datefeld';
    inp.replaceWith(feld); feld.append(inp, b);
  }
}
new MutationObserver(() => heuteKnoepfe(document.body)).observe(document.body, {childList: true, subtree: true});
