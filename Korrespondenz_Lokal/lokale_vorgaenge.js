'use strict';
(() => {
  const nav = document.querySelector('#nav');
  const view = document.querySelector('#view');
  const top = document.querySelector('.top');
  const online = location.protocol === 'http:' && location.hostname === '127.0.0.1';
  let revision = 0;
  const filters = {group:'', status:'', sort:'due'};
  const sortOptions = [['due','Nächste Frist'],['newest','Zuletzt angelegt'],['title','Titel A–Z']];
  const groupOf = item => item.bereich || 'Anderes';
  const dueLabel = date => date.split('-').reverse().join('.');
  const titleOrder = new Intl.Collator('de',{numeric:true,sensitivity:'base'});
  const orders = {
    due:(left,right)=>Number(!left.naechste_frist)-Number(!right.naechste_frist) ||
      (left.naechste_frist || '').localeCompare(right.naechste_frist || '') || right.id-left.id,
    newest:(left,right)=>right.id-left.id,
    title:(left,right)=>titleOrder.compare(left.titel,right.titel) || right.id-left.id
  };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  })[char]);
  async function api(path, options) {
    const result = await fetch('/api/' + path, options);
    const data = await result.json();
    if (!result.ok) throw new Error(data.error || 'Anfrage fehlgeschlagen.');
    return data;
  }
  function postJson(path, values) {
    return api(path, {method:'POST',headers:{'Content-Type':'application/json','X-Korrespondenz':'lokal'},
      body:JSON.stringify(values)});
  }
  function navigation() {
    if (nav.querySelector('#local-cases')) return;
    const entry = document.createElement('button');
    entry.type = 'button';
    entry.id = 'local-cases';
    entry.innerHTML = '<span aria-hidden="true">▤</span><span>Vorgänge</span>';
    entry.addEventListener('click', () => show());
    nav.insertBefore(entry, nav.querySelector('[data-action="nav"][data-id="case"]'));
  }
  navigation();
  new MutationObserver(navigation).observe(nav,{childList:true});
  top.querySelector('[data-action=import]').addEventListener('click', event => {
    event.stopPropagation();
    show(undefined, true);
  });
  function message(element, text) {
    if (element) element.textContent = text;
  }
  function stateOptions(statuses, active) {
    return statuses.map(value=>`<option value="${escape(value)}"${value===active?' selected':''}>${escape(value)}</option>`).join('');
  }
  function filterRow(key, label, values) {
    return `<div class="case-filter-row" role="group" aria-label="${label}">
      <span class="case-filter-label" aria-hidden="true">${label}</span>
      <div class="case-chips">${['',...values].map(value=>`<button type="button" data-filter="${key}"
        data-value="${escape(value)}" aria-pressed="${filters[key]===value}">${escape(value || 'Alle')}</button>`).join('')}</div></div>`;
  }
  function drawCases(section, allCases, active) {
    const filtered = allCases.filter(item=>(!filters.group || groupOf(item)===filters.group) &&
      (!filters.status || item.status===filters.status)).sort(orders[filters.sort]);
    section.querySelector('#local-case-list').innerHTML = filtered.map(item=>
      `<button type="button" class="card local-case-row" data-local-case="${item.id}" aria-pressed="${item.id===active?.id}">
        <span><strong>${escape(item.titel)}</strong><small>${escape(groupOf(item))} · ${escape(item.status)} · ${item.dokumente} Dokumente</small></span>
        ${item.naechste_frist?`<small class="case-due-label">Frist ${escape(dueLabel(item.naechste_frist))}</small>`:''}
      </button>`).join('') || (allCases.length ?
        '<p class="empty">Keine Vorgänge passen zu den gewählten Filtern.</p>' :
        '<p class="empty">Lege einen Vorgang an, um Dokumente zu importieren.</p>');
    section.querySelectorAll('[data-filter]').forEach(button=>{
      button.setAttribute('aria-pressed', String(filters[button.dataset.filter]===button.dataset.value));
    });
  }
  // Texterkennung läuft im Hintergrund. Solange ein Dokument wartet, fragt die Ansicht den Stand ab.
  const PENDING = ['Wartet auf Texterkennung','Texterkennung läuft'];
  const isPending = doc => PENDING.includes(doc.ocr_status);
  function documentCard(doc) {
    const source = doc.titel_seite ? doc.titel_quelle + ' von Seite ' + doc.titel_seite : doc.titel_quelle;
    const id = Number(doc.id);
    const failed = !isPending(doc) && doc.ocr_fehler;
    return `<article class="card" data-doc-card="${id}"><h3>${escape(doc.titel)}</h3>
      <small>${escape(doc.dateiname)} · <span aria-live="polite">${isPending(doc)?'⏳ ':''}${escape(doc.ocr_status)}</span></small>
      <small>Titelquelle: ${escape(source)}</small>
      ${failed?`<details><summary>Fehlerdetails</summary><p style="white-space:pre-wrap;overflow-wrap:anywhere">${escape(doc.ocr_fehler)}</p></details>`:''}
      <div class="tools" style="margin-top:8px">
        <a href="/api/documents/${id}/original" target="_blank" rel="noopener">Original öffnen</a>
        <button type="button" data-doc-action="text" data-doc="${id}">Dokumenttext</button>
        <button type="button" data-doc-action="rename" data-doc="${id}">Titel bearbeiten</button>
        ${isPending(doc)?'':`<button type="button" data-doc-action="ocr" data-doc="${id}">Text erneut erkennen</button>`}
      </div><div data-doc-details="${id}"></div></article>`;
  }
  // Aktualisiert nur geänderte Dokumentkarten, damit offene Formulare erhalten bleiben.
  async function followRecognition(section, caseId, documents, isCurrent) {
    while (isCurrent() && documents.some(isPending)) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      if (!isCurrent()) return;
      let fresh;
      try { fresh = (await api('cases/' + caseId + '/documents')).documents; } catch { continue; }
      for (const doc of fresh) {
        const known = documents.find(item => item.id === doc.id);
        if (!known || (known.ocr_status === doc.ocr_status && known.titel === doc.titel)) continue;
        Object.assign(known, doc);
        const card = section.querySelector('[data-doc-card="' + doc.id + '"]');
        const busy = card && card.querySelector('[data-doc-details]').firstChild;
        if (card && !busy) card.outerHTML = documentCard(doc);
      }
    }
  }
  async function startScan(caseId, button, status, isCurrent) {
    button.disabled = true;
    try {
      message(status, 'Der macOS-Scandialog wird geöffnet …');
      const job = await postJson('cases/' + caseId + '/scan', {});
      message(status, 'Scanne im macOS-Dialog und wähle dort „Scans übernehmen“.');
      let outcome;
      do {
        await new Promise(resolve => setTimeout(resolve, 1200));
        outcome = await postJson('scans/' + job.id + '/poll', {});
      } while (outcome.state === 'open');
      if (!isCurrent()) return;
      if (outcome.state === 'done') {
        await show(caseId);
        message(view.querySelector('#local-status'), outcome.imported + ' Scan(s) importiert · ' +
          outcome.duplicates + ' bereits vorhanden' + (outcome.errors.length ? ' · ' + outcome.errors.join(' · ') : ''));
      } else {
        message(status, outcome.state === 'cancelled' ? 'Scan abgebrochen.' : 'Der macOS-Scandialog wurde mit einem Fehler beendet.');
      }
    } catch (error) {
      message(status, error.message);
    } finally {
      button.disabled = false;
    }
  }
  async function show(caseId, focusUpload = false) {
    const current = ++revision;
    nav.querySelectorAll('[aria-current]').forEach(node=>node.removeAttribute('aria-current'));
    nav.querySelector('#local-cases').setAttribute('aria-current','page');
    document.querySelector('#main').classList.remove('mobile-preview');
    view.innerHTML = '<section class="list-page" id="local-view"><h1>Vorgänge</h1><p id="local-status" aria-live="polite">Wird geladen …</p></section>';
    const section = view.querySelector('#local-view');
    const isCurrent = () => current === revision && section.isConnected;
    if (!online) {
      message(section.querySelector('#local-status'), 'Zum Anlegen von Vorgängen und Importieren mit OCR öffne Korrespondenz_Starten.command im Programmordner.');
      return;
    }
    try {
      const backend = await api('cases');
      if (!isCurrent()) return;
      const active = backend.cases.find(item=>item.id === caseId) || (focusUpload ? backend.cases[0] : null);
      const assignedGroups = [...new Set([...backend.groups, ...backend.cases.map(groupOf)])];
      const statuses = [...new Set([...backend.statuses, ...backend.cases.map(item=>item.status).filter(Boolean)])];
      const documents = active ? (await api('cases/' + active.id + '/documents')).documents : [];
      if (!isCurrent()) return;
      section.innerHTML = `<header class="case-list-heading"><h1>Vorgänge</h1>
        <button class="primary" id="new-local-case" type="button" aria-expanded="false" aria-controls="local-case-form">+ Neuer Vorgang</button></header>
        <div class="case-filters">
          ${filterRow('group','Bereich',assignedGroups)}
          <div class="case-filters-secondary">
            ${filterRow('status','Status',statuses)}
            <label class="case-sort"><span>Sortieren</span><select id="local-sort">
              ${sortOptions.map(([key,label])=>`<option value="${key}"${filters.sort===key?' selected':''}>${label}</option>`).join('')}
            </select></label>
          </div>
        </div>
        <p id="local-status" class="case-feedback" role="status"></p>
        <form id="local-case-form" class="card" hidden>
          <label>Titel des Vorgangs<input name="title" maxlength="160" required></label>
          <label>Bereich<select name="group">${stateOptions(backend.groups, backend.groups.includes(filters.group) ? filters.group : 'Anderes')}</select></label>
          <label>Beschreibung (optional)<textarea name="description" maxlength="4000"></textarea></label>
          <label>Status<select name="status">${stateOptions(backend.statuses, backend.statuses.includes(filters.status) ? filters.status : active?.status)}</select></label>
          <label>Nächste Frist (optional)<input type="date" name="due"></label>
          <button class="primary" type="submit">Vorgang anlegen</button>
        </form>
        <div class="archive-grid case-results${active?'':' case-results-full'}"><div class="cards" id="local-case-list">
        </div>${active ? `<div class="cards"><div class="card"><h2>${escape(active.titel)}</h2>
            ${active.beschreibung?'<p>'+escape(active.beschreibung)+'</p>':''}
            <label style="display:block;margin:8px 0">Bereich<select id="local-group-select">
              ${backend.groups.includes(groupOf(active))?'':'<option selected disabled>'+escape(groupOf(active))+'</option>'}
              ${stateOptions(backend.groups, groupOf(active))}</select></label>
            <label style="display:block;margin:8px 0">Status<select id="local-status-select">${stateOptions(backend.statuses, active.status)}</select></label>
            <form id="local-due-form" class="case-due-form"><label>Nächste Frist
              <input type="date" name="due" value="${escape(active.naechste_frist)}"></label>
              <button type="submit">Frist speichern</button></form>
            <form id="local-upload" style="margin-top:10px"><label>Dokumente auswählen
            <input name="files" type="file" accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff" multiple required></label>
            <small>PDF, JPEG, PNG oder TIFF · bis 25 MB je Datei · ${backend.ocr?'Texterkennung bis 40 Seiten':backend.ocr_loading?'Texterkennung wird vorbereitet':'Texterkennung nicht verfügbar'}</small>
            <div class="tools"><button class="primary" type="submit">Importieren und Text erkennen</button>
            <button id="local-scan" type="button">Dokument scannen</button></div></form></div>
          ${documents.map(documentCard).join('')}</div>`:''}</div>`;

      const status = section.querySelector('#local-status');
      drawCases(section, backend.cases, active);
      if (active) followRecognition(section, active.id, documents, isCurrent);
      section.querySelector('.case-filters').addEventListener('click', event => {
        const button = event.target.closest('[data-filter]');
        if (!button) return;
        filters[button.dataset.filter] = button.dataset.value;
        drawCases(section, backend.cases, active);
      });
      section.querySelector('#local-sort').addEventListener('change', event => {
        filters.sort = event.currentTarget.value;
        drawCases(section, backend.cases, active);
      });
      section.querySelector('#local-case-list').addEventListener('click', event => {
        const button = event.target.closest('[data-local-case]');
        if (button) show(Number(button.dataset.localCase));
      });
      const create = section.querySelector('#local-case-form');
      const newButton = section.querySelector('#new-local-case');
      newButton.addEventListener('click', () => {
        create.hidden = !create.hidden;
        newButton.setAttribute('aria-expanded', String(!create.hidden));
        if (!create.hidden) create.elements.title.focus();
      });
      create.addEventListener('submit', async event => {
        event.preventDefault();
        const submit = create.querySelector('[type=submit]');
        submit.disabled = true;
        try {
          const data = await postJson('cases', Object.fromEntries(new FormData(create)));
          await show(data.id);
          message(view.querySelector('#local-status'), 'Vorgang angelegt.');
        } catch (error) {
          message(status, error.message);
          submit.disabled = false;
        }
      });
      const upload = section.querySelector('#local-upload');
      if (focusUpload) {
        if (upload) upload.elements.files.focus();
        else newButton.click();
      }
      if (!active || !upload) return;
      const dueForm = section.querySelector('#local-due-form');
      dueForm.addEventListener('submit', async event => {
        event.preventDefault();
        const submit = dueForm.querySelector('button');
        submit.disabled = true;
        try {
          await postJson('cases/' + active.id + '/due', {due:dueForm.elements.due.value});
          if (!isCurrent()) return;
          await show(active.id);
          message(view.querySelector('#local-status'), 'Frist gespeichert.');
        } catch (error) {
          message(status, error.message);
          submit.disabled = false;
        }
      });
      const caseGroup = section.querySelector('#local-group-select');
      caseGroup.addEventListener('change', async () => {
        caseGroup.disabled = true;
        try {
          await postJson('cases/' + active.id + '/group', {group:caseGroup.value});
          if (!isCurrent()) return;
          await show(active.id);
          message(view.querySelector('#local-status'), 'Bereich gespeichert.');
        } catch (error) {
          caseGroup.value = groupOf(active);
          caseGroup.disabled = false;
          message(status, error.message);
        }
      });
      const caseStatus = section.querySelector('#local-status-select');
      caseStatus.addEventListener('change', async () => {
        caseStatus.disabled = true;
        try {
          await postJson('cases/' + active.id + '/status', {status:caseStatus.value});
          if (!isCurrent()) return;
          await show(active.id);
          message(view.querySelector('#local-status'), 'Status gespeichert.');
        } catch (error) {
          caseStatus.value = active.status;
          caseStatus.disabled = false;
          message(status, error.message);
        }
      });
      section.querySelector('#local-scan').addEventListener('click', event =>
        startScan(active.id, event.currentTarget, status, isCurrent));
      upload.addEventListener('submit', async event => {
        event.preventDefault();
        const submit = upload.querySelector('[type=submit]');
        const files = [...upload.elements.files.files];
        const failures = [];
        let imported = 0;
        let duplicates = 0;
        submit.disabled = true;
        for (const file of files) {
          message(status, 'Verarbeite „' + file.name + '“ …');
          try {
            const result = await api('cases/' + active.id + '/documents', {method:'POST',
              headers:{'X-Korrespondenz':'lokal','X-Dateiname':encodeURIComponent(file.name)},body:file});
            if (result.created) imported++; else duplicates++;
          } catch (error) { failures.push(file.name + ': ' + error.message); }
        }
        if (!isCurrent()) return;
        await show(active.id);
        message(view.querySelector('#local-status'),
          imported + ' importiert · ' + duplicates + ' bereits vorhanden' + (failures.length ? ' · ' + failures.join(' · ') : ''));
      });
      section.addEventListener('click', async event => {
        const control = event.target.closest('[data-doc-action]');
        if (!control) return;
        const id = Number(control.dataset.doc);
        const doc = documents.find(item=>item.id === id);
        const detail = section.querySelector('[data-doc-details="' + id + '"]');
        if (control.dataset.docAction === 'ocr') {
          control.disabled = true;
          try {
            await postJson('documents/' + id + '/ocr', {});
            Object.assign(doc, {ocr_status:'Wartet auf Texterkennung', ocr_fehler:null});
            section.querySelector('[data-doc-card="' + id + '"]').outerHTML = documentCard(doc);
            followRecognition(section, active.id, documents, isCurrent);
          } catch (error) { message(status, error.message); control.disabled = false; }
          return;
        }
        if (control.dataset.docAction === 'text') {
          if (detail.firstChild) { detail.replaceChildren(); return; }
          control.disabled = true;
          try {
            const result = await api('documents/' + id + '/pages');
            detail.innerHTML = result.pages.map(page=>`<details><summary>Seite ${page.nummer} · ${page.methode==='ocr'?'OCR':'PDF-Text'}</summary>
              <p style="white-space:pre-wrap;padding:10px;overflow-wrap:anywhere">${escape(page.text)}</p></details>`).join('') || '<p>Kein Dokumenttext gespeichert.</p>';
          } catch (error) { message(status, error.message); }
          finally { control.disabled = false; }
          return;
        }
        detail.innerHTML = `<form><label>Dokumenttitel<input name="title" value="${escape(doc.titel)}" maxlength="160" required></label>
          <button class="primary" type="submit">Titel speichern</button></form>`;
        const form = detail.querySelector('form');
        form.elements.title.focus();
        form.addEventListener('submit', async submitEvent => {
          submitEvent.preventDefault();
          try {
            await postJson('documents/' + id + '/title',{title:form.elements.title.value});
            await show(active.id);
            message(view.querySelector('#local-status'),'Titel gespeichert.');
          } catch (error) { message(status,error.message); }
        });
      });
    } catch (error) {
      if (isCurrent()) message(section.querySelector('#local-status'), error.message);
    }
  }
})();
