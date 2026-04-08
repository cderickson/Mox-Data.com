// MTGO-DB Base JavaScript - Professional Sidebar Layout

// Sidebar Management
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const mainContent = document.getElementById('main-content');
  
  if (sidebar && overlay) {
    const isCurrentlyOpen = sidebar.classList.contains('show');
    
    if (isCurrentlyOpen) {
      // Close sidebar
      sidebar.classList.remove('show');
      overlay.classList.remove('show');
      document.body.style.overflow = '';
    } else {
      // Open sidebar
      sidebar.classList.add('show');
      overlay.classList.add('show');
      
      // Only prevent body scroll on mobile
      if (window.innerWidth <= 768) {
        document.body.style.overflow = 'hidden';
      }
    }
  }
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  
  if (sidebar && overlay) {
    sidebar.classList.remove('show');
    overlay.classList.remove('show');
    document.body.style.overflow = '';
  }
}

// User Dropdown Management
function toggleUserDropdown() {
  const accountUserMenu = document.getElementById('accountUserMenu');
  const userInfo = accountUserMenu ? accountUserMenu.querySelector('.user-info') : null;
  const userDropdown = document.getElementById('user-dropdown');
  const userChevron = accountUserMenu ? accountUserMenu.querySelector('.user-chevron') : null;
  
  if (userInfo && userDropdown) {
    const isActive = userInfo.classList.contains('active');
    
    userInfo.classList.toggle('active');
    userDropdown.classList.toggle('show');
    
    if (userChevron) {
      userChevron.style.transform = isActive ? 'rotate(0deg)' : 'rotate(180deg)';
    }
  }
}

// Close user dropdown when clicking outside
document.addEventListener('click', function(event) {
  const userMenu = document.getElementById('accountUserMenu');
  const userDropdown = document.getElementById('user-dropdown');
  const userInfo = userMenu ? userMenu.querySelector('.user-info') : null;
  
  if (userMenu && !userMenu.contains(event.target)) {
    if (userDropdown && userInfo) {
      userDropdown.classList.remove('show');
      userInfo.classList.remove('active');
      
      const userChevron = userMenu ? userMenu.querySelector('.user-chevron') : null;
      if (userChevron) {
        userChevron.style.transform = 'rotate(0deg)';
      }
    }
  }
});

// Set Active Navigation Link
function setActiveNavLink() {
  const currentPath = window.location.pathname;
  const navLinks = document.querySelectorAll('.nav-link');
  
  navLinks.forEach(link => {
    link.classList.remove('active');
    
    // Skip links that are placeholders or use onclick handlers
    const href = link.getAttribute('href');
    if (!href || href === '#' || href.startsWith('#') || link.hasAttribute('onclick')) {
      return; // Skip this link
    }
    
    try {
      // Check if the link href matches the current path
      const linkPath = new URL(link.href).pathname;
      if (linkPath === currentPath) {
        link.classList.add('active');
      }
    } catch (e) {
      // Skip invalid URLs
      return;
    }
  });
}

// Responsive Sidebar Handling
function handleResize() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  
  if (window.innerWidth > 768) {
    // Desktop: Always show sidebar, hide overlay, restore body scroll
    if (sidebar) sidebar.classList.remove('show');
    if (overlay) overlay.classList.remove('show');
    document.body.style.overflow = '';
  }
}

// Ensure body overflow is properly reset
function resetBodyOverflow() {
  // Always ensure body can scroll normally on page load
  document.body.style.overflow = '';
  
  // Only apply overflow hidden if sidebar is actually open on mobile
  const sidebar = document.getElementById('sidebar');
  if (sidebar && sidebar.classList.contains('show') && window.innerWidth <= 768) {
    document.body.style.overflow = 'hidden';
  }
}

