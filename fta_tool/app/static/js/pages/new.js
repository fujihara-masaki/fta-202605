// New analysis (B): the two-column form (UI-05) and the sample panel (UI-06).
//
// - Create: the form is still the normal POST /analyses (title, top_event,
//   system_context, incident_context, demo_points), answered by the server's
//   303 to the edit screen. Before it is sent the title is checked like the
//   list's rename (J-22, common/text.js): required and at most 255 characters
//   after trimming, counted in code points. On an error nothing is sent, the
//   reason is shown under the field and the field gets the focus. The title
//   is sent trimmed, as the rename saves it. Once sent, the button is disabled
//   and any further submit is ignored, so repeated clicks create one analysis;
//   in-page links wait too, since following one would cancel the pending
//   navigation after the server may already have created the analysis.
// - Enter in the title submits through the same check; the Enter that
//   confirms an IME conversion does not (C-08, common/ime.js).
// - Sample: choosing a scenario shows it in the preview; 「この内容を入力欄へ転記」
//   fills the top event, both context fields and the hidden demo_points, never
//   the title (J-21), and shows 「サンプルを転記済み・未保存」. Nothing is saved
//   until 作成して編集へ. The data is the JSON the template embeds; text goes
//   in through value / textContent only. Without sample data the panel is not
//   rendered and the form works as before.
// - Unsaved input (J-12): while one of the four visible fields has input,
//   leaving through an in-page link (キャンセル, header) asks 入力を続ける /
//   破棄して移動 (no 保存して移動: the form is saved only by its own button),
//   and reload / closing the tab get the browser's confirmation
//   (common/unsaved.js). Submitting releases the guard first, so the POST
//   itself is never questioned.

import { registerSource, refresh, holdNavigation, releaseNavigation } from '../common/unsaved.js';
import { announce } from '../common/notify.js';
import {
  ANALYSIS_TITLE_MAX,
  countChars,
  normalizeText,
  truncateForDisplay,
  validateAnalysisTitle,
} from '../common/text.js';
import { isImeComposing } from '../common/ime.js';

const form = document.getElementById('new-analysis-form');
const titleInput = document.getElementById('title');
const titleHelp = document.getElementById('title-help');
const titleError = document.getElementById('title-error');
const titleCount = form.querySelector('[data-title-count]');
const topEventInput = document.getElementById('top_event');
const systemInput = document.getElementById('systemContextInput');
const incidentInput = document.getElementById('incidentContextInput');
const demoPointsInput = document.getElementById('demoPointsInput');
const submitButton = form.querySelector('[data-submit]');
const submitStatus = form.querySelector('[data-submit-status]');
const sampleStatus = document.querySelector('[data-sample-status]');
const sampleStatusName = document.querySelector('[data-sample-status-name]');
const samplePanel = form.querySelector('[data-sample-panel]');
const sampleSelect = document.getElementById('sampleSelect');
const samplePreview = document.getElementById('samplePreview');
const applyButton = form.querySelector('[data-apply-sample]');

const SUBMIT_LABEL = submitButton.textContent;
const SLOW_SUBMIT_MS = 10000;

// The four visible inputs: any of them with input is unsaved (J-12).
const FIELDS = [
  { element: titleInput, label: () => `分析タイトル「${truncateForDisplay(titleInput.value)}」` },
  { element: topEventInput, label: '頂上事象' },
  { element: systemInput, label: 'AIへの参考情報：システム構成・対象範囲' },
  { element: incidentInput, label: 'AIへの参考情報：障害発生時の状況・観測事実' },
];

const LEAVE_PROMPT = {
  title: '作成していない入力があります',
  lead: '次の項目に入力があります。分析はまだ作成されていません。',
  note: '移動すると、入力した内容は失われます。保存するには「入力を続ける」を選び、「作成して編集へ」を押してください。',
  continueLabel: '入力を続ける',
};

let submitting = false;
let slowTimer = null;

function asText(value) {
  if (typeof value === 'string') return value;
  return value === null || value === undefined ? '' : String(value);
}

// ----- Title ---------------------------------------------------------------

function updateCounter() {
  const length = countChars(normalizeText(titleInput.value));
  titleCount.textContent = String(length);
  titleHelp.dataset.overLimit = length > ANALYSIS_TITLE_MAX ? 'true' : 'false';
}

function showTitleError(message) {
  titleError.textContent = message;
  titleError.hidden = false;
  titleInput.setAttribute('aria-invalid', 'true');
}

function clearTitleError() {
  titleError.textContent = '';
  titleError.hidden = true;
  titleInput.removeAttribute('aria-invalid');
}

// ----- Sample --------------------------------------------------------------

function readSamples() {
  const node = document.getElementById('sample-scenarios-data');
  if (!node) return [];
  try {
    const data = JSON.parse(node.textContent || '[]');
    return Array.isArray(data) ? data.filter((item) => item && typeof item === 'object') : [];
  } catch {
    return [];
  }
}

const samples = readSamples();

function sampleName(sample) {
  return `[${asText(sample.category)}] ${asText(sample.title)}`;
}

function selectedSample() {
  const id = sampleSelect ? sampleSelect.value : '';
  if (!id) return null;
  return samples.find((sample) => asText(sample.id) === id) || null;
}

