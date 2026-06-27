// Global visual cue for "checkbox reveals its children".
// The actual reveal is handled natively by each field's `depends_on` (so ticking
// a checkbox shows the fields that come with it). This script just adds a subtle
// left-border highlight to those dependent fields so the relationship is obvious,
// and a small caret on checkboxes that own children. It attaches on every form
// via a router hook (no per-doctype wiring required).
(function () {
    function decorate() {
        // dependent fields (have a data-depends-on referencing a checkbox) get a cue
        document.querySelectorAll('.frappe-control[data-fieldtype]').forEach((el) => {
            const dep = el.getAttribute('data-depends-on') || '';
            if (dep && /doc\.[a-z0-9_]+/i.test(dep) && !el.dataset.ipDecorated) {
                el.dataset.ipDecorated = '1';
                el.style.borderLeft = '2px solid #cfe3ff';
                el.style.paddingLeft = '8px';
                el.style.marginLeft = '2px';
            }
        });
    }
    // run after each route change / form render
    if (window.frappe && frappe.router) {
        frappe.router.on('change', () => setTimeout(decorate, 600));
    }
    document.addEventListener('DOMContentLoaded', () => setTimeout(decorate, 800));
})();
