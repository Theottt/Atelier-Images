const $ = id => document.getElementById(id);
let ready = false, busy = false, current = null, selected = null, polling = false;
let models = [], submitting = false;
let reference = null, referenceUploading = false, previewUrl = null;
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
  $('generate').disabled = !ready || busy || referenceUploading || !$('model').value;
  $('generate').textContent = busy ? 'Création en cours…' : 'Créer mon image ↗';
  $('model').disabled = busy;
  $('reference-file').disabled = busy || referenceUploading;
  $('clear-reference').disabled = busy || referenceUploading;
}
function modelError(message) { $('model-error').textContent = message; $('model-error').hidden = !message; }
function rememberModel(name) { try { localStorage.setItem('atelier-model', name); } catch {} }
function describeModel() {
  const model = models.find(item => item.name === $('model').value);
  const profile = model?.family === 'qwen21' ? 'Qwen · génération et retouche · 28 étapes' : model?.variant === 'dev' ? 'Profil Dev · 20 étapes' : 'Profil Schnell · 4 étapes · rapide';
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
    meta.append(dimensions, date); caption.append(text, meta); card.append(button, caption); $('gallery-grid').append(card);
  }
}
function showJob(job) {
  current = job; busy = true; $('progress').hidden = false;
  $('progress-title').textContent = job.state === 'queued' ? 'Ton idée attend son tour…' : 'Ton image prend forme…';
  updateButton();
}
async function poll() {
  if (polling || submitting) return;
  polling = true;
  try {
    const status = await api('/api/status');
    ready = status.ready;
    $('connection').textContent = ready ? '● Atelier prêt' : '● Démarrage du moteur…';
    $('connection').classList.toggle('ready', ready);
    if (status.error) error(status.error);
    if (ready && status.job) {
      const job = await api('/api/job');
      if (submitting) return;
      if (['queued','running'].includes(job.state)) showJob(job);
      else {
        const changed = current?.id !== job.id || busy;
        busy = false; current = job; $('progress').hidden = true;
        if (job.state === 'error') error(job.error);
        if (job.state === 'done' && changed) { error(''); await refreshGallery(); }
      }
    }
    updateButton();
  } catch (err) {
    ready = false; $('connection').textContent = '● Connexion interrompue'; $('connection').classList.remove('ready');
    error('L’atelier ne répond plus. Relance Lancer_Atelier_Images.bat si nécessaire.'); updateButton();
  } finally { polling = false; }
}
$('form').addEventListener('submit', async event => {
  event.preventDefault(); if (!ready || busy || referenceUploading || !$('model').value) return;
  error(''); busy = true; submitting = true; updateButton();
  try {
    const job = await api('/api/generate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({prompt:$('prompt').value, model:$('model').value, reference:models.find(m => m.name === $('model').value)?.can_edit ? reference : null, format:document.querySelector('[name="format"]:checked').value, seed:$('seed').value === '' ? null : Number($('seed').value)})});
    showJob(job);
  } catch (err) { busy = false; error(err.message); updateButton(); }
  finally { submitting = false; }
});
$('prompt').addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); $('form').requestSubmit(); } });
document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => { $('prompt').value = examples[button.dataset.example]; $('prompt').focus(); }));
$('refresh').addEventListener('click', () => refreshGallery().catch(err => error(err.message)));
$('close-dialog').addEventListener('click', () => $('detail').close());
$('detail').addEventListener('click', event => { if (event.target === $('detail')) { const r = $('detail').getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) $('detail').close(); } });
$('reuse').addEventListener('click', () => {
  if (!selected) return;
  $('prompt').value = selected.prompt; $('seed').value = selected.seed ?? '';
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
refreshModels().catch(err => modelError(err.message)); refreshGallery().catch(err => error(err.message)); poll(); setInterval(poll, 3000);