function showPreview() {
  const sample = selectedSample();
  samplePreview.hidden = !sample;
  if (!sample) return;
  document.getElementById('samplePreviewTopEvent').textContent = asText(sample.top_event);
  document.getElementById('samplePreviewSystem').textContent = asText(sample.system_context);
  document.getElementById('samplePreviewIncident').textContent = asText(sample.incident_context);
}

function showSampleStatus(name) {
  sampleStatusName.textContent = name ? `（${name}）` : '';
  sampleStatus.hidden = false;
}

function hideSampleStatus() {
  sampleStatusName.textContent = '';
  sampleStatus.hidden = true;
}

function applySample() {
  const sample = selectedSample();
  if (!sample || submitting) return;
  topEventInput.value = asText(sample.top_event);
  systemInput.value = asText(sample.system_context);
  incidentInput.value = asText(sample.incident_context);
  demoPointsInput.value = asText(sample.demo_points);
  // The title is left as it is (J-21).
  showSampleStatus(sampleName(sample));
  refresh();
  const titleMissing = !normalizeText(titleInput.value);
  announce(
    `サンプル「${asText(sample.title)}」を頂上事象と参考情報へ転記しました。まだ保存されていません。`
      + (titleMissing ? '分析タイトルを入力してください。' : ''),
  );
  // Not transferred, the title is what to enter next when it is empty.
  if (titleMissing) titleInput.focus();
}

// A demo_points value restored by the browser (back / forward) still comes
// from a sample: say so, as right after the transfer.
function restoreSampleStatus() {
  const restored = demoPointsInput.value;
  if (!restored) return;
  const sample = samples.find((item) => asText(item.demo_points) === restored);
  showSampleStatus(sample ? sampleName(sample) : '');
}

// ----- Unsaved input -------------------------------------------------------

// 破棄して移動: the input is dropped before the page is left.
function discardInput() {
  for (const { element } of FIELDS) element.value = '';
  demoPointsInput.value = '';
  hideSampleStatus();
  clearTitleError();
  updateCounter();
}

FIELDS.forEach(({ element, label }, index) => {
  registerSource({
    id: `new-analysis:${element.id}`,
    order: index + 1,
    label,
    isDirty: () => !submitting && normalizeText(element.value) !== '',
    discard: discardInput,
    prompt: LEAVE_PROMPT,
  });
});

// ----- Submit --------------------------------------------------------------

function setSubmitting(on) {
  submitting = on;
  window.clearTimeout(slowTimer);
  submitButton.disabled = on;
  submitButton.textContent = on ? '作成しています…' : SUBMIT_LABEL;
  for (const { element } of FIELDS) element.readOnly = on;
  if (applyButton) applyButton.disabled = on;
  submitStatus.textContent = on ? '分析を作成しています…' : '';
  if (on) {
    form.setAttribute('aria-busy', 'true');
    holdNavigation('分析を作成しています。画面が切り替わるまでお待ちください。');
    slowTimer = window.setTimeout(() => {
      const message = '作成に時間がかかっています。サーバーが別の処理（生成など）を実行中の可能性があります。画面が切り替わるまでお待ちください。';
      submitStatus.textContent = message;
      announce(message);
    }, SLOW_SUBMIT_MS);
  } else {
    form.removeAttribute('aria-busy');
    releaseNavigation();
  }
  // While submitting no field counts as unsaved, so the browser does not ask
  // before the POST navigates away.
  refresh();
}

form.addEventListener('submit', (event) => {
  if (submitting) {
    event.preventDefault(); // already sent: never a second analysis
    return;
  }
  const invalid = validateAnalysisTitle(titleInput.value);
  if (invalid) {
    event.preventDefault();
    showTitleError(invalid);
    titleInput.focus();
    announce(invalid, { assertive: true });
    return;
  }
  titleInput.value = normalizeText(titleInput.value); // sent trimmed, like the rename
  clearTitleError();
  updateCounter();
  setSubmitting(true);
});

titleInput.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  if (isImeComposing(event)) {
    // The Enter that confirms an IME conversion is not a submit (C-08).
    // While the conversion is open the IME owns the key; the one Safari
    // sends right after it (keyCode 229) must not reach the browser's
    // implicit submission.
    if (!event.isComposing) event.preventDefault();
    return;
  }
  // A normal Enter submits through the same check as the button.
  event.preventDefault();
  if (!submitting) form.requestSubmit(submitButton);
});

form.addEventListener('input', (event) => {
  if (event.target === titleInput) {
    updateCounter();
    if (!titleError.hidden && !validateAnalysisTitle(titleInput.value)) clearTitleError();
  }
  refresh();
});

// Back on this page from the back/forward cache after submitting: the page
// is live again, so the form must be usable (and protected) again.
window.addEventListener('pageshow', (event) => {
  if (event.persisted && submitting) setSubmitting(false);
});

// ----- Start ---------------------------------------------------------------

form.noValidate = true; // the check above replaces the browser's own message
const titleMax = form.querySelector('[data-title-max]');
if (titleMax) titleMax.textContent = String(ANALYSIS_TITLE_MAX);
updateCounter();

if (sampleSelect && samples.length) {
  sampleSelect.addEventListener('change', showPreview);
  applyButton.addEventListener('click', applySample);
  showPreview(); // a choice restored by the browser
} else if (samplePanel) {
  samplePanel.remove(); // the embedded data could not be read
}
restoreSampleStatus();
refresh();
