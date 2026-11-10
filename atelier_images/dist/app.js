const $ = id => document.getElementById(id);
let ready = false, busy = false, current = null, selected = null, polling = false;
let models = [], submitting = false;
let reference = null, referenceUploading = false, previewUrl = null;
let queuePaused = false, queueSignature = '', metricsPolling = false;
let deletingImage = false, galleryRevision = null;
const examples = {
  photo: 'Photographie réaliste d’un renard roux dans une forêt enneigée. Lumière douce du matin, flocons sur son pelage, arrière-plan flou, couleurs naturelles.',
  illustration: 'Une petite maison flottant au-dessus des nuages, un jardin suspendu et des oiseaux dorés. Illustration à l’aquarelle, lumière du matin, couleurs pastel, atmosphère paisible.',
  product: 'Photographie publicitaire d’un flacon de parfum ambré sur une pierre noire. Éclairage latéral doré, reflets délicats, fond sombre, composition minimaliste.'
};
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'La requête a échoué.');
  return data;
}
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function updateButton() {
  $('generate').disabled = !ready || submitting || referenceUploading || !$('model').value;
  $('generate').textContent = submitting ? 'Ajout…' : 'Ajouter à la file ↗';
  $('model').disabled = submitting;
  $('reference-file').disabled = submitting || referenceUploading;
  $('clear-reference').disabled = submitting || referenceUploading;
}
function modelError(message) { $('model-error').textContent = message; $('model-error').hidden = !message; }
function rememberModel(name) { try { localStorage.setItem('atelier-model', name); } catch {} }
function describeModel() {
  const model = models.find(item => item.name === $('model').value);
  const profile = model?.family === 'sd15' ? 'Stable Diffusion 1.5 · 20 étapes · profil mémoire réduit' : model?.family === 'qwen21' ? 'Qwen · génération et retouche · 28 étapes' : model?.variant === 'dev' ? 'Profil Dev · 20 étapes' : 'Profil Schnell · 4 étapes · rapide';
  $('model-info').textContent = model ? `${profile} · ${(model.size / 1024**3).toFixed(2)} Go` : 'Aucun modèle configuré pour le moment.';
  $('reference-panel').hidden = !model?.can_edit;
  if (model) rememberModel(model.name);
  updateButton();
}
async function refreshModels(preferred) {
  const data = await api('/api/models');
  let saved = ''; try { saved = localStorage.getItem('atelier-model') || ''; } catch {}
  const choice = preferred || $('model').value || saved || data.default;
  models = data.models; $('model').replaceChildren();
  for (const item of models) { const option = document.createElement('option'); option.value = item.name; option.textContent = item.label || item.name; $('model').append(option); }
  if (!models.length) { const option = document.createElement('option'); option.value = ''; option.textContent = 'Aucun modèle compatible'; $('model').append(option); }
  if (models.some(item => item.name === choice)) $('model').value = choice;
  modelError(data.excluded.map(item => `${item.name} : ${item.reason}`).join('\n'));
  describeModel();
}
function imageUrl(filename) { return '/images/' + encodeURIComponent(filename); }
function showDetail(item) {
  selected = item;
  $('detail-image').src = imageUrl(item.filename);
  $('detail-image').alt = item.prompt || 'Image générée';
  $('detail-prompt').textContent = item.prompt;
  $('detail-meta').textContent = `${item.width} × ${item.height} · Seed ${item.seed ?? 'inconnue'} · ${item.model || 'Modèle inconnu'}`;
  $('download').href = imageUrl(item.filename);
  $('download').download = item.filename;
  $('detail').showModal();
}
async function refreshGallery() {
  const items = await api('/api/gallery');
  if (selected && !items.some(item => item.filename === selected.filename)) {
    $('detail').close(); $('detail-image').removeAttribute('src'); $('download').removeAttribute('href');
    $('detail-prompt').textContent = ''; $('detail-meta').textContent = ''; selected = null;
  }
  $('gallery-grid').replaceChildren();
  $('count').textContent = items.length;
  $('empty').hidden = items.length > 0;
  for (const item of items) {
    const card = document.createElement('figure'); card.className = 'card';
    const button = document.createElement('button'); button.className = 'image-button'; button.setAttribute('aria-label', 'Agrandir : ' + item.prompt);
    const image = document.createElement('img'); image.src = imageUrl(item.filename); image.alt = item.prompt || 'Image générée'; image.loading = 'lazy';
    button.append(image); button.addEventListener('click', () => showDetail(item));
    const caption = document.createElement('figcaption'), text = document.createElement('p'), meta = document.createElement('div');
    text.textContent = item.prompt || 'Ma création'; meta.className = 'card-meta';
    const dimensions = document.createElement('span'), date = document.createElement('span');
    dimensions.textContent = `${item.width} × ${item.height}`;
    date.textContent = new Date(item.created * 1000).toLocaleDateString('fr-FR', {day:'numeric', month:'short'});
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'delete-image'; remove.textContent = 'Supprimer';
    remove.setAttribute('aria-label', 'Supprimer définitivement cette image');
    remove.addEventListener('click', () => removeImage(item));
    meta.append(dimensions, date); caption.append(text, meta, remove); card.append(button, caption); $('gallery-grid').append(card);
  }
}
async function removeImage(item) {
  if (deletingImage) return;
  if (!confirm('Supprimer définitivement cette image et nettoyer ses traces dans les données locales gérées par Atelier ?\n\nLe PNG sera effacé sans corbeille. Les autres images et leurs prompts seront conservés. Les copies téléchargées, sauvegardes et captures externes ne sont pas couvertes.')) return;
  deletingImage = true; error('');
  document.querySelectorAll('.delete-image').forEach(b => { b.disabled = true; });
  try {
    const result = await api('/api/images/delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename:item.filename})});
    if (selected?.filename === item.filename) {
      $('detail').close(); $('detail-image').removeAttribute('src'); $('download').removeAttribute('href');
      $('detail-prompt').textContent = ''; $('detail-meta').textContent = ''; selected = null;
    }
    if ($('prompt').value === item.prompt) { $('prompt').value = ''; updatePromptLength(); }
    await refreshGallery(); renderQueue(await api('/api/queue'));
    if (result.warnings.length) error('Image supprimée, mais nettoyage local incomplet :\n' + result.warnings.join('\n'));
  } catch (err) { error(err.message); await refreshGallery().catch(() => {}); }
  finally { deletingImage = false; document.querySelectorAll('.delete-image').forEach(b => { b.disabled = false; }); }
}
function renderQueue(data) {
  queuePaused = data.paused;
  $('queue-pause').textContent = data.paused ? 'Reprendre' : 'Mettre en pause';
  const pending = data.jobs.filter(j => !['done', 'error', 'cancelled'].includes(j.state));
  $('queue-count').textContent = pending.reduce((sum, j) => sum + j.count - j.completed, 0);
  $('queue-note').textContent = data.error || (data.paused ? 'En pause : l’image en cours se termine, puis la file attend.' : 'Exécution dans l’ordre · pause et annulation prennent effet après l’image en cours.');
  const visible = data.jobs.filter(j => !['done','cancelled'].includes(j.state));
  $('queue-empty').hidden = visible.length > 0;
  const signature = JSON.stringify(data);
  if (signature !== queueSignature) {
    const labels = {queued:'En attente', submitting:'Envoi au moteur', running:'En cours', done:'Terminé', error:'Erreur', cancelled:'Annulé'};
    $('queue-list').replaceChildren();
    for (const job of visible) {
      const row = document.createElement('li'), body = document.createElement('div'), prompt = document.createElement('p'), meta = document.createElement('small');
      row.className = 'queue-row'; row.dataset.state = job.state;
      prompt.textContent = job.prompt;
      const label = models.find(m => m.name === job.model)?.label || job.model;
      meta.textContent = `${label} · ${job.completed}/${job.count} images · ${job.cancel_requested && !['done','cancelled','error'].includes(job.state) ? 'Arrêt après cette image' : labels[job.state] || job.state}`;
      body.append(prompt, meta);
      if (job.error) { const message = document.createElement('p'); message.className = 'error'; message.textContent = job.error; body.append(message); }
      row.append(body);
      if (!['done','error','cancelled'].includes(job.state)) {
        const cancel = document.createElement('button'); cancel.className = 'text-button'; cancel.textContent = 'Annuler'; cancel.disabled = job.cancel_requested;
        cancel.setAttribute('aria-label', 'Annuler : ' + job.prompt);
        cancel.addEventListener('click', () => controlQueue('cancel', job.id).catch(err => error(err.message))); row.append(cancel);
      }
      if (job.state === 'error') {
        const dismiss = document.createElement('button'); dismiss.className = 'text-button'; dismiss.textContent = 'Retirer';
        dismiss.addEventListener('click', () => controlQueue('dismiss', job.id).catch(err => error(err.message))); row.append(dismiss);
      }
      $('queue-list').append(row);
    }
    queueSignature = signature;
  }
  const active = pending.find(j => ['running','submitting'].includes(j.state));
  busy = Boolean(active); current = active || null; $('progress').hidden = !active;
  if (active) {
    $('progress-title').textContent = `Image ${active.completed + 1} sur ${active.count}`;
    $('progress-text').textContent = active.prompt;
  }
  return data.jobs.reduce((sum, j) => sum + j.images.length, 0);
}
let completedImages = -1;
async function controlQueue(action, id) {
  const data = await api('/api/queue/control', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action,id})});
  renderQueue(data); updateButton();
}
function updateMeter(kind, reading) {
  const meter = $(kind + '-meter'), text = $(kind + '-value');
  if (!reading) { text.textContent = 'Indisponible'; meter.hidden = true; return; }
  const used = reading.used / 1024**3, total = reading.total / 1024**3;
  text.textContent = `${used.toFixed(1)} / ${total.toFixed(1)} Go`;
  meter.hidden = false; meter.max = total; meter.low = total * .7; meter.high = total * .9; meter.value = used;
  meter.parentElement.classList.toggle('memory-high', used / total >= .9);
  meter.setAttribute('aria-valuetext', text.textContent);
  if (kind === 'vram') $('vram-note').textContent = `${reading.name} · cible 8 Go · usage global`;
}
async function pollMetrics() {
  if (metricsPolling) return;
  metricsPolling = true;
  try {
    const data = await api('/api/metrics');
    const fresh = data.sampled_at && Date.now()/1000 - data.sampled_at < 10;
    updateMeter('vram', fresh ? data.vram : null); updateMeter('ram', fresh ? data.ram : null);
  } catch { updateMeter('vram', null); updateMeter('ram', null); }
  finally { metricsPolling = false; }
}
async function poll() {
  if (polling || submitting) return;
  polling = true;
  try {
    const status = await api('/api/status');
    ready = status.ready;
    $('memory-profile').textContent = !ready ? 'Profil mémoire : en attente du moteur.' : status.memory_profile ? 'Profil 8 Go actif · 1 Go réservé au système · générations séquentielles.' : 'Profil mémoire non appliqué : ferme le moteur ComfyUI puis relance Atelier pour activer les réglages 8 Go.';
    $('connection').textContent = ready ? '● Atelier prêt' : '● Démarrage du moteur…';
    $('connection').classList.toggle('ready', ready);
    if (status.error) error(status.error);
    const data = await api('/api/queue');
    const completed = renderQueue(data);
    if (completed !== completedImages || galleryRevision !== status.gallery_revision) {
      await refreshGallery(); completedImages = completed; galleryRevision = status.gallery_revision;
    }
    updateButton();
  } catch (err) {
    ready = false; $('connection').textContent = '● Connexion interrompue'; $('connection').classList.remove('ready');
    error('L’atelier ne répond plus. Relance Lancer_Atelier_Images.bat si nécessaire.'); updateButton();
  } finally { polling = false; }
}
$('form').addEventListener('submit', async event => {
  event.preventDefault(); if (!ready || submitting || referenceUploading || !$('model').value) return;
  error(''); submitting = true; updateButton();
  try {
    if (!updatePromptLength()) throw new Error('Le texte dépasse la limite affichée sous le champ.');
    const prompts = $('multi-prompt').checked ? $('prompt').value.split(/\r?\n/).map(s => s.trim()).filter(Boolean) : [$('prompt').value];
    await api('/api/queue', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({prompts, count:Number($('image-count').value), model:$('model').value, reference:models.find(m => m.name === $('model').value)?.can_edit ? reference : null, format:document.querySelector('[name="format"]:checked').value, seed:$('seed').value === '' ? null : Number($('seed').value)})});
    renderQueue(await api('/api/queue'));
  } catch (err) { busy = false; error(err.message); updateButton(); }
  finally { submitting = false; updateButton(); }
});
$('prompt').addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); $('form').requestSubmit(); } });
function updatePromptLength() {
  const value = $('prompt').value;
  const lengths = ($('multi-prompt').checked ? value.split(/\r?\n/) : [value]).map(line => Array.from(line).length);
  const longest = lengths.reduce((a,b) => Math.max(a,b), 0), total = lengths.reduce((a,b) => a+b, 0);
  const valid = longest <= 100000 && total <= 1000000;
  $('prompt-length').textContent = `${total.toLocaleString('fr-FR')} caractères · ${$('multi-prompt').checked ? 'ligne la plus longue : ' + longest.toLocaleString('fr-FR') + ' · ' : ''}100 000 par prompt, 1 000 000 par envoi. Le modèle peut ne traiter qu’une partie d’un texte très long.`;
  $('prompt-length').classList.toggle('limit-exceeded', !valid);
  $('prompt').setCustomValidity(valid ? '' : 'Limite de texte dépassée. Réduis le prompt ou répartis-le en plusieurs envois.');
  return valid;
}
$('prompt').addEventListener('input', updatePromptLength);
$('multi-prompt').addEventListener('change', updatePromptLength);
document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => { $('prompt').value = examples[button.dataset.example]; updatePromptLength(); $('prompt').focus(); }));
$('refresh').addEventListener('click', () => refreshGallery().catch(err => error(err.message)));
$('close-dialog').addEventListener('click', () => $('detail').close());
$('detail').addEventListener('click', event => { if (event.target === $('detail')) { const r = $('detail').getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) $('detail').close(); } });
$('reuse').addEventListener('click', () => {
  if (!selected) return;
  $('prompt').value = selected.prompt; $('seed').value = selected.seed ?? ''; $('multi-prompt').checked = false;
  updatePromptLength();
  if (models.some(model => model.name === selected.model)) { $('model').value = selected.model; describeModel(); }
  else if (selected.model) modelError('Le modèle de cette image n’est plus disponible. Choisis un autre modèle installé.');
  clearReference();
  if (selected.reference) { reference = selected.reference; $('reference-status').textContent = 'Image de référence précédente reprise. Clique sur Retirer pour créer sans référence.'; $('reference-preview').hidden = false; $('reference-image').hidden = true; $('reference-name').textContent = 'Référence de cette création'; }
  const shape = selected.width === selected.height ? 'square' : selected.width > selected.height ? 'landscape' : 'portrait';
  document.querySelector(`[name="format"][value="${shape}"]`).checked = true;
  $('detail').close(); $('create').scrollIntoView({behavior:'smooth'}); $('prompt').focus();
});
setInterval(() => { if (busy && current) { const seconds = Math.max(0, Math.floor(Date.now()/1000-current.started)); $('elapsed').textContent = seconds < 60 ? `${seconds} s` : `${Math.floor(seconds/60)} min ${seconds%60} s`; } }, 1000);
$('model').addEventListener('change', describeModel);
$('refresh-models').addEventListener('click', () => refreshModels().catch(err => modelError(err.message)));
function clearReference() {
  reference = null; $('reference-file').value = ''; $('reference-preview').hidden = true; $('reference-status').textContent = '';
  $('reference-image').removeAttribute('src'); $('reference-image').hidden = false;
  if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = null;
}
$('clear-reference').addEventListener('click', clearReference);
$('reference-file').addEventListener('change', async event => {
  const file = event.target.files[0]; if (!file) return;
  if (file.size > 20 * 1024 * 1024) { error('Choisis une image de moins de 20 Mo.'); return; }
  clearReference(); referenceUploading = true; updateButton(); error(''); $('reference-status').textContent = 'Préparation de ton image…';
  try {
    const data = await api('/api/reference', {method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file});
    reference = data.name; previewUrl = URL.createObjectURL(file); $('reference-image').src = previewUrl;
    $('reference-name').textContent = file.name; $('reference-preview').hidden = false; $('reference-status').textContent = 'Image prête. Décris la modification souhaitée.';
  } catch (err) { error(err.message); $('reference-status').textContent = ''; }
  finally { referenceUploading = false; updateButton(); }
});
$('queue-pause').addEventListener('click', () => controlQueue(queuePaused ? 'resume' : 'pause').catch(err => error(err.message)));
updatePromptLength();
refreshModels().catch(err => modelError(err.message)); refreshGallery().catch(err => error(err.message)); poll(); setInterval(poll, 2000);
pollMetrics(); setInterval(pollMetrics, 2000);

