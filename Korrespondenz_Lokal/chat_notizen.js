'use strict';
(() => {
  const nav = document.querySelector('#nav');
  const view = document.querySelector('#view');
  const root = document.querySelector('#main');
  const online = location.origin === 'http://127.0.0.1:8765';
  const dateFormat = new Intl.DateTimeFormat('de-DE', {
    dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Berlin'
  });
  const asDate = value => value == null ? 'Datum unbekannt' : dateFormat.format(new Date(value*1000));
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  })[char]);
  const normalize = value => value.normalize('NFC').toLocaleLowerCase('de');
  const pauseNote = 'Für neue Beiträge wählst du bei Bedarf einen neueren ChatGPT-Export aus.';
  let revision = 0;
  let activeThread;

  async function api(path, body, type) {
    const options = body === undefined ? undefined : {
      method:'POST', headers:{'X-Korrespondenz':'lokal','Content-Type':type}, body
    };
    const result = await fetch('/api/chat/' + path, options);
    const data = await result.json();
    if (!result.ok) throw new Error(data.error || 'Die Anfrage ist fehlgeschlagen.');
    return data;
  }
  function ensureLink() {
    if (nav.querySelector('#chat-notes')) return;
    const item = document.createElement('button');
    item.id = 'chat-notes';
    item.type = 'button';
    item.innerHTML = '<span aria-hidden="true">≡</span><span>Chat-Notizen</span>';
    item.addEventListener('click', () => show());
    nav.append(item);
  }
  ensureLink();
  new MutationObserver(ensureLink).observe(nav,{childList:true});
  document.addEventListener('click', event => {
    if (event.target.closest('[data-open-chat-notes]')) show();
  });

  function attachment(item) {
    const title = escape(item.name);
    if (item.local) return '<li><a href="/api/chat/originals/'+Number(item.id)+'">'+title+'</a> · Lokales Original</li>';
    if (item.archiv_id) {
      const source='https://chatgpt.com/library?file_id='+encodeURIComponent(item.archiv_id)+'&account_id=personal';
      return '<li><a href="'+source+'" target="_blank" rel="noopener">'+title+'</a> · Archivdatei</li>';
    }
    return '<li>'+title+' · Original im Export nicht verfügbar</li>';
  }
  function noteCard(note) {
    const role = note.rolle === 'user' ? 'Dein Beitrag' : 'ChatGPT-Antwort';
    const variants = note.alternativ ? ' · Alternativer Gesprächsverlauf' : '';
    const attached = note.anlagen.length ? '<h4>Dokumente und Anlagen</h4><ul>'+note.anlagen.map(attachment).join('')+'</ul>' : '';
    return `<article class="card"><h3>${role}</h3><small>${asDate(note.datum)}${variants}</small>
      ${note.text?'<p style="white-space:pre-wrap;overflow-wrap:anywhere;margin-top:8px">'+escape(note.text)+'</p>':''}${attached}</article>`;
  }

  async function show(feedback = '') {
    const current = ++revision;
    function isOpen(section) { return revision === current && section.isConnected; }
    nav.querySelectorAll('[aria-current]').forEach(node=>node.removeAttribute('aria-current'));
    nav.querySelector('#chat-notes').setAttribute('aria-current','page');
    root.classList.remove('mobile-preview');
    view.innerHTML = '<section class="list-page" id="chat-view"><h1>Chat-Notizen · Rechtsberatung</h1>'+
      '<p id="chat-status" role="status"></p></section>';
    const section = view.querySelector('#chat-view');
    if (!online) {
      section.querySelector('#chat-status').textContent = 'Starte die lokale Anwendung mit Korrespondenz_Starten.command.';
      return;
    }
    let data;
    try { data = await api('threads'); }
    catch (error) { section.querySelector('#chat-status').textContent = error.message; return; }
    if (!isOpen(section)) return;
    const selected = data.threads.find(item=>item.id === activeThread) || data.threads[0];
    activeThread = selected?.id;

    section.innerHTML = `<h1>Chat-Notizen · Rechtsberatung</h1>
      <form id="chat-export" class="card" style="max-width:800px;margin-bottom:14px">
        <label>ChatGPT-Export auswählen<input name="file" type="file" accept=".zip,.json" required></label>
        <small>ZIP bis 250 MB oder einzelne Unterhaltungs-JSON bis 150 MB. ${pauseNote}</small>
        <div class="tools" style="margin-top:8px"><button type="submit" class="primary">Unterhaltungen auswählen</button></div>
      </form>
      <p id="chat-status" role="status" aria-live="polite" style="margin:8px 0"></p>
      <div id="chat-pick"></div>
      <div class="archive-grid"><div class="cards" id="chat-threads">
        ${data.threads.map(item=>`<button type="button" class="card" data-chat-id="${escape(item.id)}" aria-pressed="${item.id===activeThread}">
          <strong>${escape(item.titel)}</strong><small>${item.notizen} Notizen · Stand: ${asDate(item.stand)}</small></button>`).join('') ||
          '<p class="empty">Es wurden noch keine Gespräche übernommen.</p>'}
      </div><section id="chat-notes-list" aria-label="Notizen"></section></div>`;
    const status = section.querySelector('#chat-status');
    status.textContent = feedback;
    const form = section.querySelector('#chat-export');
    form.addEventListener('submit', async event=>{
      event.preventDefault();
      const submit = form.querySelector('[type=submit]');
      const file = form.elements.file.files[0];
      if (!file) return;
      submit.disabled = true;
      section.querySelector('#chat-pick').replaceChildren();
      status.textContent = 'Export wird lokal gelesen …';
      try {
        const preview = await api('preview', file, 'application/octet-stream');
        if (!isOpen(section)) return;
        status.textContent = 'Wähle nur die Unterhaltungen aus „Rechtsberatung“ aus.';
        choose(section.querySelector('#chat-pick'), preview, status, ()=>isOpen(section));
      } catch (error) { status.textContent = error.message; }
      finally { submit.disabled = false; }
    });
    section.querySelector('#chat-threads').addEventListener('click', event=>{
      const button = event.target.closest('[data-chat-id]');
      if (button) {
        activeThread = button.dataset.chatId;
        show();
      }
    });
    if (!selected) return;
    const list = section.querySelector('#chat-notes-list');
    list.innerHTML = '<p>Notizen werden geladen …</p>';
    try {
      const result = await api('threads/' + encodeURIComponent(selected.id));
      if (!isOpen(section)) return;
      renderNotes(list, selected, result.notes);
    } catch (error) { list.textContent = error.message; }
  }

  function choose(container, preview, status, isOpen) {
    container.innerHTML = '<form class="card" style="margin-bottom:14px"><h2>Welche Unterhaltungen gehören dazu?</h2>'+
      '<label>Titel filtern<input id="chat-pick-query" type="search"></label>'+
      '<p id="chat-pick-count" aria-live="polite"></p><div id="chat-pick-rows" style="max-height:300px;overflow:auto"></div>'+
      '<button type="submit" class="primary" style="margin-top:8px">Ausgewählte Unterhaltungen übernehmen</button></form>';
    const selected = new Set(preview.threads.filter(item=>item.known).map(item=>item.id));
    const report = container.querySelector('#chat-pick-count');
    const rows = container.querySelector('#chat-pick-rows');
    const query = container.querySelector('#chat-pick-query');
    query.value = preview.threads.some(item=>normalize(item.title).includes('rechtsberatung')) ? 'Rechtsberatung' : '';
    function draw() {
      const needle = normalize(query.value.trim());
      rows.innerHTML = preview.threads.filter(item=>normalize(item.title).includes(needle)).slice(0,200).map(item=>
        '<label style="display:flex;gap:8px;align-items:start;padding:3px 0"><input style="width:auto;margin-top:5px" data-select-thread="'+escape(item.id)+'" type="checkbox" '+
        (selected.has(item.id)?'checked':'')+'><span>'+escape(item.title)+'<small>'+asDate(item.date)+(item.known?' · Schon importiert':'')+'</small></span></label>'
      ).join('') || '<p>Keine passenden Titel.</p>';
      report.textContent = selected.size + ' ausgewählt · Bei vielen Treffern nach Titel filtern.';
    }
    query.addEventListener('input', draw);
    rows.addEventListener('change', event=>{
      const field = event.target.closest('[data-select-thread]');
      if (!field) return;
      if (field.checked) selected.add(field.dataset.selectThread);
      else selected.delete(field.dataset.selectThread);
      report.textContent = selected.size + ' ausgewählt';
    });
    container.querySelector('form').addEventListener('submit', async event=>{
      event.preventDefault();
      if (!selected.size) { status.textContent='Wähle mindestens eine Unterhaltung aus.'; return; }
      const submit = event.currentTarget.querySelector('[type=submit]');
      submit.disabled = true;
      status.textContent = 'Auswahl wird übernommen …';
      try {
        const result = await api('import', JSON.stringify({token:preview.token,threads:[...selected]}), 'application/json');
        if (!isOpen()) return;
        activeThread = selected.values().next().value;
        await show(result.notes+' neue Notizen · '+result.updated+' aktualisiert · '+result.unchanged+
          ' unverändert · '+result.originals+' Originale übernommen · '+result.missing+' Anlagen ohne lokale Kopie');
      } catch (error) { status.textContent = error.message; }
      finally { submit.disabled = false; }
    });
    draw();
  }

  function renderNotes(container, thread, notes) {
    const source='https://chatgpt.com/c/'+encodeURIComponent(thread.id);
    container.innerHTML = `<h2>${escape(thread.titel)}</h2><p><a href="${source}" target="_blank" rel="noopener">Unterhaltung in ChatGPT öffnen</a></p>
      <div class="archive-tools"><input id="chat-note-search" type="search" placeholder="Notizen und Dateinamen suchen" aria-label="Notizen suchen">
      <select id="chat-note-role" aria-label="Beiträge filtern"><option value="">Alle Beiträge</option><option value="user">Deine Beiträge</option>
      <option value="assistant">ChatGPT-Antworten</option></select></div><div id="chat-note-items" class="cards"></div>`;
    const query = container.querySelector('#chat-note-search');
    const role = container.querySelector('#chat-note-role');
    function draw() {
      const needle = normalize(query.value.trim());
      const matching = notes.filter(note=>(!role.value || role.value === note.rolle) &&
        normalize([note.text,...note.anlagen.map(item=>item.name)].join(' ')).includes(needle));
      container.querySelector('#chat-note-items').innerHTML = matching.map(noteCard).join('') ||
        '<p class="empty">Keine passenden Notizen.</p>';
    }
    query.addEventListener('input', draw);
    role.addEventListener('change', draw);
    draw();
  }
})();
