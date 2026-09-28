// Japanese IME: the Enter that confirms a conversion must not save/submit
// (C-08). isComposing covers most browsers; keyCode 229 covers the Enter that
// Safari delivers right after compositionend.
export function isImeComposing(event) {
  return Boolean(event && (event.isComposing || event.keyCode === 229));
}