// Disable any carousel or slideshow behavior
function disableCarouselBehavior() {
  // Remove any scroll-snap properties that might cause carousel behavior
  document.body.style.scrollSnapType = 'none';
  document.documentElement.style.scrollSnapType = 'none';
  
  // Ensure normal scrolling behavior
  document.body.style.scrollBehavior = 'auto';
  document.documentElement.style.scrollBehavior = 'auto';
  
  // Remove any transforms on body or html that might cause sliding
  document.body.style.transform = 'none';
  document.documentElement.style.transform = 'none';
  
  // Ensure proper overflow settings
  document.body.style.overflowX = 'hidden';
  document.body.style.overflowY = 'auto';
  
  // Target feature cards specifically - but preserve our grid layout
  setTimeout(() => {
    const featuresContainer = document.querySelector('.features-container');
    if (featuresContainer) {
      // Keep our CSS grid layout, just disable carousel behavior
      featuresContainer.style.position = 'static';
      featuresContainer.style.transform = 'none';
      featuresContainer.style.scrollSnapType = 'none';
      featuresContainer.style.overflow = 'visible';
      
      // Fix all cards in the container - but don't override grid layout
      const cards = featuresContainer.querySelectorAll('.section-card');
      cards.forEach(card => {
        card.style.position = 'static';
        card.style.transform = 'none';
        card.style.scrollSnapAlign = 'none';
        // Remove flex properties that interfere with grid
        card.style.flex = '';
        card.style.maxWidth = '';
        card.style.minWidth = '';
        card.style.width = '';
      });
    }
    
    // Disable any potential carousel libraries
    if (window.Swiper) {
      console.log('Disabling Swiper');
    }
    if (window.Glide) {
      console.log('Disabling Glide');
    }
    if (window.Flickity) {
      console.log('Disabling Flickity');
    }
  }, 100);
}

// Flash Message Auto-Hide
function scheduleFlashRemoval(alertElement, delayMs = 2500) {
  if (!alertElement || alertElement.dataset.autoDismissScheduled === 'true') {
    return;
  }

  alertElement.dataset.autoDismissScheduled = 'true';

  setTimeout(() => {
    if (!alertElement.parentNode) {
      return;
    }

    alertElement.style.transition = 'opacity 0.25s ease, transform 0.25s ease, margin 0.25s ease';
    alertElement.style.opacity = '0';
    alertElement.style.transform = 'translateY(-8px)';
    alertElement.style.marginBottom = '0';

    setTimeout(() => {
      if (alertElement.parentNode) {
        alertElement.remove();
      }
    }, 260);
  }, delayMs);
}

function initFlashMessages() {
  const alerts = document.querySelectorAll('.flash-messages [role="alert"]');
  alerts.forEach(alert => scheduleFlashRemoval(alert));
}

// Smooth Scrolling for Anchor Links
function initSmoothScrolling() {
  const anchorLinks = document.querySelectorAll('a[href^="#"]');
  
  anchorLinks.forEach(link => {
    link.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href').substring(1);
      if (!targetId) {
        return;
      }
      const targetElement = document.getElementById(targetId);
      
      if (targetElement) {
        e.preventDefault();
        targetElement.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });
}

// Accordion Functionality
function initAccordions() {
  const accordionItems = document.querySelectorAll('.accordion-item');
  
  if (accordionItems.length === 0) {
    return; // No accordions found
  }
  
  // Clear any existing accordion state and listeners
  accordionItems.forEach(item => {
    item.classList.remove('active');
    const header = item.querySelector('.accordion-header');
    if (header) {
      // Clone the header to remove all event listeners
      const newHeader = header.cloneNode(true);
      header.parentNode.replaceChild(newHeader, header);
    }
  });
  
  // Open first item by default
  accordionItems[0].classList.add('active');
  
  // Add fresh event listeners
  accordionItems.forEach(item => {
    const header = item.querySelector('.accordion-header');
    
    if (header) {
      header.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        
        const isCurrentlyActive = item.classList.contains('active');
        
        if (isCurrentlyActive) {
          // Close the currently active item
          item.classList.remove('active');
        } else {
          // Close all items
          accordionItems.forEach(otherItem => {
            otherItem.classList.remove('active');
          });
          
          // Open the clicked item
          item.classList.add('active');
        }
      });
    }
  });
}

// Form Enhancements
function initFormEnhancements() {
  // Add focus/blur effects to form inputs
  const formInputs = document.querySelectorAll('.form-input');
  
  formInputs.forEach(input => {
    input.addEventListener('focus', function() {
      this.parentElement.classList.add('focused');
    });
    
    input.addEventListener('blur', function() {
      this.parentElement.classList.remove('focused');
    });
  });
  
  // Auto-resize textareas
  const textareas = document.querySelectorAll('textarea.form-input');
  textareas.forEach(textarea => {
    textarea.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = this.scrollHeight + 'px';
    });
  });
}

