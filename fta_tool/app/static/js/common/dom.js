// Small DOM builder. Text is always inserted as text nodes (never innerHTML),
// so user input and LLM output can be passed in safely.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (name === 'class') node.className = value;
    else if (name === 'dataset') Object.assign(node.dataset, value);
    else if (value === true) node.setAttribute(name, '');
    else node.setAttribute(name, String(value));
  }
  append(node, children);
  return node;
}

export function append(parent, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

// Paragraph-per-string helper for dialog / notification bodies.
export function paragraphs(items) {
  return [items].flat().filter((item) => item !== null && item !== undefined && item !== false)
    .map((item) => (item instanceof Node ? item : el('p', {}, item)));
}

export function focusElement(target) {
  if (target && target.isConnected && typeof target.focus === 'function') {
    target.focus();
    return document.activeElement === target;
  }
  return false;
}
