/* Keep bottom sheets inside the visible viewport when the iPhone keyboard opens. */
(() => {
  const viewport = window.visualViewport;
  if (!viewport) return;
  let scheduled = false;
  function sync() {
    scheduled = false;
    // Preserve the user's intentional pinch zoom.
    if (Math.abs(viewport.scale - 1) > 0.05) return;
    const root = document.documentElement;
    root.style.setProperty('--sheet-viewport-height', `${viewport.height}px`);
    const inset = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
    root.style.setProperty('--sheet-keyboard-inset', `${inset}px`);
    const editing = document.activeElement?.matches('input,textarea,[contenteditable="true"]');
    root.classList.toggle('keyboard-open', Boolean(editing && inset > 150));
  }
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(sync);
  }
  viewport.addEventListener('resize', schedule);
  viewport.addEventListener('scroll', schedule);
  window.addEventListener('resize', schedule);
  window.addEventListener('pageshow', schedule);
  document.addEventListener('focusin', schedule);
  document.addEventListener('focusout', schedule);
  sync();
})();