// Keyboard Navigation
function initKeyboardNavigation() {
  document.addEventListener('keydown', function(event) {
    // ESC key closes sidebar and dropdowns
    if (event.key === 'Escape') {
      closeSidebar();
      
      // Close user dropdown
      const userDropdown = document.getElementById('user-dropdown');
      const userInfo = document.querySelector('.user-info');
      if (userDropdown && userInfo) {
        userDropdown.classList.remove('show');
        userInfo.classList.remove('active');
      }
    }
    
    // Toggle sidebar with Ctrl+B
    if (event.ctrlKey && event.key === 'b') {
      event.preventDefault();
      toggleSidebar();
    }
  });
}

// Initialize Page
function initPage() {
  disableCarouselBehavior(); // Disable any carousel/slideshow behavior
  resetBodyOverflow(); // Ensure proper scrolling on page load
  setActiveNavLink();
  initFlashMessages();
  initSmoothScrolling();
  initAccordions();
  initFormEnhancements();
  initKeyboardNavigation();
  initImageModal(); // Initialize image modal functionality
}

// Initialize Image Modal
function initImageModal() {
  // Initialize feature card click handlers if they exist
  const featureCards = document.querySelectorAll('.feature-card');
  featureCards.forEach(card => {
    card.addEventListener('click', function() {
      const imageSrc = this.dataset.image;
      const title = this.dataset.title;
      const description = this.dataset.description;
      
      showImageModal(imageSrc, title, description);
    });
  });
  
  // Close modal with Escape key
  document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
      closeImageModal();
    }
  });
}

// Game Winner Modal Management
class GameWinnerManager {
  constructor() {
    this.currentGame = null;
    this.modal = document.getElementById('GameWinnerModal');
  }

  async initialize() {
    await this.loadNextGame();
  }

  updateModalContent(gameData) {
    // Update game info section
    const dateElement = document.getElementById('GameWinnerModalDate');
    dateElement.innerHTML = `<center><strong>Match</strong>: ${gameData.match_id}-${gameData.game_num} vs. ${gameData.p2}<br/><strong>Date</strong>: ${gameData.date}</center>`;

    // Update game actions
    const actionsElement = document.getElementById('EndGameActions');
    actionsElement.innerHTML = gameData.game_actions
      .map(action => this.formatGameAction(action))
      .join('<br>');

    // Update button labels
    const p1Button = document.querySelector('[onclick="applyGetWinner(\'P1\')"]');
    const p2Button = document.querySelector('[onclick="applyGetWinner(\'P2\')"]');
    
    if (p1Button) p1Button.innerHTML = `<i class="fas fa-user" style="margin-right: var(--spacing-xs);"></i>${gameData.p1}`;
    if (p2Button) p2Button.innerHTML = `<i class="fas fa-user" style="margin-right: var(--spacing-xs);"></i>${gameData.p2}`;
  }

  formatGameAction(action) {
    // Handle the @[...@] formatting from the original code
    if (action.indexOf('@[') === -1) return action;
    
    let formatted = action;
    const openCount = (action.match(/@\[/g) || []).length;
    const closeCount = (action.match(/@\]/g) || []).length;
    
    if (openCount === closeCount) {
      for (let i = 0; i < openCount; i++) {
        formatted = formatted.replace('@[', '<strong>').replace('@]', '</strong>');
      }
    }
    
    return formatted;
  }

