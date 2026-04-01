/**
 * Collapsible Tab Functionality
 * Handles expanding/collapsing of tab content with smooth animations
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeCollapsibleTabs();
});

function initializeCollapsibleTabs() {
    const collapsibleTabs = document.querySelectorAll('.collapsible-tab');
    
    collapsibleTabs.forEach(tab => {
        const header = tab.querySelector('.section-card-header');
        const content = tab.querySelector('.section-card-content');
        
        if (!header || !content) return;

        // Ensure only the dedicated right-side chevron acts as the rotating indicator.
        const headerIcon = Array.from(header.children).find((child) => child.tagName === 'I');
        if (headerIcon) {
            headerIcon.classList.add('collapsible-indicator');
        }
        
        // Make header focusable for accessibility
        header.setAttribute('tabindex', '0');
        header.setAttribute('role', 'button');
        header.setAttribute('aria-expanded', 'false');
        
        // Set up ARIA labels
        const title = header.querySelector('.section-card-title');
        if (title) {
            const titleText = title.textContent.trim();
            header.setAttribute('aria-label', `Toggle ${titleText} section`);
        }
        
        // Add click event listener
        header.addEventListener('click', function(e) {
            e.preventDefault();
            toggleTab(tab);
        });
        
        // Add keyboard event listener for accessibility
        header.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleTab(tab);
            }
        });
        
        // Initialize: expand if has 'expanded' class, otherwise collapse
        if (tab.classList.contains('expanded')) {
            expandTab(tab, false);
        } else {
            collapseTab(tab, false);
        }
    });
}

function toggleTab(tab) {
    if (tab.classList.contains('expanded')) {
        collapseTab(tab, true);
    } else {
        expandTab(tab, true);
    }
}

function clearPendingExpandCleanup(content) {
    if (content._expandTransitionHandler) {
        content.removeEventListener('transitionend', content._expandTransitionHandler);
        content._expandTransitionHandler = null;
    }
}

function expandTab(tab, animate = true) {
    const header = tab.querySelector('.section-card-header');
    const content = tab.querySelector('.section-card-content');
    
    if (!animate) {
        // Instant expand (for initialization)
        clearPendingExpandCleanup(content);
        tab.classList.add('expanded');
        header.setAttribute('aria-expanded', 'true');
        content.style.maxHeight = 'none';
        content.style.opacity = '1';
        return;
    }
    
    // Animated expand
    clearPendingExpandCleanup(content);
    tab.classList.add('expanded');
    header.setAttribute('aria-expanded', 'true');
    
    // Calculate the full height of content
    const fullHeight = content.scrollHeight;
    
    // Set explicit height for smooth animation
    content.style.maxHeight = fullHeight + 'px';
    content.style.opacity = '1';
    
    // Clean up after max-height transition completes
    const onTransitionEnd = (event) => {
        if (event.propertyName !== 'max-height') {
            return;
        }

        content.removeEventListener('transitionend', onTransitionEnd);
        content._expandTransitionHandler = null;

        if (tab.classList.contains('expanded')) {
            content.style.maxHeight = 'none';
        }
    };

    content._expandTransitionHandler = onTransitionEnd;
    content.addEventListener('transitionend', onTransitionEnd);
}

function collapseTab(tab, animate = true) {
    const header = tab.querySelector('.section-card-header');
    const content = tab.querySelector('.section-card-content');
    
    if (!animate) {
        // Instant collapse (for initialization)
        clearPendingExpandCleanup(content);
        tab.classList.remove('expanded');
        header.setAttribute('aria-expanded', 'false');
        content.style.maxHeight = '0';
        content.style.opacity = '0';
        return;
    }
    
    // Get current height before starting animation
    clearPendingExpandCleanup(content);
    const currentHeight = content.scrollHeight;
    content.style.maxHeight = currentHeight + 'px';
    
    // Force reflow to ensure the height is applied
    content.offsetHeight;
    
    // Start collapse animation
    tab.classList.remove('expanded');
    header.setAttribute('aria-expanded', 'false');
    content.style.maxHeight = '0';
    content.style.opacity = '0';
}

// Utility function to expand all tabs (useful for testing or "expand all" feature)
function expandAllTabs() {
    const collapsibleTabs = document.querySelectorAll('.collapsible-tab');
    collapsibleTabs.forEach(tab => expandTab(tab, true));
}

// Utility function to collapse all tabs
function collapseAllTabs() {
    const collapsibleTabs = document.querySelectorAll('.collapsible-tab');
    collapsibleTabs.forEach(tab => collapseTab(tab, true));
}

// Export functions for potential external use
window.CollapsibleTabs = {
    expandTab,
    collapseTab,
    toggleTab,
    expandAllTabs,
    collapseAllTabs,
    initializeCollapsibleTabs
};