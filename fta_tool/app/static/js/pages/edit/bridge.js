// window.ftaEditBridge: the page's partial update, reachable from outside
// the modules (the browser tests and the console use it to show the
// server's current state without a reload). Until PR-6 it was also the way
// the legacy app.js reached the new screen for generation; app.js and its
// overlay are gone (edit/generation.js), and with them the bridge's other
// functions.
//   refresh(options)   show the server's current state by a partial update
//                      (edit/refresh.js; held back while a generation runs)

export function installBridge(app) {
  const bridge = {
    refresh: (options) => app.refresh(options || {}),
  };
  window.ftaEditBridge = Object.freeze(bridge);
  return bridge;
}
