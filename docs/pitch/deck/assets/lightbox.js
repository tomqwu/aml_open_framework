/* Lightbox helper — included by any slide that has clickable screenshots.
 *
 * Usage: add `class="zoomable"` to any <img> (or any element containing a
 * single <img>). Clicking it opens a fullscreen overlay with the image
 * scaled to fit. ESC or clicking the backdrop closes.
 *
 * Self-contained — appends a single overlay div to body on first click,
 * delegates clicks via a single document listener so it works for
 * dynamically-added images too.
 */
(function () {
  let overlay = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'lightbox-overlay';
    overlay.innerHTML =
      '<img alt="" />' +
      '<div class="lightbox-hint">click anywhere · press ESC to close</div>' +
      '<div class="lightbox-close" aria-label="Close">×</div>';
    overlay.addEventListener('click', (e) => {
      // Click on overlay (backdrop) or close button → close. Click on
      // the image itself shouldn't propagate-cancel; image inside an
      // already-open lightbox = also close.
      close();
    });
    document.body.appendChild(overlay);
    return overlay;
  }

  function open(src, alt) {
    const ov = ensureOverlay();
    const img = ov.querySelector('img');
    img.src = src;
    img.alt = alt || '';
    // Defer to next frame so the transition runs.
    requestAnimationFrame(() => ov.classList.add('open'));
  }

  function close() {
    if (overlay) overlay.classList.remove('open');
  }

  document.addEventListener('click', (e) => {
    const trigger = e.target.closest('.zoomable');
    if (!trigger) return;
    e.preventDefault();
    e.stopPropagation();
    const img = trigger.tagName === 'IMG' ? trigger : trigger.querySelector('img');
    if (img && img.src) open(img.src, img.alt);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });
})();
