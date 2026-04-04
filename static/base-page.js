var directLink = false;

// Modal Dropdown functionality
function toggleDropdown(event, dropdownId) {
  event.preventDefault();
  const dropdown = document.getElementById(dropdownId);
  const toggle = event.currentTarget;
  const isVisible = dropdown.classList.contains('show');

  document.querySelectorAll('.dropdown-menu').forEach(menu => {
    menu.classList.remove('show');
  });
  document.querySelectorAll('.dropdown-toggle').forEach(toggleBtn => {
    toggleBtn.classList.remove('active');
  });

  if (!isVisible) {
    dropdown.classList.add('show');
    toggle.classList.add('active');
  }
}

// User dropdown functionality
function toggleUserDropdown() {
  const dropdown = document.getElementById('user-dropdown');
  const chevron = document.querySelector('.user-chevron');
  const isVisible = dropdown.classList.contains('show');

  document.querySelectorAll('.dropdown-menu').forEach(menu => {
    menu.classList.remove('show');
  });
  document.querySelectorAll('.dropdown-toggle').forEach(toggleBtn => {
    toggleBtn.classList.remove('active');
  });

  if (!isVisible) {
    dropdown.classList.add('show');
    if (chevron) chevron.style.transform = 'rotate(180deg)';
  } else {
    dropdown.classList.remove('show');
    if (chevron) chevron.style.transform = 'rotate(0deg)';
  }
}

// Close dropdowns when clicking outside
document.addEventListener('click', function(event) {
  if (!event.target.closest('.nav-item') && !event.target.closest('.dropdown') && !event.target.closest('.user-menu')) {
    document.querySelectorAll('.dropdown-menu').forEach(menu => {
      menu.classList.remove('show');
    });
    document.querySelectorAll('.dropdown-toggle').forEach(toggleBtn => {
      toggleBtn.classList.remove('active');
    });

    const userDropdown = document.getElementById('user-dropdown');
    const chevron = document.querySelector('.user-chevron');
    if (userDropdown) {
      userDropdown.classList.remove('show');
      if (chevron) chevron.style.transform = 'rotate(0deg)';
    }
  }
});

// Close certain modals when clicking outside (backdrop click)
document.addEventListener('DOMContentLoaded', function() {
  const gwModal = document.getElementById('GameWinnerModal');
  if (gwModal) {
    gwModal.addEventListener('click', function(e) {
      if (e.target === gwModal) {
        hideGameWinnerModal();
      }
    });
  }
  const draftModal = document.getElementById('DraftIdModal');
  if (draftModal) {
    draftModal.addEventListener('click', function(e) {
      if (e.target === draftModal) {
        hideDraftIdModal();
      }
    });
  }
});