$('delete-all').addEventListener('click', async () => {
  if (deletingImage || submitting || referenceUploading) return;
  if (!await confirmPurge()) return;
  deletingImage = true;
  $('delete-all').disabled = true;
  $('delete-all').textContent = 'Suppression…';
  $('purge-status').textContent = 'Nettoyage en cours…';
  error('');
  try {
    const result = await api('/api/images/delete-all', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({confirmation:'DELETE_ALL'})});
    $('prompt').value = ''; updatePromptLength(); clearReference();
    $('detail').close(); $('detail-image').removeAttribute('src'); $('detail-image').alt = '';
    $('download').removeAttribute('href'); $('download').removeAttribute('download');
    $('detail-prompt').textContent = ''; $('detail-meta').textContent = '';
    selected = null; current = null;
    await refreshGallery(); renderQueue(await api('/api/queue'));
    $('purge-status').textContent = result.warnings.length
      ? 'Nettoyage incomplet : ' + result.warnings.join(' ')
      : 'Données locales supprimées. La file est en pause. Les journaux techniques peuvent se recréer.';
  } catch (err) {
    error(err.message);
    $('purge-status').textContent = 'Suppression non terminée : ' + err.message;
    await refreshGallery().catch(() => {});
  } finally {
    deletingImage = false; $('delete-all').disabled = false;
    $('delete-all').textContent = 'Tout supprimer';
  }
});

function confirmPurge() {
  const dialog = $('purge-confirm');
  dialog.returnValue = 'cancel';
  return new Promise(resolve => {
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'delete'), {once:true});
    dialog.showModal();
  });
}