  async applyWinner(winner) {
    if (!this.currentGame) {
      console.error('No current game data');
      return;
    }

    try {
      const payload = {
        match_id: this.currentGame.match_id,
        game_num: this.currentGame.game_num,
        winner: winner, // 'P1', 'P2', or 'skip'
        p1: this.currentGame.p1,
        p2: this.currentGame.p2
      };

      const response = await fetch('/api/game-winner/update', {
        method: 'POST',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Failed to update game winner');
      }

      const result = await response.json();
      
      // Show success message only when a winner is actually set (not skipped)
      if (winner !== 'skip' && typeof showFlashMessage === 'function') {
        const winnerText = winner === 'P1' ? this.currentGame.p1 : this.currentGame.p2;
        showFlashMessage(`Game winner set to: ${winnerText}`, 'success');
      }

      if (winner === 'skip') {
        // For skip operations, use the backend's sequential logic
        if (result.hasNextGame) {
          this.currentGame = result.nextGame;
          this.updateModalContent(result.nextGame);
          this.enableMenuButton();
        } else {
          // Check if there are still any games available to process
          // (skipped games might still be processable from the beginning)
          hideGameWinnerModal();
          await this.checkAndUpdateButtonState();
        }
      } else {
        // For apply operations, use the reliable /api/game-winner/next
        await this.loadNextGame();
      }

    } catch (error) {
      console.error('Error updating game winner:', error);
      this.showErrorMessage('Failed to update game winner');
    }
  }

  async loadNextGame() {
    try {
      const response = await fetch('/api/game-winner/next', {
        method: 'GET',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch next game data');
      }

      const data = await response.json();
      
      if (!data.hasGames) {
        // Check if we're in the modal or just initializing
        if (this.modal && this.modal.style.display === 'flex') {
          // Modal is open, so we're done processing
          hideGameWinnerModal();
          this.showCompletionMessage();
        } else {
          // Initial load with no games
          this.showNoGamesMessage();
        }
        this.disableMenuButton();
        return;
      }

      // Load the next game
      this.currentGame = data;
      this.updateModalContent(data);
      this.enableMenuButton();
      
    } catch (error) {
      console.error('Error loading next game:', error);
      this.showErrorMessage('Failed to load next game data');
    }
  }

  showNoGamesMessage() {
    const dateElement = document.getElementById('GameWinnerModalDate');
    dateElement.innerHTML = `No games found.`;
    
    const actionsElement = document.getElementById('EndGameActions');
    actionsElement.innerHTML = '<div style="text-align: center;">No games with missing winners found.</div>';
    
    // Disable action buttons
    document.querySelectorAll('#GameWinnerModal .button').forEach(btn => {
      if (!btn.onclick || !btn.onclick.toString().includes('hideGameWinnerModal')) {
        btn.disabled = true;
      }
    });
  }

  showErrorMessage(message) {
    const actionsElement = document.getElementById('EndGameActions');
    actionsElement.innerHTML = `<div style="text-align: center; color: #ef4444; padding: var(--spacing-lg);">${message}</div>`;
  }

  showCompletionMessage() {
    // Show a success flash message
    if (typeof showFlashMessage === 'function') {
      showFlashMessage('Processed all games with missing winners.', 'success');
    }
  }

  enableMenuButton() {
    const menuButton = document.getElementById('getMissingMenuButton');
    if (menuButton) {
      menuButton.disabled = false;
      menuButton.classList.remove('disabled');
    }
  }

  disableMenuButton() {
    const menuButton = document.getElementById('getMissingMenuButton');
    if (menuButton) {
      menuButton.disabled = true;
      menuButton.classList.add('disabled');
    }
  }

  async checkAndUpdateButtonState() {
    try {
      // Check if there are still any games that need processing
      const response = await fetch('/api/game-winner/next', {
        method: 'GET',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to check for remaining games');
      }

      const data = await response.json();
      
      if (data.hasGames) {
        // There are still games available, keep button enabled
        this.enableMenuButton();
      } else {
        // Truly no more games to process
        this.showCompletionMessage();
        this.disableMenuButton();
      }
      
    } catch (error) {
      console.error('Error checking button state:', error);
      // On error, keep button enabled to be safe
      this.enableMenuButton();
    }
  }
}

// Global instance
let gameWinnerManager = null;

// Draft ID Modal Management
class DraftIdManager {
  constructor() {
    this.currentMatch = null;
    this.modal = document.getElementById('DraftIdModal');
    this.selectedDraftId = null;
    this.processedMatches = new Set(); // Track actually processed (applied) matches in memory
    this.skippedMatches = new Set(); // Track skipped matches separately
  }

  async initialize() {
    await this.loadNextMatch();
  }

  updateModalContent(matchData) {
    // Update match info section
    const dateElement = document.getElementById('DraftIdModalDate');
    dateElement.innerHTML = `<center><strong>Match</strong>: ${matchData.match_id}<br/><strong>Date</strong>: ${matchData.date}</center>`;

    // Update card lists
    this.updateCardList('DraftIdLands', matchData.lands);
    this.updateCardList('DraftIdSpells', matchData.spells.slice(0, Math.floor(matchData.spells.length / 2)));
    this.updateCardList('DraftIdSpells2', matchData.spells.slice(Math.floor(matchData.spells.length / 2)));

    // Update dropdown with possible draft IDs
    this.updateDraftIdDropdown(matchData.possible_draft_ids);
  }

  updateCardList(elementId, cards) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    element.innerHTML = cards.length > 0 ? cards.join('<br>') : '<em>No cards</em>';
  }

  updateDraftIdDropdown(draftIds) {
    const button = document.getElementById('DraftIdButton');
    const menu = document.getElementById('DraftIdMenu');
    
    if (!button || !menu || !draftIds || draftIds.length === 0) {
      if (button) button.textContent = 'No draft IDs available';
      if (menu) menu.innerHTML = '';
      return;
    }

    // Set default selection
    this.selectedDraftId = draftIds[0];
    button.innerHTML = `<i style="margin-right: var(--spacing-xs);"></i>${draftIds[0]}`;

    // Populate dropdown menu
    menu.innerHTML = draftIds.map(draftId => 
      `<li onclick="draftIdManager.selectDraftId('${draftId}')">${draftId}</li>`
    ).join('');
  }

  selectDraftId(draftId) {
    this.selectedDraftId = draftId;
    const button = document.getElementById('DraftIdButton');
    if (button) {
      button.innerHTML = `<i style="margin-right: var(--spacing-xs);"></i>${draftId}`;
    }
    
    // Close dropdown
    const menu = document.getElementById('DraftIdMenu');
    if (menu) {
      menu.classList.remove('show');
    }
  }

  async applyDraftId(skip = false) {
    if (!this.currentMatch) {
      console.error('No current match data');
      return;
    }

    // Track matches differently based on whether they're skipped or applied
    if (skip) {
      this.skippedMatches.add(this.currentMatch.match_id);
    } else {
      this.processedMatches.add(this.currentMatch.match_id);
    }

    // Call backend API for both skip and apply
    try {
      const payload = {
        match_id: this.currentMatch.match_id,
        draft_id: skip ? null : this.selectedDraftId,
        skip: skip
      };

      const response = await fetch('/api/draft-id/update', {
        method: 'POST',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Failed to update draft association');
      }

      const result = await response.json();

      // Show success message only when a draft ID is actually applied (not skipped)
      if (!skip && typeof showFlashMessage === 'function') {
        showFlashMessage(`Applied Draft ID: ${this.selectedDraftId}`, 'success');
      }

      if (skip) {
        // For skip operations, use the backend's sequential logic
        if (result.hasNextMatch) {
          this.currentMatch = result.nextMatch;
          this.selectedDraftId = result.nextMatch.possible_draft_ids?.[0] || null;
          this.updateModalContent(result.nextMatch);
          this.enableMenuButton();
        } else {
          // Check if there are still any matches available to process
          // (skipped matches might still be processable from the beginning)
          hideDraftIdModal();
          await this.checkAndUpdateButtonState();
        }
      } else {
        // For apply operations, use the reliable /api/draft-id/next
        await this.loadNextMatch();
      }

    } catch (error) {
      console.error('Error updating draft association:', error);
      this.showErrorMessage('Failed to update draft association');
    }
  }

  async loadNextMatch() {
    try {
      console.log('DraftIdManager: Loading next match...');
      const response = await fetch('/api/draft-id/next', {
        method: 'GET',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        }
      });

      console.log('DraftIdManager: Response status:', response.status);
      if (!response.ok) {
        const errorText = await response.text();
        console.error('DraftIdManager: API Error:', errorText);
        throw new Error('Failed to fetch next match data');
      }

      const data = await response.json();
      console.log('DraftIdManager: Received data:', data);
      
      if (!data.hasMatches) {
        // Check if we're in the modal or just initializing
        if (this.modal && this.modal.style.display === 'flex') {
          // Modal is open, so we're done processing
          hideDraftIdModal();
          this.showCompletionMessage();
        } else {
          // Initial load with no matches
          this.showNoMatchesMessage();
        }
        this.disableMenuButton();
        return;
      }

      // Check if this match was already processed (applied) in this session
      // Skipped matches can still be processed, so only check processedMatches
      if (this.processedMatches.has(data.match_id)) {
        // We've already applied a draft ID to this match in this session, so we're really done
        hideDraftIdModal();
        this.showCompletionMessage();
        this.disableMenuButton();
        return;
      }

      // Load the match
      this.currentMatch = data;
      this.selectedDraftId = data.possible_draft_ids?.[0] || null;
      this.updateModalContent(data);
      this.enableMenuButton();
      
    } catch (error) {
      console.error('DraftIdManager: Error loading next match:', error);
      this.showErrorMessage('Failed to load next match data');
      // Enable buttons even if there's an error so user can close modal
      this.enableButtons();
    }
  }

  showNoMatchesMessage() {
    const dateElement = document.getElementById('DraftIdModalDate');
    dateElement.textContent = 'No limited matches found.';
    
    const landsElement = document.getElementById('DraftIdLands');
    const spellsElement = document.getElementById('DraftIdSpells');
    const spells2Element = document.getElementById('DraftIdSpells2');
    
    if (landsElement) landsElement.innerHTML = '';
    if (spellsElement) spellsElement.innerHTML = '<div>No Limited Matches missing an Associated Draft_ID.<br><br>Note: Matches need to have Format set to \'Limited\' before they can be associated with a Draft.</div>';
    if (spells2Element) spells2Element.innerHTML = '';
    
    // Disable action buttons
    document.querySelectorAll('#DraftIdModal .button').forEach(btn => {
      if (!btn.onclick || !btn.onclick.toString().includes('hideDraftIdModal')) {
        btn.disabled = true;
      }
    });
  }

  showErrorMessage(message) {
    const landsElement = document.getElementById('DraftIdLands');
    if (landsElement) {
      landsElement.innerHTML = `<div style="text-align: center; color: #ef4444; padding: var(--spacing-lg);">${message}</div>`;
    }
  }

  showCompletionMessage() {
    // Show a success flash message
    if (typeof showFlashMessage === 'function') {
      showFlashMessage('All limited matches have been processed for draft associations!', 'success');
    }
  }

  enableMenuButton() {
    const menuButton = document.getElementById('applyDraftIdMenuButton');
    if (menuButton) {
      menuButton.disabled = false;
      menuButton.classList.remove('disabled');
    }
  }

  disableMenuButton() {
    const menuButton = document.getElementById('applyDraftIdMenuButton');
    if (menuButton) {
      menuButton.disabled = true;
      menuButton.classList.add('disabled');
    }
  }

  enableButtons() {
    // Enable the modal buttons in case they get stuck
    const skipButton = document.querySelector('#DraftIdModal button[onclick*="applyGetDraftId(true)"]');
    const applyButton = document.querySelector('#DraftIdModal button[onclick*="applyGetDraftId(false)"]');
    
    if (skipButton) {
      skipButton.disabled = false;
      skipButton.style.opacity = '1';
      skipButton.style.pointerEvents = 'auto';
    }
    if (applyButton) {
      applyButton.disabled = false;
      applyButton.style.opacity = '1';
      applyButton.style.pointerEvents = 'auto';
    }
  }

  clearProcessedMatches() {
    this.processedMatches.clear();
    this.skippedMatches.clear();
  }

  async checkAndUpdateButtonState() {
    try {
      // Check if there are still any matches that need processing
      const response = await fetch('/api/draft-id/next', {
        method: 'GET',
        headers: {
          'X-Requested-By': 'MTGO-Tracker',
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to check for remaining matches');
      }

      const data = await response.json();
      
      if (data.hasMatches) {
        // There are still matches available, keep button enabled
        this.enableMenuButton();
      } else {
        // Truly no more matches to process
        this.showCompletionMessage();
        this.disableMenuButton();
      }
      
    } catch (error) {
      console.error('Error checking draft ID button state:', error);
      // On error, keep button enabled to be safe
      this.enableMenuButton();
    }
  }
}

// Global instance
let draftIdManager = null;

// Flash message helper function
function showFlashMessage(message, category = 'info') {
  // Always use or create the flash-messages container
  let flashContainer = document.querySelector('.flash-messages');
  
  if (!flashContainer) {
    // Create the flash-messages container if it doesn't exist
    flashContainer = document.createElement('div');
    flashContainer.className = 'flash-messages';
    flashContainer.id = 'flash-messages';
    document.body.appendChild(flashContainer);
  }

  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${category}`;
  alertDiv.setAttribute('role', 'alert');
  
  let iconClass = 'fas fa-info-circle';
  let iconColor = 'black'; // White icons for better contrast on solid backgrounds
  
  switch(category) {
    case 'success':
      iconClass = 'fas fa-check-circle';
      break;
    case 'error':
      iconClass = 'fas fa-exclamation-circle';
      break;
    case 'warning':
      iconClass = 'fas fa-exclamation-triangle';
      break;
  }
  
  alertDiv.innerHTML = `
    <div class="alert-content"><i class="${iconClass}" style="margin-right: var(--spacing-sm); color: ${iconColor};"></i><span class="alert-message"></span></div>
    <button type="button" class="alert-close" onclick="this.parentElement.remove()">
      <i class="fas fa-times"></i>
    </button>
  `;
  const alertMessage = alertDiv.querySelector('.alert-message');
  if (alertMessage) {
    alertMessage.textContent = String(message ?? '');
  }
  
  // Always append to flash container (newest messages at bottom)
  flashContainer.appendChild(alertDiv);
  
  // Auto-remove popup after a couple seconds
  scheduleFlashRemoval(alertDiv);
}

// Initialize the manager when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  gameWinnerManager = new GameWinnerManager();
  if (!draftIdManager) {
    draftIdManager = new DraftIdManager();
    window.draftIdManager = draftIdManager; // Make it accessible from window
  }
});

// Updated global functions for compatibility with existing onclick handlers
async function initGetWinner() {
  if (!gameWinnerManager) {
    gameWinnerManager = new GameWinnerManager();
  }
  
  await gameWinnerManager.initialize();
  showGameWinnerModal();
}

async function applyGetWinner(winner) {
  if (!gameWinnerManager) {
    console.error('GameWinnerManager not initialized');
    return;
  }
  
  // Map the winner parameter correctly
  let winnerParam = winner;
  if (winner === '0') {
    winnerParam = 'skip';
  }
  
  await gameWinnerManager.applyWinner(winnerParam);
}

async function initGetDraftId() {
  if (!draftIdManager) {
    draftIdManager = new DraftIdManager();
    window.draftIdManager = draftIdManager; // Make it accessible from window
  }
  
  await draftIdManager.initialize();
  showDraftIdModal();
}

async function applyGetDraftId(skip) {
  if (!draftIdManager) {
    console.error('DraftIdManager not initialized');
    return;
  }
  
  await draftIdManager.applyDraftId(skip);
}

// Compatibility function for dropdown selection
function showAssociatedDraftId(item) {
  if (draftIdManager && item && item.textContent) {
    draftIdManager.selectDraftId(item.textContent.trim());
  }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', initPage);
window.addEventListener('resize', function() {
  handleResize();
  resetBodyOverflow();
});

// Legacy Functions (for compatibility with existing modals and functionality)
// Note: Modal functions are now implemented inline in base.html to avoid conflicts

// Utility Functions
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

function throttle(func, limit) {
  let inThrottle;
  return function() {
    const args = arguments;
    const context = this;
    if (!inThrottle) {
      func.apply(context, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

// Image Modal Functions
function showImageModal(imageSrc, title, description) {
  const modal = document.getElementById('imageModal');
  const modalImage = document.getElementById('modalImage');
  const modalTitle = document.getElementById('modalTitle');
  const modalDescription = document.getElementById('modalDescription');
  const content = modal ? modal.querySelector('.image-modal-content') : null;
  
  if (!modal || !modalImage || !modalTitle || !modalDescription) {
    console.error('Modal elements not found');
    return;
  }
  
  modalImage.src = imageSrc;
  modalImage.alt = title;
  modalTitle.textContent = title;
  modalDescription.textContent = description;
  
  // Optional: set a default modal height; callers can override with CSS var
  if (content) {
    content.style.setProperty('--image-modal-height', '80vh');
  }
  
  // Show modal using CSS (with dimmed background)
  modal.style.display = 'flex';
  
  document.body.style.overflow = 'hidden';
}

function closeImageModal() {
  const modal = document.getElementById('imageModal');
  if (modal) {
    modal.style.display = 'none';
    document.body.style.overflow = 'auto';
  }
}

// Export functions for use in other scripts
window.MTGODB = {
  toggleSidebar,
  closeSidebar,
  toggleUserDropdown,
  setActiveNavLink,
  initAccordions,
  showImageModal,
  closeImageModal,
  debounce,
  throttle
};