function showGameWinnerModal() {
  const modal = document.getElementById('GameWinnerModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function hideGameWinnerModal() {
  const modal = document.getElementById('GameWinnerModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
  if (window.location.pathname.startsWith('/table/')) {
    window.location.reload();
  }
}

function showDraftIdModal() {
  const modal = document.getElementById('DraftIdModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function hideDraftIdModal() {
  const modal = document.getElementById('DraftIdModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';

  if (window.draftIdManager) {
    window.draftIdManager.clearProcessedMatches();
  }
  if (window.location.pathname.startsWith('/table/')) {
    window.location.reload();
  }
}

function showBestGuessModal() {
  const modal = document.getElementById('BestGuessModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  const matchSetButton = document.getElementById('BG_Match_Set_Button');
  const replaceButton = document.getElementById('BG_Replace_Button');
  const matchSetHidden = document.getElementById('BG_Match_Set');
  const replaceHidden = document.getElementById('BG_Replace');
  if (matchSetButton) matchSetButton.textContent = 'Choose an option';
  if (replaceButton) replaceButton.textContent = 'Choose an option';
  if (matchSetHidden) matchSetHidden.value = '';
  if (replaceHidden) replaceHidden.value = '';
  updateBestGuessApplyState();
}

function hideBestGuessModal() {
  const modal = document.getElementById('BestGuessModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
}

function updateBestGuessApplyState() {
  const matchSetValue = (document.getElementById('BG_Match_Set')?.value || '').trim();
  const replaceValue = (document.getElementById('BG_Replace')?.value || '').trim();
  const applyButton = document.getElementById('bestGuessApplyButton');
  if (applyButton) {
    applyButton.disabled = !(matchSetValue && replaceValue);
  }
}

function setBestGuessMatchSet(element, value) {
  const button = document.getElementById('BG_Match_Set_Button');
  const hiddenInput = document.getElementById('BG_Match_Set');

  button.textContent = value;
  hiddenInput.value = value;

  const dropdown = document.getElementById('BG_Match_Set_Menu');
  dropdown.classList.remove('show');
  button.classList.remove('active');
  updateBestGuessApplyState();
}

function setBestGuessReplace(element, value) {
  const button = document.getElementById('BG_Replace_Button');
  const hiddenInput = document.getElementById('BG_Replace');

  button.textContent = (element?.textContent || '').trim() || value;
  hiddenInput.value = value;

  const dropdown = document.getElementById('BG_Replace_Menu');
  dropdown.classList.remove('show');
  button.classList.remove('active');
  updateBestGuessApplyState();
}

function showImportModal() {
  const modal = document.getElementById('ImportModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  document.getElementById('importForm').reset();
  validateImportFiles();
}

function hideImportModal() {
  const modal = document.getElementById('ImportModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
  document.getElementById('importForm').reset();
  const submitBtn = document.getElementById('importSubmitBtn');
  if (submitBtn) submitBtn.disabled = true;
}

function showLoadRevisionsModal() {
  const modal = document.getElementById('LoadRevisionsModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  document.getElementById('loadRevisionsForm').reset();
  validateLoadRevisionsFiles();
}

function hideLoadRevisionsModal() {
  const modal = document.getElementById('LoadRevisionsModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
  document.getElementById('loadRevisionsForm').reset();
}

function showReprocessModal() {
  const modal = document.getElementById('ReprocessModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function hideReprocessModal() {
  const modal = document.getElementById('ReprocessModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
}

function showZipLogsModal() {
  const modal = document.getElementById('ZipLogsModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function hideZipLogsModal() {
  const modal = document.getElementById('ZipLogsModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
}

function showProcessingModal(message = 'Please wait while we process your request.') {
  const modal = document.getElementById('processingModal');
  document.getElementById('processingMessage').textContent = message;
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function hideProcessingModal() {
  const modal = document.getElementById('processingModal');
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';

  if (exportTimeout) {
    clearTimeout(exportTimeout);
    exportTimeout = null;
  }
  if (downloadCheckInterval) {
    clearInterval(downloadCheckInterval);
    downloadCheckInterval = null;
  }

  downloadStarted = false;
  document.getElementById('processingButtons').style.display = 'none';
  document.getElementById('processingMessage').textContent = 'Please wait while we process your request.';
}

let exportTimeout;
let downloadCheckInterval;
let downloadStarted = false;

function handleExportClick(linkElement) {
  window.location.assign(linkElement.href);
}

function initiateDownload(url) {
  const tempLink = document.createElement('a');
  tempLink.href = url;
  tempLink.style.display = 'none';
  document.body.appendChild(tempLink);

  const originalUrl = window.location.href;
  tempLink.click();

  setTimeout(function() {
    if (document.body.contains(tempLink)) {
      document.body.removeChild(tempLink);
    }
  }, 1000);

  setTimeout(function() {
    if (window.location.href !== originalUrl) {
      downloadDetected();
    }
  }, 500);
}

function setupAdvancedDownloadDetection() {
  let checkCount = 0;
  const maxChecks = 120;

  const visibilityHandler = function() {
    if (document.hidden) {
      setTimeout(function() {
        if (!document.hidden && !downloadStarted) {
          downloadDetected();
        }
      }, 1500);
    }
  };

  document.addEventListener('visibilitychange', visibilityHandler);

  const focusHandler = function() {
    setTimeout(function() {
      if (document.hasFocus() && !downloadStarted) {
        downloadDetected();
      }
    }, 1000);
  };

  window.addEventListener('focus', focusHandler);

  downloadCheckInterval = setInterval(function() {
    checkCount++;
    if (performance && performance.getEntriesByType) {
      const entries = performance.getEntriesByType('navigation');
      if (entries.length > 0 && !downloadStarted) {
        // no-op
      }
    }

    if (checkCount >= maxChecks || downloadStarted) {
      clearInterval(downloadCheckInterval);
      document.removeEventListener('visibilitychange', visibilityHandler);
      window.removeEventListener('focus', focusHandler);
    }
  }, 1000);

  setTimeout(function() {
    if (!downloadStarted) {
      downloadDetected();
    }
  }, 12000);
}

function downloadDetected() {
  if (downloadStarted) return;
  downloadStarted = true;

  if (exportTimeout) clearTimeout(exportTimeout);
  if (downloadCheckInterval) clearInterval(downloadCheckInterval);

  document.getElementById('processingMessage').textContent = 'Download started! The file should appear in your downloads.';
  setTimeout(function() {
    hideProcessingModal();
  }, 2000);
}

function updateBestGuessForm() {
  document.getElementById('BG_Match_Set').value = document.getElementById('BG_Match_Set_Select').value;
  document.getElementById('BG_Replace').value = document.getElementById('BG_Replace_Select').value;
}

document.addEventListener('click', function(event) {
  if (event.target.classList.contains('modal') && !event.target.classList.contains('image-modal') && event.target.id !== 'processingModal') {
    if (event.target.id === 'ReviseModal') {
      if (typeof hideReviseModal === 'function') {
        hideReviseModal();
      } else {
        event.target.style.display = 'none';
        document.body.style.overflow = 'auto';
      }
    } else if (event.target.id === 'ReviseMultiModal') {
      if (typeof hideReviseMultiModal === 'function') {
        hideReviseMultiModal();
      } else {
        event.target.style.display = 'none';
        document.body.style.overflow = 'auto';
      }
    } else if (event.target.id === 'RemoveModal') {
      if (typeof hideRemoveModal === 'function') {
        hideRemoveModal();
      } else {
        event.target.style.display = 'none';
        document.body.style.overflow = 'auto';
      }
    } else {
      event.target.style.display = 'none';
      document.body.style.overflow = 'auto';
    }
  }
});

document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    const modals = document.querySelectorAll('.modal:not(.image-modal):not(#processingModal)');
    modals.forEach(modal => {
      if (modal.style.display === 'flex') {
        if (modal.id === 'ReviseModal') {
          if (typeof hideReviseModal === 'function') {
            hideReviseModal();
          } else {
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
          }
        } else if (modal.id === 'ReviseMultiModal') {
          if (typeof hideReviseMultiModal === 'function') {
            hideReviseMultiModal();
          } else {
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
          }
        } else if (modal.id === 'RemoveModal') {
          if (typeof hideRemoveModal === 'function') {
            hideRemoveModal();
          } else {
            modal.style.display = 'none';
            document.body.style.overflow = 'auto';
          }
        } else {
          modal.style.display = 'none';
          document.body.style.overflow = 'auto';
        }
      }
    });
  }
});

function validateImportFiles() {
  const fileInput = document.getElementById('importFileInput');
  const submitBtn = document.getElementById('importSubmitBtn');

  if (fileInput.files.length === 0) {
    submitBtn.disabled = true;
    return;
  }

  const selectedFile = fileInput.files[0];
  const fileName = selectedFile.name.toLowerCase();
  submitBtn.disabled = fileName.endsWith('.zip') ? false : true;
}

document.addEventListener('DOMContentLoaded', function() {
  const importForm = document.getElementById('importForm');
  if (importForm) {
    importForm.addEventListener('submit', function() {
      const modal = document.getElementById('ImportModal');
      if (modal) {
        modal.style.visibility = 'hidden';
        modal.style.opacity = '0';
        modal.style.pointerEvents = 'none';
      }
      showProcessingModal('Uploading and processing your GameLogs...');
      const buttons = document.getElementById('processingButtons');
      if (buttons) buttons.style.display = 'none';
    });
  }
});

function validateLoadRevisionsFiles() {
  const fileInput = document.getElementById('loadRevisionsFileInput');
  const submitBtn = document.getElementById('loadRevisionsSubmitBtn');
  if (!fileInput || !submitBtn) return;

  if (fileInput.files.length === 0) {
    submitBtn.disabled = true;
    return;
  }

  const selectedFile = fileInput.files[0];
  const fileName = selectedFile.name.split('/').pop().split('\\').pop();
  submitBtn.disabled = (fileName === 'ALL_DATA') ? false : true;
}

async function checkTableStatusAndUpdateButtons() {
  try {
    const response = await fetch('/api/table-status', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    });

    if (response.ok) {
      const data = await response.json();
      updateSidebarButtonStates(data.status);
    } else {
      console.error('Failed to fetch table status');
    }
  } catch (error) {
    console.error('Error checking table status:', error);
  }
}

function updateSidebarButtonStates(status) {
  const buttonConfigs = [
    { id: 'matchesMenuButton', enabled: status.matches_enabled },
    { id: 'bestGuessMenuButton', enabled: status.best_guess_enabled },
    { id: 'draftsMenuButton', enabled: status.drafts_enabled },
    { id: 'ignoredMatchesMenuButton', enabled: status.ignored_matches_enabled },
    { id: 'getMissingMenuButton', enabled: status.missing_winners_enabled },
    { id: 'applyDraftIdMenuButton', enabled: status.draft_ids_enabled },
    { id: 'reprocessMenuButton', enabled: status.reprocess_enabled },
    { id: 'dashboardsMenuButton', enabled: status.dashboards_enabled }
  ];

  buttonConfigs.forEach(config => {
    const button = document.getElementById(config.id);
    if (button) {
      if (config.enabled) {
        enableSidebarButton(button);
      } else {
        disableSidebarButton(button);
      }
    }
  });
}

function enableSidebarButton(button) {
  button.classList.remove('disabled', 'table-dependent');
  button.style.pointerEvents = 'auto';
  button.style.opacity = '1';
  button.style.color = '';

  const originalOnclick = button.getAttribute('data-original-onclick');
  if (originalOnclick) {
    button.setAttribute('onclick', originalOnclick);
  }

  button.removeEventListener('click', preventNavigation);
  const icon = button.querySelector('.nav-icon');
  if (icon) {
    icon.style.color = '';
  }
}

function disableSidebarButton(button) {
  button.classList.add('disabled');
  button.style.pointerEvents = 'none';
  button.style.opacity = '0.5';
  button.removeAttribute('onclick');
  button.addEventListener('click', preventNavigation);
}

function preventNavigation(e) {
  e.preventDefault();
  e.stopPropagation();
  return false;
}

window.refreshSidebarButtonStates = checkTableStatusAndUpdateButtons;

async function refreshReferenceCache(event) {
  if (event) event.preventDefault();
  const refreshButton = document.getElementById('debugRefreshCacheButton');
  if (refreshButton) {
    refreshButton.style.pointerEvents = 'none';
    refreshButton.style.opacity = '0.6';
  }

  try {
    const response = await fetch('/admin/refresh-reference-cache', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok || !result.success) {
      throw new Error(result?.error || 'Failed to refresh cache');
    }

    const stats = result.stats || {};
    alert(
      `Reference cache refreshed.\n` +
      `Input Options: ${stats.input_options_categories ?? 0}\n` +
      `Multifaced Card Groups: ${stats.multifaced_groups ?? 0}\n` +
      `All Deck Months: ${stats.all_decks_months ?? 0}`
    );
  } catch (error) {
    console.error('Error refreshing reference cache:', error);
    alert(error?.message || 'Failed to refresh cache');
  } finally {
    if (refreshButton) {
      refreshButton.style.pointerEvents = '';
      refreshButton.style.opacity = '';
    }
  }
}

document.addEventListener('DOMContentLoaded', function() {
  const tableDependent = document.querySelectorAll('.table-dependent');
  if (tableDependent.length > 0) {
    checkTableStatusAndUpdateButtons();
  }
});

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.toggle('show');
}

function toggleDesktopSidebar() {
  const sidebar = document.getElementById('sidebar');
  const collapseBtn = document.getElementById('sidebarCollapseBtn');
  const mainContent = document.querySelector('.main-content');
  const sidebarLinks = document.querySelectorAll('.sidebar a');

  sidebar.classList.toggle('collapsed');

  const icon = collapseBtn.querySelector('i');
  if (sidebar.classList.contains('collapsed')) {
    icon.className = 'fas fa-chevron-right';
    collapseBtn.title = 'Expand Sidebar';
    if (mainContent) {
      mainContent.style.marginLeft = '50px';
    }
    sidebarLinks.forEach(link => {
      link.setAttribute('data-prev-tabindex', link.getAttribute('tabindex') || '');
      link.setAttribute('tabindex', '-1');
    });
  } else {
    icon.className = 'fas fa-chevron-left';
    collapseBtn.title = 'Collapse Sidebar';
    if (mainContent) {
      mainContent.style.marginLeft = '280px';
    }
    sidebarLinks.forEach(link => {
      const prev = link.getAttribute('data-prev-tabindex');
      if (prev === '') {
        link.removeAttribute('tabindex');
      } else if (prev !== null) {
        link.setAttribute('tabindex', prev);
      }
      link.removeAttribute('data-prev-tabindex');
    });
  }

  const isCollapsed = sidebar.classList.contains('collapsed');
  localStorage.setItem('sidebarCollapsed', isCollapsed);
  try {
    document.cookie = `sidebarCollapsed=${isCollapsed}; path=/; SameSite=Lax`;
  } catch (e) {
    // Ignore cookie errors
  }
}