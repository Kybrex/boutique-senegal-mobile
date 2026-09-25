const sessions = new Map();
let activeOverlay = null;
export default function ({ data, setTriggerValue }) {
  for (const key of sessions.keys()) if (key !== data.nonce) sessions.delete(key);
  if (!sessions.has(data.nonce)) sessions.set(data.nonce, {deadline:Date.now()+data.remaining_ms,lastSignal:0,pending:false,locked:false});
  const state = sessions.get(data.nonce);
  if (state.timeoutMs !== data.timeout_ms) {
    state.timeoutMs = data.timeout_ms;
    state.deadline = Date.now() + data.remaining_ms;
  }
  let { deadline, lastSignal, locked } = state;
  let overlay = null;
  function lock() {
    if (locked) return;
    locked = true;
    state.locked = true;
    if (activeOverlay) activeOverlay.remove();
    overlay = document.createElement('div');
    activeOverlay = overlay;
    overlay.setAttribute('role', 'alertdialog');
    overlay.setAttribute('aria-label', 'Session verrouillée');
    Object.assign(overlay.style, {position:'fixed',inset:'0',zIndex:'2147483647',
      background:'#fff',color:'#173d2c',display:'grid',placeContent:'center',padding:'24px',textAlign:'center'});
    const title = document.createElement('h2');
    title.textContent = 'Session verrouillée';
    const message = document.createElement('p');
    message.textContent = 'Reconnectez-vous pour continuer.';
    const button = document.createElement('button');
    button.textContent = 'Se reconnecter';
    button.onclick = () => window.location.reload();
    overlay.append(title, message, button);
    document.body.append(overlay);
    setTriggerValue('locked', Date.now());
  }
  function activity(event) {
    if (!event.isTrusted || locked) return;
    if (Date.now() >= deadline) { lock(); return; }
    // Never read key codes, text, passwords or any input contents.
    deadline = Date.now() + data.timeout_ms;
    state.deadline = deadline;
    state.pending = true;
    if (Date.now()-lastSignal >= 10000) {
      lastSignal = Date.now();
      state.lastSignal = lastSignal;
      state.pending = false;
      setTriggerValue('activity', lastSignal);
    }
  }
  function check() {
    if (Date.now() >= deadline) { lock(); return; }
    if (!locked && state.pending && Date.now()-lastSignal >= 10000) {
      lastSignal = Date.now();
      state.lastSignal = lastSignal;
      state.pending = false;
      setTriggerValue('activity', lastSignal);
    }
  }
  const events = ['pointerdown','keydown','input','touchstart','wheel'];
  events.forEach(name => document.addEventListener(name, activity, {capture:true,passive:true}));
  document.addEventListener('visibilitychange', check);
  const timer = setInterval(check, 1000);
  return () => {
    clearInterval(timer);
    events.forEach(name => document.removeEventListener(name, activity, true));
    document.removeEventListener('visibilitychange', check);
    if (overlay && activeOverlay === overlay) {
      overlay.remove();
      activeOverlay = null;
    }
  };
}
