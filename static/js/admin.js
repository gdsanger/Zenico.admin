// Zenico Admin JavaScript
// Minimal JS helpers for HTMX interactions

// Configure HTMX to include CSRF token in all requests
document.addEventListener('DOMContentLoaded', function() {
    // Get CSRF token from meta tag
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

    if (csrfToken) {
        // Configure HTMX to include CSRF token in all requests
        document.body.addEventListener('htmx:configRequest', function(evt) {
            evt.detail.headers['X-CSRFToken'] = csrfToken;
        });
    }

    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Confirm dialogs for dangerous actions
    document.addEventListener('click', function(e) {
        const target = e.target.closest('[data-confirm]');
        if (target) {
            const message = target.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
                e.stopPropagation();
            }
        }
    });

    // Mobile sidebar toggle
    const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
    const sidebar = document.querySelector('.sidebar');

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('show');
        });
    }
});

// HTMX event handlers
document.body.addEventListener('htmx:afterSwap', function(evt) {
    // Re-initialize Bootstrap tooltips after HTMX swap
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});

document.body.addEventListener('htmx:responseError', function(evt) {
    // Handle HTMX errors
    console.error('HTMX Error:', evt.detail);
    alert('An error occurred. Please try again.');
});
