(function () {
    'use strict';

    const status = document.getElementById('cobros-live-status');
    if (!status) return;

    const button = status.querySelector('button');
    const manual = status.dataset.manual === 'true';
    const fields = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select';
    const original = new WeakMap();
    let pending = false;
    let checking = false;
    let leaving = false;
    let lastInteraction = Date.now();

    function value(field) {
        if (['checkbox', 'radio'].includes(field.type)) return field.checked;
        if (field.type === 'file') return field.value;
        if (field.multiple) return JSON.stringify(Array.from(field.selectedOptions, option => option.value));
        return field.value;
    }

    for (const field of document.querySelectorAll(fields)) {
        original.set(field, value(field));
    }

    function editing() {
        return document.activeElement?.matches(fields + ', [contenteditable="true"]')
            || document.querySelector('dialog[open], .modal.show')
            || Array.from(document.querySelectorAll(fields)).some(field => original.has(field) && original.get(field) !== value(field));
    }

    function refresh(force = false) {
        if (!pending || leaving || document.hidden) return;
        const busy = editing();
        status.hidden = false;
        button.disabled = Boolean(busy);
        if (busy || (manual && !force) || (!force && Date.now() - lastInteraction < 1500)) return;
        leaving = true;
        location.reload();
    }

    async function check() {
        if (document.hidden || checking || leaving) return;
        checking = true;
        try {
            const response = await fetch(status.dataset.url, {
                cache: 'no-store',
                redirect: 'manual',
                signal: typeof AbortSignal.timeout === 'function' ? AbortSignal.timeout(6000) : undefined,
            });
            if (response.type === 'opaqueredirect' || response.status === 401 || response.status === 403) {
                const message = status.querySelector('[role="status"]');
                message.textContent = 'La sesión terminó. Volvé a ingresar para actualizar.';
                pending = true;
                status.hidden = false;
                button.disabled = Boolean(editing());
                return;
            }
            if (!response.ok) return;
            const {revision} = await response.json();
            pending = revision !== status.dataset.revision;
            status.hidden = !pending;
            refresh();
        } catch (_) {
            // Retry on the next check after a temporary network failure.
        } finally {
            checking = false;
        }
    }

    button.addEventListener('click', () => refresh(true));
    for (const event of ['pointerdown', 'keydown', 'input', 'change', 'scroll']) {
        document.addEventListener(event, () => { lastInteraction = Date.now(); }, {capture: true, passive: true});
    }
    document.addEventListener('submit', event => {
        lastInteraction = Date.now();
        window.setTimeout(() => {
            const target = event.submitter?.getAttribute('formtarget') || event.target.target;
            if (!event.defaultPrevented && (!target || target === '_self')) leaving = true;
        }, 0);
    }, true);
    window.addEventListener('pagehide', () => { leaving = true; });
    window.addEventListener('pageshow', () => { leaving = false; check(); });
    document.addEventListener('visibilitychange', check);
    window.setInterval(check, 4000);
}());
