// The generation's connection to the save coordinator (PR-4; plan 5.9.1
// steps 1-4, J-09). The legacy generation of app.js (still used until PR-6)
// calls window.ftaEditBridge.beginGeneration(level) before it sends anything
// and the returned end() when it is completely done:
//
//   preparing  generation buttons off at once (no second start); saves in
//              flight (title, ①, judgements) are awaited until none is left —
//              a judgement queued for the same factor starts when the one
//              before it ends, so the parents are fixed only after the last
//              one was saved; if the title being
//              edited could not be saved, nothing is generated; then the
//              automatic save through the same saveSource() as the save
//              buttons: 一次 (normal and additional) — the top event (empty:
//              nothing is generated) and the reference information; 二次・三次
//              — the reference information only, the saved top event is used
//              (J-09). A failed save: nothing is generated, the input stays.
//   running    the requests (app.generating: no partial update meanwhile).
//   finishing  the partial update that shows the result, until it has
//              succeeded or failed (no time limit: a phase that ended before
//              the update would let 保存して移動 run while the page is still
//              being changed); then idle.
// In every phase but idle the coordinator refuses 保存して移動 (5.9.3-1).
// The phase is never stored: a reload starts idle.
//
// Left for PR-6: the waiting display and 生成を取りやめる of the preparation,
// blocking writes and in-page links during a generation, the two-choice
// dialog for a factor switch, the generation log and result categories, and
// the browser's leave confirmation during a generation (E-G08).

import { notify } from '../../common/notify.js';
import { normalizeText } from '../../common/text.js';
import {
  getGenerationPhase,
  isSaving,
  lastFailure,
  saveSource,
  setGenerationPhase,
  whenAllIdle,
} from '../../common/unsaved.js';

export function createGeneration(app, { step1, title }) {
  function fail(reason) {
    setGenerationPhase('idle');
    app.setGenerating(false);
    notify(reason, { type: 'error' });
    return null;
  }

  async function end() {
    setGenerationPhase('finishing');
    app.setGenerating(false); // the update held back during the requests runs now
    try {
      await app.whenRefreshed(); // resolves once the update has been applied or has failed
    } finally {
      setGenerationPhase('idle');
    }
  }

  // Saves in flight (save sources and the page's writes: judgements, the
  // top event), again and again until none is left.
  async function waitForSaves() {
    for (;;) {
      await whenAllIdle();
      while (app.writes.inFlight > 0) await app.writes.whenIdle();
      await Promise.resolve(); // let a write that starts when another ends begin
      if (!isSaving() && app.writes.inFlight === 0) return;
    }
  }

  async function begin(level) {
    if (app.gone) return fail('分析が見つかりません（削除された可能性があります）');
    if (getGenerationPhase() !== 'idle') {
      notify('別の生成の準備中または実行中です。完了までお待ちください。', { type: 'warning' });
      return null;
    }
    setGenerationPhase('preparing');
    app.setGenerating(true);
    try {
      await waitForSaves();
      if (title && title.source.isDirty()) {
        const failure = lastFailure(title.source);
        return fail(`分析タイトルの保存に失敗したため、生成を開始しませんでした：${failure ? failure.reason : '保存していない変更があります'}`);
      }
      if (step1) {
        if (Number(level) === 1) {
          if (!normalizeText(step1.fields.top.value)) {
            const result = fail('頂上事象を入力してから生成してください');
            step1.fields.top.focus();
            return result;
          }
          if (step1.topEvent.isDirty()) {
            const outcome = await saveSource(step1.topEvent);
            if (!outcome.ok) return fail(`頂上事象の保存に失敗したため、生成を開始しませんでした：${outcome.reason}`);
            notify('編集中の頂上事象を保存してから生成します', { type: 'success' });
          }
        }
        if (step1.context.isDirty()) {
          const outcome = await saveSource(step1.context);
          if (!outcome.ok) return fail(`参考情報の保存に失敗したため、生成を開始しませんでした：${outcome.reason}`);
          notify('編集中の参考情報を保存してから生成します', { type: 'success' });
        }
      }
      if (app.gone) return fail('分析が見つかりません（削除された可能性があります）');
    } catch {
      return fail('生成の準備中にエラーが発生したため、生成を開始しませんでした');
    }
    setGenerationPhase('running');
    let ended = false;
    return {
      end: () => {
        if (ended) return Promise.resolve();
        ended = true;
        return end();
      },
    };
  }

  return { begin };
}
