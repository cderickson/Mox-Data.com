let vintageFilterOptions = {};
let vintageScatterChart = null;
let vintageEventExplorerScatterChart = null;
let vintageEventPlayerBarChart = null;
let vintageEventMwpBarChart = null;
let vintagePlayerDecksBarChart = null;
let vintageMatchupOppArchChart = null;
let vintageMatchupOppSubarchChart = null;
let selectedEventId = '';
let previousDashboardType = '';
let vintageMetagameMode = 'overall';
let latestVintageMetagameData = null;
let latestVintageMatchupHeatmapData = null;
let vintageMetagameScatterGroupBy = 'subarchetype';
let vintageChartDefaultsApplied = false;
let isRefreshingVintageFilterOptions = false;
let vintageMetagameSortState = {
  archetype: { key: null, direction: 'desc' },
  subarchetype: { key: null, direction: 'desc' }
};

document.addEventListener('DOMContentLoaded', function() {
  loadVintageFilterOptions().then(() => {
    // Auto-load default dashboard type (Metagame Breakdown) on initial page visit.
    generateVintageDashboard();
  });
  setupVintageFilterEventListeners();

  const dashboardTypeSelect = document.getElementById('dashboardType');
  const metagameModeSelect = document.getElementById('metagameModeSelect');
  if (dashboardTypeSelect) {
    previousDashboardType = dashboardTypeSelect.value || '';
    dashboardTypeSelect.addEventListener('change', function() {
      const nextDashboardType = this.value || '';
      resetVintageFiltersExceptDateRange();
      if (nextDashboardType !== 'metagame-breakdown') {
        vintageMetagameScatterGroupBy = 'subarchetype';
      }
      const resetArchetypeToAll = (previousDashboardType === 'matchup-graph' && nextDashboardType !== 'matchup-graph');
      syncArchetypeFilterState(resetArchetypeToAll);
      previousDashboardType = nextDashboardType;
      syncPlayerFilterState();
      syncMetagameModeControlVisibility();
      refreshVintageFilterOptions();
    });
  }
  if (metagameModeSelect) {
    metagameModeSelect.addEventListener('change', function() {
      vintageMetagameMode = this.value === 'exclude-mirrors' ? 'exclude-mirrors' : 'overall';
      if ((document.getElementById('dashboardType')?.value || '') === 'metagame-breakdown') {
        generateVintageDashboard();
      }
    });
  }

  syncPlayerFilterState();
  syncMetagameModeControlVisibility();
});

window.addEventListener('beforeunload', function() {
  // Ensure hidden event selection does not persist across page leave/reload.
  selectedEventId = '';
  resetPlayerFilterSelection();
  vintageMetagameScatterGroupBy = 'subarchetype';
});

function resetPlayerFilterSelection() {
  const playerFilter = document.getElementById('playerFilter');
  if (playerFilter) {
    playerFilter.value = '';
  }
}

function resetVintageFiltersExceptDateRange() {
  const eventIdFilter = document.getElementById('eventIdFilter');
  const eventTypeFilter = document.getElementById('eventTypeFilter');
  const archetypeFilter = document.getElementById('archetypeFilter');
  const subarchetypeFilter = document.getElementById('subarchetypeFilter');
  const playerFilter = document.getElementById('playerFilter');

  if (eventIdFilter) eventIdFilter.value = '';
  if (eventTypeFilter) eventTypeFilter.value = '';
  if (archetypeFilter) archetypeFilter.value = '';
  if (subarchetypeFilter) subarchetypeFilter.value = '';
  if (playerFilter) playerFilter.value = '';

  // Hidden Event Explorer-only filter
  selectedEventId = '';
}

function updateVintageMetricsVisibility(dashboardType, showMetricsCard = true) {
  const metricsCard = document.getElementById('vintageMetricsCard');
  const metricsBody = document.getElementById('vintageMetricsBody');
  const winnerCard = document.getElementById('winnerCard');
  const runnerUpCard = document.getElementById('runnerUpCard');
  const trophiesCard = document.getElementById('trophiesCard');
  const top8RateCard = document.getElementById('top8RateCard');
  const matchupGraphMwpCard = document.getElementById('matchupGraphMwpCard');
  const uniquePlayersCard = document.getElementById('uniquePlayersCard');
  if (!metricsCard || !metricsBody || !winnerCard || !runnerUpCard || !trophiesCard || !top8RateCard || !matchupGraphMwpCard || !uniquePlayersCard) return;

  if (!showMetricsCard) {
    metricsCard.style.display = 'none';
    metricsBody.classList.remove('unique-only');
    metricsBody.classList.remove('event-explorer-mode');
    metricsBody.classList.remove('player-leaderboard-mode');
    return;
  }

  metricsCard.style.display = '';
  const normalizedType = dashboardType || '';
  const showWinnerRunner = normalizedType === 'event-explorer';
  const showPlayerLeaderboardCards = normalizedType === 'player-leaderboard';
  const showMatchupGraphMwpCard = normalizedType === 'matchup-graph';

  winnerCard.style.display = showWinnerRunner ? '' : 'none';
  runnerUpCard.style.display = showWinnerRunner ? '' : 'none';
  trophiesCard.style.display = showPlayerLeaderboardCards ? '' : 'none';
  top8RateCard.style.display = showPlayerLeaderboardCards ? '' : 'none';
  matchupGraphMwpCard.style.display = showMatchupGraphMwpCard ? '' : 'none';
  uniquePlayersCard.style.display = '';
  const uniqueOnly = !showWinnerRunner && !showPlayerLeaderboardCards && !showMatchupGraphMwpCard;
  metricsBody.classList.toggle('unique-only', uniqueOnly);
  metricsBody.classList.toggle('event-explorer-mode', showWinnerRunner);
  metricsBody.classList.toggle('player-leaderboard-mode', showPlayerLeaderboardCards);
}

function destroyVintageMatchupGraphCharts() {
  if (vintageMatchupOppArchChart) {
    vintageMatchupOppArchChart.destroy();
    vintageMatchupOppArchChart = null;
  }
  if (vintageMatchupOppSubarchChart) {
    vintageMatchupOppSubarchChart.destroy();
    vintageMatchupOppSubarchChart = null;
  }
}

async function loadVintageFilterOptions() {
  try {
    const response = await fetch('/api/vintage/filter-options', {
      method: 'GET',
      headers: {
        'X-Requested-By': 'MTGO-Tracker'
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to load vintage filter options (${response.status})`);
    }

    vintageFilterOptions = await response.json();
    populateVintageFilterDropdowns(getCurrentVintageFilterValues());
  } catch (error) {
    console.error('Error loading vintage filter options:', error);
  }
}

function setupVintageFilterEventListeners() {
  const cascadingFilterIds = ['eventIdFilter', 'eventTypeFilter', 'archetypeFilter', 'subarchetypeFilter', 'playerFilter'];
  cascadingFilterIds.forEach(elementId => {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.addEventListener('change', function() {
      if (isRefreshingVintageFilterOptions) return;
      if (elementId === 'eventIdFilter') {
        selectedEventId = this.value || '';
      }
      refreshVintageFilterOptions();
    });
  });
}

async function refreshVintageFilterOptions() {
  const currentValues = getCurrentVintageFilterValues();
  try {
    isRefreshingVintageFilterOptions = true;
    const response = await fetch('/api/vintage/filtered-options', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-By': 'MTGO-Tracker'
      },
      body: JSON.stringify({
        filters: {
          eventId: currentValues.eventId || '',
          eventType: currentValues.eventType || '',
          archetype: currentValues.archetype || '',
          subarchetype: currentValues.subarchetype || '',
          player: currentValues.player || ''
        }
      })
    });
    if (!response.ok) {
      throw new Error(`Failed to refresh vintage filter options (${response.status})`);
    }

    vintageFilterOptions = await response.json();
    populateVintageFilterDropdowns(currentValues);
  } catch (error) {
    console.error('Error refreshing vintage filter options:', error);
  } finally {
    isRefreshingVintageFilterOptions = false;
  }
}

function populateVintageFilterDropdowns(selectedValues = {}) {
  populateVintageDropdown('eventIdFilter', vintageFilterOptions.EventId || [], 'All Event IDs', selectedValues.eventId || '');
  populateVintageDropdown('eventTypeFilter', vintageFilterOptions.EventType || [], 'All Event Types', selectedValues.eventType || '');
  populateVintageDropdown('subarchetypeFilter', vintageFilterOptions.Subarchetype || [], 'All Subarchetypes', selectedValues.subarchetype || '');
  populateVintageDropdown('playerFilter', vintageFilterOptions.Player || [], 'All Players', selectedValues.player || '');

  const startDateInput = document.getElementById('startDate');
  const endDateInput = document.getElementById('endDate');
  const minDate = vintageFilterOptions.Date1 || '';
  const maxDate = vintageFilterOptions.Date2 || '';

  if (startDateInput) {
    startDateInput.min = minDate;
    startDateInput.max = maxDate;
    const selectedStartDate = selectedValues.startDate || startDateInput.value || '';
    startDateInput.value = clampDateToRange(selectedStartDate, minDate, maxDate) || minDate || '';
  }
  if (endDateInput) {
    endDateInput.min = minDate;
    endDateInput.max = maxDate;
    const selectedEndDate = selectedValues.endDate || endDateInput.value || '';
    endDateInput.value = clampDateToRange(selectedEndDate, minDate, maxDate) || maxDate || '';
  }

  syncArchetypeFilterState();
  syncPlayerFilterState();
}

function clampDateToRange(value, minDate, maxDate) {
  const dateValue = String(value || '').trim();
  if (!dateValue) return '';
  if (minDate && dateValue < minDate) return minDate;
  if (maxDate && dateValue > maxDate) return maxDate;
  return dateValue;
}

function populateVintageDropdown(elementId, optionsList, defaultText, selectedValue = '') {
  const selectElement = document.getElementById(elementId);
  if (!selectElement) return;
  const normalizedOptions = Array.isArray(optionsList)
    ? optionsList.map(optionValue => String(optionValue || '').trim()).filter(Boolean)
    : [];

  selectElement.innerHTML = '';

  const defaultOption = document.createElement('option');
  defaultOption.value = '';
  defaultOption.textContent = defaultText;
  selectElement.appendChild(defaultOption);

  normalizedOptions.forEach(optionValue => {
    const option = document.createElement('option');
    option.value = optionValue;
    option.textContent = optionValue;
    if (selectedValue && optionValue === selectedValue) {
      option.selected = true;
    }
    selectElement.appendChild(option);
  });

  const normalizedSelectedValue = String(selectedValue || '').trim();
  if (normalizedSelectedValue && [...selectElement.options].some(option => option.value === normalizedSelectedValue)) {
    selectElement.value = normalizedSelectedValue;
    return;
  }

  // Auto-select the only available non-default option.
  if (normalizedOptions.length === 1) {
    selectElement.value = normalizedOptions[0];
    return;
  }

  selectElement.value = '';
}

function clearVintageFilters() {
  const filtersForm = document.getElementById('vintageFilters');
  if (filtersForm) {
    filtersForm.reset();
  }

  const startDateInput = document.getElementById('startDate');
  const endDateInput = document.getElementById('endDate');

  if (startDateInput && vintageFilterOptions.Date1) {
    startDateInput.value = vintageFilterOptions.Date1;
  }
  if (endDateInput && vintageFilterOptions.Date2) {
    endDateInput.value = vintageFilterOptions.Date2;
  }

  // Hidden Event Explorer-only filter
  selectedEventId = '';
  const playerFilter = document.getElementById('playerFilter');
  if (playerFilter) {
    playerFilter.value = '';
  }
  syncArchetypeFilterState();
  refreshVintageFilterOptions();
  generateVintageDashboard();
}

function syncPlayerFilterState() {
  const dashboardType = document.getElementById('dashboardType')?.value || '';
  const playerFilter = document.getElementById('playerFilter');
  const playerFilterGroup = document.getElementById('playerFilterGroup');
  if (!playerFilter || !playerFilterGroup) return;

  const enabled = dashboardType === 'player-leaderboard';
  playerFilter.disabled = !enabled;
  if (!enabled) {
    playerFilter.value = '';
    playerFilterGroup.style.opacity = '0.5';
    playerFilterGroup.style.pointerEvents = 'none';
  } else {
    playerFilterGroup.style.opacity = '1';
    playerFilterGroup.style.pointerEvents = 'auto';
  }
}

function syncMetagameModeControlVisibility() {
  const dashboardType = document.getElementById('dashboardType')?.value || '';
  const modeGroup = document.getElementById('metagameModeControlGroup');
  const modeSelect = document.getElementById('metagameModeSelect');
  if (!modeGroup || !modeSelect) return;

  const show = dashboardType === 'metagame-breakdown';
  modeGroup.style.visibility = show ? 'visible' : 'hidden';
  modeGroup.style.pointerEvents = show ? 'auto' : 'none';
  if (!show) {
    modeSelect.value = 'overall';
    vintageMetagameMode = 'overall';
  } else {
    modeSelect.value = vintageMetagameMode;
  }
}

function syncArchetypeFilterState(forceResetToAll = false) {
  const archetypeFilter = document.getElementById('archetypeFilter');
  if (!archetypeFilter) return;

  const archetypeOptions = Array.isArray(vintageFilterOptions.Archetype) ? vintageFilterOptions.Archetype : [];
  const currentValue = archetypeFilter.value || '';

  archetypeFilter.innerHTML = '';

  const defaultOption = document.createElement('option');
  defaultOption.value = '';
  defaultOption.textContent = 'All Archetypes';
  archetypeFilter.appendChild(defaultOption);

  archetypeOptions.forEach(optionValue => {
    const option = document.createElement('option');
    option.value = optionValue;
    option.textContent = optionValue;
    archetypeFilter.appendChild(option);
  });

  const hasCurrentSelection = archetypeOptions.includes(currentValue);
  archetypeFilter.value = forceResetToAll ? '' : (hasCurrentSelection ? currentValue : '');
}

function applyVintageFilters() {
  generateVintageDashboard();
}

function getCurrentVintageFilterValues() {
  const selectedEventIdFilter = document.getElementById('eventIdFilter')?.value || '';
  return {
    startDate: document.getElementById('startDate')?.value || '',
    endDate: document.getElementById('endDate')?.value || '',
    eventId: selectedEventIdFilter || '',
    eventType: document.getElementById('eventTypeFilter')?.value || '',
    archetype: document.getElementById('archetypeFilter')?.value || '',
    subarchetype: document.getElementById('subarchetypeFilter')?.value || '',
    player: (document.getElementById('playerFilter')?.disabled ? '' : (document.getElementById('playerFilter')?.value || ''))
  };
}

function formatPercent(value) {
  const numeric = Number(value || 0);
  return `${(numeric * 100).toFixed(1)}%`;
}

function formatInteger(value) {
  return Number(value || 0).toLocaleString();
}

function addVintageTableTooltips() {
  const tableCells = document.querySelectorAll('#dashboardResults .modern-table td');
  tableCells.forEach(cell => {
    const textContent = cell.textContent.trim();
    if (textContent && textContent.length > 0) {
      cell.removeAttribute('title');
      cell.title = textContent;
      cell.style.cursor = 'help';
    }
  });

  const tableHeaders = document.querySelectorAll('#dashboardResults .modern-table th');
  tableHeaders.forEach(header => {
    const textContent = header.textContent.trim();
    if (textContent && textContent.length > 0) {
      header.removeAttribute('title');
      header.title = textContent;
      header.style.cursor = 'help';
    }
  });
}

function getVintageChartTextColor() {
  return '#000';
}

function getVintageAxisTitle(text) {
  return {
    display: !!text,
    text: text || '',
    color: getVintageChartTextColor(),
    font: { weight: 'normal', size: 13 }
  };
}

function getVintageTickOptions(customOptions = {}) {
  const merged = { ...customOptions };
  merged.color = getVintageChartTextColor();
  merged.font = { weight: 'normal', ...(customOptions.font || {}) };
  return merged;
}

function getVintageLegendOptions(display = true) {
  return {
    display,
    position: 'right',
    labels: {
      padding: 12,
      color: getVintageChartTextColor(),
      font: { weight: 'normal' }
    }
  };
}

function getVintageTitleOptions(text = '') {
  return {
    display: !!text,
    text,
    font: { weight: 'bold', size: 18 },
    color: getVintageChartTextColor(),
    padding: { bottom: 6 }
  };
}

function getVintageSubtitleOptions(text = '') {
  if (!text) return undefined;
  return {
    display: true,
    text,
    font: { weight: 'normal', size: 14 },
    color: getVintageChartTextColor(),
    padding: { top: 2, bottom: 0 }
  };
}

function getVintageTooltipOptions(extraOptions = {}) {
  return {
    titleColor: getVintageChartTextColor(),
    bodyColor: getVintageChartTextColor(),
    footerColor: getVintageChartTextColor(),
    titleFont: { weight: 'normal' },
    bodyFont: { weight: 'normal' },
    footerFont: { weight: 'normal' },
    backgroundColor: 'rgba(255, 255, 255, 0.96)',
    borderColor: '#d1d5db',
    borderWidth: 1,
    ...extraOptions
  };
}

function formatMwpWithCi(mwpValue, ciValue) {
  const mwpPct = (Number(mwpValue || 0) * 100).toFixed(1);
  const ciPct = (Number(ciValue || 0) * 100).toFixed(1);
  return `${mwpPct}% &plusmn; ${ciPct}%`;
}

function getMetagameModeTitleSuffix(mode) {
  return mode === 'exclude-mirrors' ? ' - Mirrors Excluded' : ' - Overall';
}

function getMetagameScatterTitle(mode, groupBy) {
  const titleSuffix = getMetagameModeTitleSuffix(mode);
  const groupedLabel = groupBy === 'archetype' ? 'Archetype' : 'Subarchetype';
  return `Metagame Share vs Match Win%${titleSuffix}`;
}

function getMetagameMwpHeatStyle(mwpValue) {
  const mwp = Number(mwpValue || 0);
  // Condense color band around typical metagame MWP values.
  // 44% maps to red, 50% to yellow, 56% to green.
  const bandMin = 0.44;
  const bandMax = 0.56;
  const normalized = (mwp - bandMin) / (bandMax - bandMin);
  const clamped = Math.max(0, Math.min(1, normalized));
  const hue = Math.round(clamped * 120); // 0=red, 120=green
  return `background-color: hsl(${hue}, 72%, 82%);`;
}

function getMetagameSortIndicator(tableType, sortKey) {
  const state = vintageMetagameSortState[tableType] || {};
  if (state.key !== sortKey) return '';
  return state.direction === 'asc' ? ' ▲' : ' ▼';
}

function sortMetagameRows(rows, tableType, mode) {
  const state = vintageMetagameSortState[tableType] || {};
  if (!state.key) return rows;

  const normalizedMode = mode === 'exclude-mirrors' ? 'exclude-mirrors' : 'overall';
  const mwpKey = normalizedMode === 'exclude-mirrors' ? 'mwp_no_mirrors' : 'mwp_overall';
  const totalMatchesKey = normalizedMode === 'exclude-mirrors' ? 'total_matches_no_mirrors' : 'total_matches';
  const directionMultiplier = state.direction === 'asc' ? 1 : -1;
  const copy = [...(rows || [])];

  copy.sort((a, b) => {
    let aValue;
    let bValue;

    if (state.key === 'name') {
      aValue = String(a?.name || '').toLowerCase();
      bValue = String(b?.name || '').toLowerCase();
      if (aValue < bValue) return -1 * directionMultiplier;
      if (aValue > bValue) return 1 * directionMultiplier;
      return 0;
    }

    if (state.key === 'players') {
      aValue = Number(a?.players || 0);
      bValue = Number(b?.players || 0);
    } else if (state.key === 'meta_pct') {
      aValue = Number(a?.meta_pct || 0);
      bValue = Number(b?.meta_pct || 0);
    } else if (state.key === 'mwp') {
      aValue = Number(a?.[mwpKey] || 0);
      bValue = Number(b?.[mwpKey] || 0);
    } else if (state.key === 'total_matches') {
      aValue = Number(a?.[totalMatchesKey] || 0);
      bValue = Number(b?.[totalMatchesKey] || 0);
    } else {
      return 0;
    }

    if (aValue === bValue) {
      const aName = String(a?.name || '').toLowerCase();
      const bName = String(b?.name || '').toLowerCase();
      if (aName < bName) return -1;
      if (aName > bName) return 1;
      return 0;
    }
    return (aValue - bValue) * directionMultiplier;
  });

  return copy;
}

function toggleMetagameSort(tableType, sortKey) {
  if (tableType !== 'archetype' && tableType !== 'subarchetype') return;
  const current = vintageMetagameSortState[tableType] || { key: null, direction: 'desc' };
  if (current.key === sortKey) {
    vintageMetagameSortState[tableType] = {
      key: sortKey,
      direction: current.direction === 'asc' ? 'desc' : 'asc'
    };
  } else {
    const defaultDirection = sortKey === 'name' ? 'asc' : 'desc';
    vintageMetagameSortState[tableType] = {
      key: sortKey,
      direction: defaultDirection
    };
  }

  if (latestVintageMetagameData) {
    renderVintageMetagameDashboard(latestVintageMetagameData, { tablesOnly: true });
  } else {
    generateVintageDashboard();
  }
}

async function applyMetagameTableFilterSelection(filterType, encodedValue) {
  const targetId = filterType === 'subarchetype' ? 'subarchetypeFilter' : 'archetypeFilter';
  const targetSelect = document.getElementById(targetId);
  if (!targetSelect) return;

  const selectedValue = decodeURIComponent(encodedValue || '').trim();
  if (!selectedValue) return;

  const hasExistingOption = Array.from(targetSelect.options).some(option => option.value === selectedValue);
  if (!hasExistingOption) {
    const option = document.createElement('option');
    option.value = selectedValue;
    option.textContent = selectedValue;
    targetSelect.appendChild(option);
  }

  targetSelect.value = selectedValue;
  await refreshVintageFilterOptions();
  generateVintageDashboard();
}

async function applyPlayerLeaderboardFilterSelection(encodedValue) {
  const playerFilter = document.getElementById('playerFilter');
  if (!playerFilter) return;

  const selectedValue = decodeURIComponent(encodedValue || '').trim();
  if (!selectedValue) return;

  const hasExistingOption = Array.from(playerFilter.options).some(option => option.value === selectedValue);
  if (!hasExistingOption) {
    const option = document.createElement('option');
    option.value = selectedValue;
    option.textContent = selectedValue;
    playerFilter.appendChild(option);
  }

  playerFilter.value = selectedValue;
  await refreshVintageFilterOptions();
  generateVintageDashboard();
}

function applySubarchetypeFilterSelection(encodedValue) {
  const subarchetypeFilter = document.getElementById('subarchetypeFilter');
  if (!subarchetypeFilter) return;

  const selectedValue = decodeURIComponent(encodedValue || '').trim();
  if (!selectedValue) return;

  const hasExistingOption = Array.from(subarchetypeFilter.options).some(option => option.value === selectedValue);
  if (!hasExistingOption) {
    const option = document.createElement('option');
    option.value = selectedValue;
    option.textContent = selectedValue;
    subarchetypeFilter.appendChild(option);
  }

  subarchetypeFilter.value = selectedValue;
  generateVintageDashboard();
}

function renderMetagameTable(tableTitle, rows, mode, filterType) {
  const normalizedMode = mode === 'exclude-mirrors' ? 'exclude-mirrors' : 'overall';
  const mwpKey = normalizedMode === 'exclude-mirrors' ? 'mwp_no_mirrors' : 'mwp_overall';
  const ciKey = normalizedMode === 'exclude-mirrors' ? 'ci_95_no_mirrors' : 'ci_95';
  const totalMatchesKey = normalizedMode === 'exclude-mirrors' ? 'total_matches_no_mirrors' : 'total_matches';
  const titleSuffix = getMetagameModeTitleSuffix(normalizedMode);
  const sortedRows = sortMetagameRows(rows || [], filterType, normalizedMode);
  const headers = [
    { label: tableTitle, sortKey: 'name' },
    { label: 'Players', sortKey: 'players' },
    { label: 'Meta%', sortKey: 'meta_pct' },
    { label: 'MWP ± 95% CI', sortKey: 'mwp' },
    { label: 'Total Matches', sortKey: 'total_matches' }
  ];

  const bodyRows = sortedRows.map(row => `
    <tr>
      <td>
        <a href="#" class="metagame-filter-select vintage-table-filter-link" data-filter-type="${filterType}" data-filter-value="${encodeURIComponent(row.name || '')}">
          ${row.name || ''}
        </a>
      </td>
      <td>${formatInteger(row.players)}</td>
      <td>${formatPercent(row.meta_pct)}</td>
      <td style="${getMetagameMwpHeatStyle(row[mwpKey])}">${formatMwpWithCi(row[mwpKey], row[ciKey])}</td>
      <td>${formatInteger(row[totalMatchesKey])}</td>
    </tr>
  `).join('');

  return `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <div class="vintage-card-header-row">
          <h2 class="section-card-title">
            <i class="fas fa-table"></i>
            ${tableTitle}${titleSuffix}
          </h2>
        </div>
      </div>
      <div class="section-card-body section-thin-body table-body-no-padding">
        <div class="table-wrapper">
          <table class="modern-table" style="table-layout: fixed; width: 100%;">
            <colgroup>
              <col style="width: 26%;">
              <col style="width: 15%;">
              <col style="width: 14%;">
              <col style="width: 21%;">
              <col style="width: 24%;">
            </colgroup>
            <thead>
              <tr>${headers.map((h, i) => `<th class="metagame-sort-header" data-table-type="${filterType}" data-sort-key="${h.sortKey}" style="${i === 0 ? 'text-align: center; cursor: pointer;' : 'cursor: pointer;'}">${h.label}${getMetagameSortIndicator(filterType, h.sortKey)}</th>`).join('')}</tr>
            </thead>
            <tbody>
              ${bodyRows || '<tr><td colspan="5">No data available for the selected filters.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function bindMetagameTableInteractions(containerElement) {
  if (!containerElement) return;
  containerElement.querySelectorAll('.metagame-filter-select').forEach(link => {
    link.addEventListener('click', function(event) {
      event.preventDefault();
      applyMetagameTableFilterSelection(this.dataset.filterType || '', this.dataset.filterValue || '');
    });
  });
  containerElement.querySelectorAll('.metagame-sort-header').forEach(header => {
    header.addEventListener('click', function() {
      toggleMetagameSort(this.dataset.tableType || '', this.dataset.sortKey || '');
    });
  });
}

function renderVintageMetagameDashboard(data, options = {}) {
  updateVintageMetricsVisibility('metagame-breakdown', true);
  latestVintageMetagameData = data || null;
  const dashboardResults = document.getElementById('dashboardResults');
  const uniquePlayersValue = document.getElementById('uniquePlayersValue');
  const vintageMetricsBody = document.getElementById('vintageMetricsBody');
  const winnerValue = document.getElementById('winnerValue');
  const winnerSubtitle = document.getElementById('winnerSubtitle');
  const runnerUpValue = document.getElementById('runnerUpValue');
  const runnerUpSubtitle = document.getElementById('runnerUpSubtitle');
  if (!dashboardResults) return;
  if (vintageEventExplorerScatterChart) {
    vintageEventExplorerScatterChart.destroy();
    vintageEventExplorerScatterChart = null;
  }
  if (vintageEventPlayerBarChart) {
    vintageEventPlayerBarChart.destroy();
    vintageEventPlayerBarChart = null;
  }
  if (vintageEventMwpBarChart) {
    vintageEventMwpBarChart.destroy();
    vintageEventMwpBarChart = null;
  }
  if (vintagePlayerDecksBarChart) {
    vintagePlayerDecksBarChart.destroy();
    vintagePlayerDecksBarChart = null;
  }
  destroyVintageMatchupGraphCharts();
  if (vintageMetricsBody) {
    vintageMetricsBody.classList.remove('event-explorer-mode');
  }
  if (uniquePlayersValue) {
    uniquePlayersValue.textContent = formatInteger(data?.unique_players || 0);
  }
  if (winnerValue) winnerValue.textContent = '--';
  if (winnerSubtitle) winnerSubtitle.textContent = 'Selected event';
  if (runnerUpValue) runnerUpValue.textContent = '--';
  if (runnerUpSubtitle) runnerUpSubtitle.textContent = 'Selected event';

  const metagameMode = vintageMetagameMode === 'exclude-mirrors' ? 'exclude-mirrors' : 'overall';
  const scatterGroupBy = vintageMetagameScatterGroupBy === 'archetype' ? 'archetype' : 'subarchetype';
  const scatterCard = `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <div class="vintage-card-header-row">
          <h2 class="section-card-title" id="vintageMetaScatterTitle">
            <i class="fas fa-braille"></i>
            ${getMetagameScatterTitle(metagameMode, scatterGroupBy)}
          </h2>
          <select class="filter-select vintage-table-mode-select" id="metagameScatterGroupSelect">
            <option value="archetype"${scatterGroupBy === 'archetype' ? ' selected' : ''}>Archetype</option>
            <option value="subarchetype"${scatterGroupBy === 'subarchetype' ? ' selected' : ''}>Subarchetype</option>
          </select>
        </div>
      </div>
      <div class="section-card-body section-thin-body">
        <div class="chart-canvas-container" style="height: 380px;">
          <canvas id="vintage-meta-scatter"></canvas>
        </div>
      </div>
    </div>
  `;

  const archetypeTable = renderMetagameTable('Archetype', data?.archetype_rows || [], metagameMode, 'archetype');
  const subarchetypeTable = renderMetagameTable('Subarchetype', data?.subarchetype_rows || [], metagameMode, 'subarchetype');
  const tablesHtml = `
    <div class="dashboard-table-grid" id="metagameTablesContainer" style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
      ${archetypeTable}
      ${subarchetypeTable}
    </div>
  `;

  if (options.tablesOnly) {
    const tablesContainer = document.getElementById('metagameTablesContainer');
    if (tablesContainer) {
      tablesContainer.outerHTML = tablesHtml;
      bindMetagameTableInteractions(document.getElementById('metagameTablesContainer'));
      return;
    }
  }

  dashboardResults.innerHTML = `
    ${tablesHtml}
    <div style="margin-top: 16px;">${scatterCard}</div>
  `;
  bindMetagameTableInteractions(dashboardResults);
  const scatterGroupSelect = document.getElementById('metagameScatterGroupSelect');
  if (scatterGroupSelect) {
    scatterGroupSelect.addEventListener('change', function() {
      vintageMetagameScatterGroupBy = this.value === 'archetype' ? 'archetype' : 'subarchetype';
      const currentMode = vintageMetagameMode === 'exclude-mirrors' ? 'exclude-mirrors' : 'overall';
      const scatterTitle = document.getElementById('vintageMetaScatterTitle');
      if (scatterTitle) {
        scatterTitle.innerHTML = `<i class="fas fa-braille"></i> ${getMetagameScatterTitle(currentMode, vintageMetagameScatterGroupBy)}`;
      }
      const sourceRows = vintageMetagameScatterGroupBy === 'archetype'
        ? (latestVintageMetagameData?.archetype_rows || [])
        : (latestVintageMetagameData?.subarchetype_rows || []);
      renderVintageMetagameScatter(sourceRows, currentMode, vintageMetagameScatterGroupBy);
    });
  }
  const initialScatterRows = scatterGroupBy === 'archetype'
    ? (data?.archetype_rows || [])
    : (data?.subarchetype_rows || []);
  renderVintageMetagameScatter(initialScatterRows, metagameMode, scatterGroupBy);
}

function renderEventExplorerDashboard(data) {
  updateVintageMetricsVisibility('event-explorer', true);
  const dashboardResults = document.getElementById('dashboardResults');
  const uniquePlayersValue = document.getElementById('uniquePlayersValue');
  const vintageMetricsBody = document.getElementById('vintageMetricsBody');
  const winnerValue = document.getElementById('winnerValue');
  const winnerSubtitle = document.getElementById('winnerSubtitle');
  const runnerUpValue = document.getElementById('runnerUpValue');
  const runnerUpSubtitle = document.getElementById('runnerUpSubtitle');
  if (!dashboardResults) return;
  if (vintagePlayerDecksBarChart) {
    vintagePlayerDecksBarChart.destroy();
    vintagePlayerDecksBarChart = null;
  }
  destroyVintageMatchupGraphCharts();
  if (vintageMetricsBody) {
    vintageMetricsBody.classList.add('event-explorer-mode');
  }
  if (uniquePlayersValue) {
    uniquePlayersValue.textContent = formatInteger(data?.unique_players || 0);
  }
  if (winnerValue) winnerValue.textContent = data?.winner?.player || '--';
  if (winnerSubtitle) winnerSubtitle.textContent = data?.winner?.deck || 'Selected event';
  if (runnerUpValue) runnerUpValue.textContent = data?.runner_up?.player || '--';
  if (runnerUpSubtitle) runnerUpSubtitle.textContent = data?.runner_up?.deck || 'Selected event';

  const eventRows = data?.event_rows || [];
  const standingsRows = data?.standings_rows || [];
  const eventScatterRows = data?.event_scatter_rows || [];
  const eventBarRows = data?.event_bar_rows || [];
  const eventMatchupHeatmap = data?.event_matchup_heatmap || { subarchetypes: [], rows: [] };
  selectedEventId = data?.selected_event_id || selectedEventId || '';
  const eventIdFilter = document.getElementById('eventIdFilter');
  if (eventIdFilter) {
    const hasOption = Array.from(eventIdFilter.options).some(option => option.value === selectedEventId);
    if (selectedEventId && !hasOption) {
      const option = document.createElement('option');
      option.value = selectedEventId;
      option.textContent = selectedEventId;
      eventIdFilter.appendChild(option);
    }
    eventIdFilter.value = selectedEventId || '';
  }

  const leftTable = `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <h2 class="section-card-title">
          <i class="fas fa-calendar-alt"></i>
          Events
        </h2>
      </div>
      <div class="section-card-body section-thin-body table-body-no-padding">
        <div class="table-wrapper" style="height: 280px;">
          <table class="modern-table">
            <thead>
              <tr>
                <th style="text-align: center !important;">Event ID</th>
                <th>Event Type</th>
                <th>Date</th>
                <th>Players</th>
              </tr>
            </thead>
            <tbody>
              ${eventRows.map(row => `
                <tr>
                  <td>
                    <a
                      href="#"
                      class="event-id-select${(selectedEventId && row.event_id === selectedEventId) ? ' active' : ''}"
                      data-event-id="${row.event_id || ''}"
                      style="color: var(--sky-blue); text-decoration: none; font-weight: 600; cursor: pointer;"
                      onmouseover="this.style.textDecoration='underline'"
                      onmouseout="this.style.textDecoration='none'"
                    >
                      ${row.event_id || ''}
                    </a>
                  </td>
                  <td>${row.event_type || ''}</td>
                  <td>${row.date || ''}</td>
                  <td>${formatInteger(row.players)}</td>
                </tr>
              `).join('') || '<tr><td colspan="4">No event data for selected filters.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  const rightTable = `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <h2 class="section-card-title">
          <i class="fas fa-list-ol"></i>
          Event Standings
        </h2>
      </div>
      <div class="section-card-body section-thin-body table-body-no-padding">
        <div class="table-wrapper" style="height: 280px;">
          <table class="modern-table" style="table-layout: fixed; width: 100%;">
            <colgroup>
              <col style="width: 12%;">
              <col style="width: 35%;">
              <col style="width: 15%;">
              <col style="width: 38%;">
            </colgroup>
            <thead>
              <tr>
                <th style="text-align: center !important;">Rank</th>
                <th>Player</th>
                <th>Record</th>
                <th>Deck</th>
              </tr>
            </thead>
            <tbody>
              ${(selectedEventId ? standingsRows : []).map(row => `
                <tr>
                  <td style="text-align: center !important;">${row.rank ?? ''}</td>
                  <td>${row.player || ''}</td>
                  <td>${formatInteger(row.wins)}-${formatInteger(row.losses)}-${formatInteger(row.byes)}</td>
                  <td>${row.deck || ''}</td>
                </tr>
              `).join('') || (selectedEventId
                ? '<tr><td colspan="4">No standings found for selected event.</td></tr>'
                : '<tr><td colspan="4">Select an Event ID from the left table to view standings.</td></tr>')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  const chartsSection = selectedEventId ? `
    <div class="dashboard-chart-grid" style="display: grid; grid-template-columns: 2fr 1fr; gap: 16px; align-items: start;">
      <div class="section-card section-thin-card" style="margin-bottom: 0;">
        <div class="section-card-header">
          <h2 class="section-card-title">
            <i class="fas fa-braille"></i>
            Subarchetype Player Count vs MWP w/o Mirrors
          </h2>
        </div>
        <div class="section-card-body section-thin-body">
          <div class="chart-canvas-container" style="height: 470px;">
            <canvas id="event-explorer-subarch-scatter"></canvas>
          </div>
        </div>
      </div>

      <div class="event-explorer-right-stack" style="display: grid; grid-template-rows: auto auto; gap: 16px; align-content: start;">
        <div class="section-card section-thin-card" style="margin-bottom: 0;">
          <div class="section-card-header">
            <h2 class="section-card-title">
              <i class="fas fa-chart-bar"></i>
              Player Count by Archetype
            </h2>
          </div>
          <div class="section-card-body section-thin-body">
            <div class="chart-canvas-container" style="height: 182px;">
              <canvas id="event-explorer-arch-players-bar"></canvas>
            </div>
          </div>
        </div>

        <div class="section-card section-thin-card" style="margin-bottom: 0;">
          <div class="section-card-header">
            <h2 class="section-card-title">
              <i class="fas fa-chart-bar"></i>
              MWP w/o Mirrors by Archetype
            </h2>
          </div>
          <div class="section-card-body section-thin-body">
            <div class="chart-canvas-container" style="height: 182px;">
              <canvas id="event-explorer-arch-mwp-bar"></canvas>
            </div>
          </div>
        </div>
      </div>
    </div>
  ` : '';
  dashboardResults.innerHTML = `
    <div class="dashboard-table-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">${leftTable}${rightTable}</div>
    ${chartsSection ? `<div style="margin-top: 16px;">${chartsSection}</div>` : ''}
  `;

  dashboardResults.querySelectorAll('.event-id-select').forEach(button => {
    button.addEventListener('click', async function(event) {
      event.preventDefault();
      selectedEventId = this.dataset.eventId || '';
      const eventIdFilterInput = document.getElementById('eventIdFilter');
      if (eventIdFilterInput) {
        const hasOption = Array.from(eventIdFilterInput.options).some(option => option.value === selectedEventId);
        if (selectedEventId && !hasOption) {
          const option = document.createElement('option');
          option.value = selectedEventId;
          option.textContent = selectedEventId;
          eventIdFilterInput.appendChild(option);
        }
        eventIdFilterInput.value = selectedEventId || '';
      }
      await refreshVintageFilterOptions();
      generateVintageDashboard();
    });
  });

  renderEventExplorerCharts(eventScatterRows, eventBarRows, selectedEventId);
}

function renderEventExplorerMatchupHeatmap(heatmapData, options = {}) {
  const showZoomButton = options?.showZoomButton === true;
  const isZoomedView = options?.isZoomedView === true;
  const renderOnlyTable = options?.renderOnlyTable === true;
  const subarchetypes = Array.isArray(heatmapData?.subarchetypes) ? heatmapData.subarchetypes : [];
  const rowData = Array.isArray(heatmapData?.rows) ? heatmapData.rows : [];
  const stickyLabelColumnWidth = isZoomedView ? 300 : 220;
  const matchupValueColumnWidth = isZoomedView ? '170px' : '120px';
  const headerActionsHtml = showZoomButton ? `
    <div class="vintage-card-header-actions">
      <button type="button" class="button primary vintage-header-action-btn" id="matchupHeatmapZoomButton">
        <i class="fas fa-search-plus"></i>
        Zoom
      </button>
    </div>
  ` : '';

  if (!subarchetypes.length || !rowData.length) {
    if (renderOnlyTable) {
      return `<div style="padding: 8px 4px; color: var(--text-secondary);">No matchup heatmap data for the current filters.</div>`;
    }
    return `
      <div class="section-card section-thin-card">
        <div class="section-card-header">
          <h2 class="section-card-title">
            <i class="fas fa-th"></i>
            Matchup Heatmap
          </h2>
        </div>
        <div class="section-card-body section-thin-body">
          <div style="padding: 8px 4px; color: var(--text-secondary);">
            No matchup heatmap data for the current filters.
          </div>
        </div>
      </div>
    `;
  }

  const bodyRows = rowData.map(row => {
    const leftLabel = row?.subarchetype || '';
    const cells = Array.isArray(row?.cells) ? row.cells : [];
    const cellHtml = cells.map(cell => {
      const totalMatches = Number(cell?.total_matches || 0);
      const matchWinPct = Number(cell?.match_win_pct);
      const hasData = totalMatches > 0 && Number.isFinite(matchWinPct);
      const pctText = hasData ? `${(matchWinPct * 100).toFixed(1)}%` : '--';
      const bgStyle = hasData
        ? `background-color: hsl(${Math.round(matchWinPct * 120)}, 68%, 84%);`
        : 'background-color: #f3f4f6;';
      return `
        <td style="${bgStyle} text-align: center; white-space: nowrap;" title="Matches: ${totalMatches}">
          ${pctText}
        </td>
      `;
    }).join('');

    return `
      <tr>
        <th style="position: sticky; left: 0; background: #fff; z-index: 2; width: ${stickyLabelColumnWidth}px; min-width: ${stickyLabelColumnWidth}px; max-width: ${stickyLabelColumnWidth}px;">${leftLabel}</th>
        ${cellHtml}
      </tr>
    `;
  }).join('');

  const heatmapColgroup = `
    <colgroup>
      <col style="width: ${stickyLabelColumnWidth}px;">
      ${subarchetypes.map(() => `<col style="width: ${matchupValueColumnWidth};">`).join('')}
    </colgroup>
  `;

  const heatmapTableHtml = `
    <div class="table-wrapper" style="height: auto; max-height: none; overflow-x: auto; overflow-y: ${renderOnlyTable ? 'hidden' : 'visible'};">
      <table class="modern-table" style="table-layout: fixed; width: max-content; min-width: 100%;">
        ${heatmapColgroup}
        <thead>
          <tr>
            <th style="position: sticky; left: 0; top: 0; z-index: 4; background: #fff; width: ${stickyLabelColumnWidth}px; min-width: ${stickyLabelColumnWidth}px; max-width: ${stickyLabelColumnWidth}px;">Subarchetype</th>
            ${subarchetypes.map(value => `<th style="position: sticky; top: 0; z-index: 3; background: #fff; width: ${matchupValueColumnWidth}; white-space: normal; word-break: break-word; overflow-wrap: anywhere; line-height: 1.2;">${value}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${bodyRows}
        </tbody>
      </table>
    </div>
  `;

  if (renderOnlyTable) {
    return heatmapTableHtml;
  }

  return `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <div class="vintage-card-header-row">
          <h2 class="section-card-title">
            <i class="fas fa-th"></i>
            Matchup Heatmap
          </h2>
          ${headerActionsHtml}
        </div>
      </div>
      <div class="section-card-body section-thin-body table-body-no-padding">
        ${heatmapTableHtml}
      </div>
    </div>
  `;
}

function openVintageHeatmapZoomModal() {
  const modal = document.getElementById('vintageHeatmapZoomModal');
  const modalBody = document.getElementById('vintageHeatmapZoomModalBody');
  if (!modal || !modalBody) return;

  modalBody.innerHTML = renderEventExplorerMatchupHeatmap(
    latestVintageMatchupHeatmapData || { subarchetypes: [], rows: [] },
    { isZoomedView: true, renderOnlyTable: true }
  );
  addVintageTableTooltips();
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeVintageHeatmapZoomModal() {
  const modal = document.getElementById('vintageHeatmapZoomModal');
  const modalBody = document.getElementById('vintageHeatmapZoomModalBody');
  if (!modal || !modalBody) return;
  modal.style.display = 'none';
  modalBody.innerHTML = '';
  document.body.style.overflow = '';
}

function renderMatchupHeatmapDashboard(data) {
  updateVintageMetricsVisibility('matchup-heatmap', true);
  const dashboardResults = document.getElementById('dashboardResults');
  const uniquePlayersValue = document.getElementById('uniquePlayersValue');
  const vintageMetricsBody = document.getElementById('vintageMetricsBody');
  const winnerValue = document.getElementById('winnerValue');
  const winnerSubtitle = document.getElementById('winnerSubtitle');
  const runnerUpValue = document.getElementById('runnerUpValue');
  const runnerUpSubtitle = document.getElementById('runnerUpSubtitle');
  if (!dashboardResults) return;

  if (vintageEventExplorerScatterChart) {
    vintageEventExplorerScatterChart.destroy();
    vintageEventExplorerScatterChart = null;
  }
  if (vintageEventPlayerBarChart) {
    vintageEventPlayerBarChart.destroy();
    vintageEventPlayerBarChart = null;
  }
  if (vintageEventMwpBarChart) {
    vintageEventMwpBarChart.destroy();
    vintageEventMwpBarChart = null;
  }
  if (vintagePlayerDecksBarChart) {
    vintagePlayerDecksBarChart.destroy();
    vintagePlayerDecksBarChart = null;
  }
  destroyVintageMatchupGraphCharts();

  if (vintageMetricsBody) {
    vintageMetricsBody.classList.remove('event-explorer-mode');
  }
  if (uniquePlayersValue) {
    uniquePlayersValue.textContent = formatInteger(data?.unique_players || 0);
  }
  if (winnerValue) winnerValue.textContent = '--';
  if (winnerSubtitle) winnerSubtitle.textContent = 'Selected event';
  if (runnerUpValue) runnerUpValue.textContent = '--';
  if (runnerUpSubtitle) runnerUpSubtitle.textContent = 'Selected event';

  latestVintageMatchupHeatmapData = data?.event_matchup_heatmap || { subarchetypes: [], rows: [] };
  const heatmapSection = renderEventExplorerMatchupHeatmap(latestVintageMatchupHeatmapData, { showZoomButton: true });
  dashboardResults.innerHTML = `
    <div class="dashboard-table-grid" style="display: grid; grid-template-columns: 1fr; gap: 16px;">
      ${heatmapSection}
    </div>
    <div class="vintage-heatmap-zoom-modal" id="vintageHeatmapZoomModal" aria-hidden="true">
      <div class="vintage-heatmap-zoom-backdrop" data-vintage-zoom-close></div>
      <div class="vintage-heatmap-zoom-content" role="dialog" aria-modal="true" aria-label="Matchup Heatmap Zoom">
        <div class="vintage-heatmap-zoom-header">
          <strong>Matchup Heatmap (Zoomed)</strong>
          <button type="button" class="button primary vintage-header-action-btn" id="vintageHeatmapZoomCloseButton">
            <i class="fas fa-times"></i>
            Close
          </button>
        </div>
        <div class="vintage-heatmap-zoom-body" id="vintageHeatmapZoomModalBody"></div>
      </div>
    </div>
  `;

  const zoomButton = document.getElementById('matchupHeatmapZoomButton');
  if (zoomButton) {
    zoomButton.addEventListener('click', openVintageHeatmapZoomModal);
  }
  const closeButton = document.getElementById('vintageHeatmapZoomCloseButton');
  if (closeButton) {
    closeButton.addEventListener('click', closeVintageHeatmapZoomModal);
  }
  const zoomModal = document.getElementById('vintageHeatmapZoomModal');
  if (zoomModal) {
    zoomModal.addEventListener('click', function(event) {
      if (event.target && event.target.dataset && event.target.dataset.vintageZoomClose !== undefined) {
        closeVintageHeatmapZoomModal();
      }
    });
  }
}

function renderPlayerLeaderboardDashboard(data) {
  updateVintageMetricsVisibility('player-leaderboard', true);
  const dashboardResults = document.getElementById('dashboardResults');
  const uniquePlayersValue = document.getElementById('uniquePlayersValue');
  const vintageMetricsBody = document.getElementById('vintageMetricsBody');
  const winnerValue = document.getElementById('winnerValue');
  const winnerSubtitle = document.getElementById('winnerSubtitle');
  const runnerUpValue = document.getElementById('runnerUpValue');
  const runnerUpSubtitle = document.getElementById('runnerUpSubtitle');
  const trophiesValue = document.getElementById('trophiesValue');
  const trophiesSubtitle = document.getElementById('trophiesSubtitle');
  const top8RateValue = document.getElementById('top8RateValue');
  const top8RateSubtitle = document.getElementById('top8RateSubtitle');
  if (!dashboardResults) return;

  if (vintageEventExplorerScatterChart) {
    vintageEventExplorerScatterChart.destroy();
    vintageEventExplorerScatterChart = null;
  }
  if (vintageEventPlayerBarChart) {
    vintageEventPlayerBarChart.destroy();
    vintageEventPlayerBarChart = null;
  }
  if (vintageEventMwpBarChart) {
    vintageEventMwpBarChart.destroy();
    vintageEventMwpBarChart = null;
  }
  if (vintagePlayerDecksBarChart) {
    vintagePlayerDecksBarChart.destroy();
    vintagePlayerDecksBarChart = null;
  }
  destroyVintageMatchupGraphCharts();

  if (vintageMetricsBody) {
    vintageMetricsBody.classList.remove('event-explorer-mode');
  }
  if (uniquePlayersValue) {
    uniquePlayersValue.textContent = formatInteger(data?.unique_players || 0);
  }
  if (winnerValue) winnerValue.textContent = '--';
  if (winnerSubtitle) winnerSubtitle.textContent = 'Selected event';
  if (runnerUpValue) runnerUpValue.textContent = '--';
  if (runnerUpSubtitle) runnerUpSubtitle.textContent = 'Selected event';

  const rows = data?.leaderboard_rows || [];
  const selectedPlayer = data?.selected_player || '';
  const eventHistoryRows = data?.event_history_rows || [];
  const decksPlayedRows = data?.decks_played_rows || [];
  const headToHeadRows = data?.head_to_head_rows || [];
  const selectedPlayerLower = selectedPlayer.toLowerCase();
  const selectedPlayerRow = selectedPlayer
    ? rows.find(row => String(row.player || '').toLowerCase() === selectedPlayerLower)
    : null;
  if (trophiesValue) trophiesValue.textContent = selectedPlayerRow ? formatInteger(selectedPlayerRow.finals_wins) : '--';
  if (top8RateValue) top8RateValue.textContent = selectedPlayerRow ? formatPercent(selectedPlayerRow.top8_rate) : '--';
  if (trophiesSubtitle) trophiesSubtitle.textContent = selectedPlayer || 'Selected player';
  if (top8RateSubtitle) top8RateSubtitle.textContent = selectedPlayer || 'Selected player';
  const leaderboardTable = `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <h2 class="section-card-title">
          <i class="fas fa-trophy"></i>
          Player Leaderboard
        </h2>
      </div>
      <div class="section-card-body section-thin-body table-body-no-padding">
        <div class="table-wrapper" style="height: 190px;">
          <table class="modern-table" style="table-layout: fixed; width: 100%;">
            <colgroup>
              <col style="width: 22%;">
              <col style="width: calc(78% / 6);">
              <col style="width: calc(78% / 6);">
              <col style="width: calc(78% / 6);">
              <col style="width: calc(78% / 6);">
              <col style="width: calc(78% / 6);">
              <col style="width: calc(78% / 6);">
            </colgroup>
            <thead>
              <tr>
                <th style="text-align: center;">Player</th>
                <th>Total Matches</th>
                <th>Match Win%</th>
                <th>Total Events</th>
                <th>Finals Wins</th>
                <th>Top 8s</th>
                <th>Top 8 Rate</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(row => `
                <tr>
                  <td>
                    <a href="#" class="player-leaderboard-filter-select vintage-table-filter-link" data-player-value="${encodeURIComponent(row.player || '')}">
                      ${row.player || ''}
                    </a>
                  </td>
                  <td>${formatInteger(row.total_matches)}</td>
                  <td style="${getMetagameMwpHeatStyle(row.match_win_pct)}">${formatPercent(row.match_win_pct)}</td>
                  <td>${formatInteger(row.total_events)}</td>
                  <td>${formatInteger(row.finals_wins)}</td>
                  <td>${formatInteger(row.top8s)}</td>
                  <td>${formatPercent(row.top8_rate)}</td>
                </tr>
              `).join('') || '<tr><td colspan="7">No player data for selected filters.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  const eventHistoryTable = `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <h2 class="section-card-title">
          <i class="fas fa-history"></i>
          Event History
        </h2>
      </div>
      <div class="section-card-body section-thin-body table-body-no-padding">
        <div class="table-wrapper" style="height: 560px;">
          <table class="modern-table" style="table-layout: fixed; width: 100%;">
            <colgroup>
              <col style="width: 20%;">
              <col style="width: 20%;">
              <col style="width: 14%;">
              <col style="width: 20%;">
              <col style="width: 26%;">
            </colgroup>
            <thead>
              <tr>
                <th style="text-align: center !important;">Event Date</th>
                <th>Event Type</th>
                <th>Rank</th>
                <th>Record</th>
                <th>Deck</th>
              </tr>
            </thead>
            <tbody>
              ${!selectedPlayer
                ? '<tr><td colspan="5">Select a Player filter to view event history.</td></tr>'
                : (eventHistoryRows.map(row => {
                    const rankValue = Number(row.rank);
                    const normalizedRank = Number.isFinite(rankValue) ? rankValue : null;
                    let rowBackgroundColor = '';
                    if (normalizedRank === 1) {
                      rowBackgroundColor = '#fff7db';
                    } else if (normalizedRank !== null && normalizedRank <= 8 && normalizedRank >= 1) {
                      rowBackgroundColor = '#28a74524';
                    }
                    const rowStyle = rowBackgroundColor ? ` style="background-color: ${rowBackgroundColor};"` : '';
                    return `
                    <tr${rowStyle}>
                      <td style="text-align: center !important;">${row.event_date || ''}</td>
                      <td>${row.event_type || ''}</td>
                      <td>${row.rank ?? ''}</td>
                      <td>${row.record || ''}</td>
                      <td>
                        <a href="#" class="event-history-subarch-filter-select vintage-table-filter-link" data-subarchetype-value="${encodeURIComponent(row.deck || '')}">
                          ${row.deck || ''}
                        </a>
                      </td>
                    </tr>
                  `;
                }).join('') || '<tr><td colspan="5">No event history for the selected player and filters.</td></tr>')
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  const decksPlayedCard = `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <h2 class="section-card-title">
          <i class="fas fa-chart-bar"></i>
          Decks Played
        </h2>
      </div>
      <div class="section-card-body section-thin-body">
        <div class="chart-canvas-container" style="height: 272px;">
          <canvas id="player-decks-played-bar"></canvas>
        </div>
      </div>
    </div>
  `;

  const headToHeadTable = `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <h2 class="section-card-title">
          <i class="fas fa-handshake"></i>
          Head-to-Head
        </h2>
      </div>
      <div class="section-card-body section-thin-body table-body-no-padding">
        <div class="table-wrapper" style="height: 272px;">
          <table class="modern-table" style="table-layout: fixed; width: 100%;">
            <colgroup>
              <col style="width: 25%;">
              <col style="width: 25%;">
              <col style="width: 25%;">
              <col style="width: 25%;">
            </colgroup>
            <thead>
              <tr>
                <th style="text-align: center !important;">Opponent</th>
                <th>Total Matches</th>
                <th>Record</th>
                <th>Match Win%</th>
              </tr>
            </thead>
            <tbody>
              ${headToHeadRows.map(row => `
                <tr>
                  <td>
                    <a href="#" class="player-leaderboard-filter-select vintage-table-filter-link" data-player-value="${encodeURIComponent(row.opponent || '')}">
                      ${row.opponent || ''}
                    </a>
                  </td>
                  <td>${formatInteger(row.total_matches)}</td>
                  <td>${row.record || '0-0'}</td>
                  <td>${formatPercent(row.match_win_pct)}</td>
                </tr>
              `).join('') || '<tr><td colspan="4">No head-to-head data for the selected player and filters.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  dashboardResults.innerHTML = `
    <div class="dashboard-table-grid" style="display: grid; grid-template-columns: 1fr; gap: 16px;">
      ${leaderboardTable}
      ${selectedPlayer ? `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start;">
          ${eventHistoryTable}
          <div style="display: grid; grid-template-rows: auto auto; gap: 16px; align-content: start;">
            ${decksPlayedCard}
            ${headToHeadTable}
          </div>
        </div>
      ` : ''}
    </div>
  `;

  dashboardResults.querySelectorAll('.player-leaderboard-filter-select').forEach(link => {
    link.addEventListener('click', function(event) {
      event.preventDefault();
      applyPlayerLeaderboardFilterSelection(this.dataset.playerValue || '');
    });
  });
  dashboardResults.querySelectorAll('.event-history-subarch-filter-select').forEach(link => {
    link.addEventListener('click', function(event) {
      event.preventDefault();
      applySubarchetypeFilterSelection(this.dataset.subarchetypeValue || '');
    });
  });

  renderPlayerDecksPlayedChart(decksPlayedRows, selectedPlayer);
}

function renderMatchupGraphDashboard(data) {
  updateVintageMetricsVisibility('matchup-graph', true);
  const dashboardResults = document.getElementById('dashboardResults');
  const uniquePlayersValue = document.getElementById('uniquePlayersValue');
  const vintageMetricsBody = document.getElementById('vintageMetricsBody');
  const winnerValue = document.getElementById('winnerValue');
  const winnerSubtitle = document.getElementById('winnerSubtitle');
  const runnerUpValue = document.getElementById('runnerUpValue');
  const runnerUpSubtitle = document.getElementById('runnerUpSubtitle');
  const matchupGraphMwpValue = document.getElementById('matchupGraphMwpValue');
  const matchupGraphMwpSubtitle = document.getElementById('matchupGraphMwpSubtitle');
  if (!dashboardResults) return;

  if (vintageEventExplorerScatterChart) {
    vintageEventExplorerScatterChart.destroy();
    vintageEventExplorerScatterChart = null;
  }
  if (vintageEventPlayerBarChart) {
    vintageEventPlayerBarChart.destroy();
    vintageEventPlayerBarChart = null;
  }
  if (vintageEventMwpBarChart) {
    vintageEventMwpBarChart.destroy();
    vintageEventMwpBarChart = null;
  }
  if (vintagePlayerDecksBarChart) {
    vintagePlayerDecksBarChart.destroy();
    vintagePlayerDecksBarChart = null;
  }
  if (vintageScatterChart) {
    vintageScatterChart.destroy();
    vintageScatterChart = null;
  }
  destroyVintageMatchupGraphCharts();

  if (vintageMetricsBody) {
    vintageMetricsBody.classList.remove('event-explorer-mode');
  }
  if (uniquePlayersValue) {
    uniquePlayersValue.textContent = formatInteger(data?.unique_players || 0);
  }
  if (winnerValue) winnerValue.textContent = '--';
  if (winnerSubtitle) winnerSubtitle.textContent = 'Selected event';
  if (runnerUpValue) runnerUpValue.textContent = '--';
  if (runnerUpSubtitle) runnerUpSubtitle.textContent = 'Selected event';
  if (matchupGraphMwpValue) matchupGraphMwpValue.textContent = formatPercent(data?.match_win_pct || 0);
  if (matchupGraphMwpSubtitle) matchupGraphMwpSubtitle.textContent = 'Match Win%';

  const opponentArchetypeRows = data?.opponent_archetype_rows || [];
  const opponentSubarchetypeRows = data?.opponent_subarchetype_rows || [];
  const selectedArchetype = document.getElementById('archetypeFilter')?.value || '';
  const selectedSubarchetype = document.getElementById('subarchetypeFilter')?.value || '';
  const selectedDeckParts = [selectedArchetype, selectedSubarchetype].filter(Boolean);
  const titleSuffix = selectedDeckParts.length > 0 ? selectedDeckParts.join(' / ') : 'All Decks';

  const chartCard = (title, canvasId, noDataMessage) => `
    <div class="section-card section-thin-card">
      <div class="section-card-header">
        <h2 class="section-card-title">
          <i class="fas fa-project-diagram"></i>
          ${title}
        </h2>
      </div>
      <div class="section-card-body section-thin-body">
        <div class="chart-canvas-container" style="height: 400px;">
          <canvas id="${canvasId}"></canvas>
        </div>
        <div id="${canvasId}-empty" style="display: none; margin-top: 8px; color: var(--text-secondary);">${noDataMessage}</div>
      </div>
    </div>
  `;

  dashboardResults.innerHTML = `
    <div class="dashboard-table-grid" style="display: grid; grid-template-columns: 1fr; gap: 16px;">
      ${chartCard(`vs Opposing Archetypes (${titleSuffix})`, 'matchup-graph-opp-arch', 'No opposing archetype data for selected filters.')}
      ${chartCard(`vs Opposing Decks (${titleSuffix})`, 'matchup-graph-opp-subarch', 'No opposing subarchetype data for selected filters.')}
    </div>
  `;

  renderMatchupGraphCharts(opponentArchetypeRows, opponentSubarchetypeRows);
}

function renderMatchupGraphCharts(opponentArchetypeRows, opponentSubarchetypeRows) {
  ensureChartJsLoaded().then(() => {
    vintageMatchupOppArchChart = renderVintageMatchupComboChart(
      'matchup-graph-opp-arch',
      opponentArchetypeRows || [],
      'Opposing Archetypes'
    );
    vintageMatchupOppSubarchChart = renderVintageMatchupComboChart(
      'matchup-graph-opp-subarch',
      opponentSubarchetypeRows || [],
      'Opposing Decks'
    );
  }).catch(error => {
    console.error('Error rendering matchup graph charts:', error);
  });
}

function renderVintageMatchupComboChart(canvasId, rows, xAxisTitle) {
  const canvas = document.getElementById(canvasId);
  const emptyState = document.getElementById(`${canvasId}-empty`);
  if (!canvas) return null;

  const filteredRows = (rows || []).filter(row => {
    const name = String(row?.name || '').trim().toUpperCase();
    return name && name !== 'OTHER';
  });

  const sortedRows = filteredRows.slice().sort((a, b) => {
    const matchWinDiff = Number(a.match_win_pct || 0) - Number(b.match_win_pct || 0);
    if (matchWinDiff !== 0) return matchWinDiff;
    const matchDiff = Number(a.total_matches || 0) - Number(b.total_matches || 0);
    if (matchDiff !== 0) return matchDiff;
    return String(a.name || '').localeCompare(String(b.name || ''));
  });

  if (!sortedRows.length) {
    canvas.style.display = 'none';
    if (emptyState) emptyState.style.display = 'block';
    return null;
  }

  canvas.style.display = 'block';
  if (emptyState) emptyState.style.display = 'none';
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  const labels = sortedRows.map(row => {
    const label = String(row?.name || '').trim();
    return label ? `vs. ${label}` : '';
  });
  const totalMatches = sortedRows.map(row => Number(row.total_matches || 0));
  const matchWinPct = sortedRows.map(row => Number(row.match_win_pct || 0) * 100);
  const ciHigh = sortedRows.map(row => Number(row.ci_high || 0) * 100);
  const ciLow = sortedRows.map(row => Number(row.ci_low || 0) * 100);
  const maxMatches = totalMatches.length ? Math.max(...totalMatches) : 0;

  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          type: 'bar',
          label: 'Total Matches',
          yAxisID: 'yMatches',
          data: totalMatches,
          backgroundColor: 'rgba(203, 213, 225, 0.35)',
          borderColor: 'rgba(148, 163, 184, 0.95)',
          borderWidth: 1,
          order: 3
        },
        {
          type: 'line',
          label: 'Match Win%',
          yAxisID: 'yPct',
          data: matchWinPct,
          borderColor: 'rgba(22, 163, 74, 1)',
          backgroundColor: 'rgba(22, 163, 74, 0.15)',
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.2,
          order: 1
        },
        {
          type: 'line',
          label: '95% CI High',
          yAxisID: 'yPct',
          data: ciHigh,
          borderColor: 'rgba(234, 88, 12, 0.9)',
          pointRadius: 0,
          borderDash: [6, 4],
          tension: 0.15,
          order: 1
        },
        {
          type: 'line',
          label: '95% CI Low',
          yAxisID: 'yPct',
          data: ciLow,
          borderColor: 'rgba(234, 88, 12, 0.9)',
          pointRadius: 0,
          borderDash: [6, 4],
          tension: 0.15,
          order: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: {
        padding: {
          bottom: 0
        }
      },
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          ...getVintageLegendOptions(true),
          position: 'top',
          align: 'center'
        },
        title: getVintageTitleOptions(''),
        subtitle: getVintageSubtitleOptions(''),
        tooltip: getVintageTooltipOptions({
          filter: function(context) {
            return context.datasetIndex === 0;
          },
          callbacks: {
            label: function(context) {
              const idx = context?.dataIndex ?? 0;
              const row = sortedRows[idx] || {};
              return [
                `Total Matches: ${formatInteger(row.total_matches || 0)}`,
                `Match Win%: ${formatPercent(row.match_win_pct || 0)}`,
                `95% CI High: ${formatPercent(row.ci_high || 0)}`,
                `95% CI Low: ${formatPercent(row.ci_low || 0)}`
              ];
            }
          }
        })
      },
      scales: {
        x: {
          title: getVintageAxisTitle(''),
          grid: { display: false },
          ticks: getVintageTickOptions({ autoSkip: false })
        },
        yMatches: {
          type: 'linear',
          position: 'left',
          beginAtZero: true,
          max: Math.max(maxMatches + 2, 5),
          grid: { display: false },
          title: getVintageAxisTitle('Total Matches'),
          ticks: getVintageTickOptions()
        },
        yPct: {
          type: 'linear',
          position: 'right',
          beginAtZero: true,
          min: 0,
          max: 100,
          grid: { display: false },
          title: getVintageAxisTitle('Match Win% / CI'),
          ticks: getVintageTickOptions({
            callback: function(value) {
              return `${Number(value).toFixed(0)}%`;
            }
          })
        }
      }
    }
  });
}

function ensureChartJsLoaded() {
  return new Promise((resolve, reject) => {
    if (window.Chart) {
      if (!vintageChartDefaultsApplied && Chart.defaults) {
        Chart.defaults.color = getVintageChartTextColor();
        vintageChartDefaultsApplied = true;
      }
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
    script.async = true;
    script.onload = () => {
      if (!vintageChartDefaultsApplied && window.Chart && Chart.defaults) {
        Chart.defaults.color = getVintageChartTextColor();
        vintageChartDefaultsApplied = true;
      }
      resolve();
    };
    script.onerror = () => reject(new Error('Failed to load Chart.js'));
    document.head.appendChild(script);
  });
}

function renderVintageMetagameScatter(scatterRows, mode, groupBy) {
  ensureChartJsLoaded().then(() => {
    const canvas = document.getElementById('vintage-meta-scatter');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (vintageScatterChart) {
      vintageScatterChart.destroy();
      vintageScatterChart = null;
    }

    const normalizedMode = mode === 'exclude-mirrors' ? 'exclude-mirrors' : 'overall';
    const normalizedGroupBy = groupBy === 'archetype' ? 'archetype' : 'subarchetype';
    const mwpKey = normalizedMode === 'exclude-mirrors' ? 'mwp_no_mirrors' : 'mwp_overall';
    const totalMatchesKey = normalizedMode === 'exclude-mirrors' ? 'total_matches_no_mirrors' : 'total_matches';
    const mwpLabel = normalizedMode === 'exclude-mirrors' ? 'MWP w/o Mirrors' : 'MWP Overall';
    const totalMatchesLabel = normalizedMode === 'exclude-mirrors' ? 'Total Matches w/o Mirrors' : 'Total Matches';
    const pointGroupLabel = normalizedGroupBy === 'archetype' ? 'Archetypes' : 'Subarchetypes';

    const points = (scatterRows || []).map(row => ({
      x: Number((row.meta_pct || 0) * 100),
      y: Number((row[mwpKey] || 0) * 100),
      label: row.name || '',
      players: row.players || 0,
      totalMatches: row[totalMatchesKey] || 0
    }));

    const yValues = points.map(point => point.y).filter(value => Number.isFinite(value));
    let yMin = 0;
    let yMax = 100;
    if (yValues.length > 0) {
      const rawMin = Math.min(...yValues);
      const rawMax = Math.max(...yValues);
      const span = Math.max(rawMax - rawMin, 1);
      const padding = Math.max(span * 0.08, 0.5);
      yMin = Math.max(0, Math.floor(rawMin - padding));
      yMax = Math.min(100, Math.ceil(rawMax + padding));
      if ((yMax - yMin) < 1) {
        yMin = Math.max(0, yMin - 1);
        yMax = Math.min(100, yMax + 1);
      }
    }

    const pointLabelPlugin = {
      id: 'pointLabelPlugin',
      afterDatasetsDraw(chart) {
        const dataset = chart.data.datasets[0];
        const meta = chart.getDatasetMeta(0);
        const ctx = chart.ctx;

        ctx.save();
        ctx.font = '11px Arial';
        ctx.fillStyle = '#111';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';

        const placementCounts = new Map();
        const chartArea = chart.chartArea || {};

        meta.data.forEach((pointElement, index) => {
          const raw = dataset.data[index] || {};
          const label = raw.label || '';
          if (!label) return;
          const { x, y } = pointElement.getProps(['x', 'y'], true);
          const bucketKey = `${Math.round(x / 6)}|${Math.round(y / 6)}`;
          const placementIndex = placementCounts.get(bucketKey) || 0;
          placementCounts.set(bucketKey, placementIndex + 1);

          // Stagger labels for points sharing nearby coordinates.
          let dx = 8 + ((placementIndex % 3) * 8);
          let dy = -8 - (Math.floor(placementIndex / 3) * 10);

          // Keep labels inside plot area by flipping/raising near edges.
          if (chartArea.right && x > (chartArea.right - 70)) {
            dx = -8 - ((placementIndex % 3) * 8);
          }
          if (chartArea.left && x < (chartArea.left + 20)) {
            dx = 8 + ((placementIndex % 3) * 8);
          }
          if (chartArea.bottom && y > (chartArea.bottom - 18)) {
            dy = -12 - (placementIndex * 10);
          }
          if (chartArea.top && (y + dy) < (chartArea.top + 10)) {
            dy = 10 + ((placementIndex % 3) * 8);
          }

          ctx.textAlign = dx < 0 ? 'right' : 'left';
          ctx.fillText(label, x + dx, y + dy);
        });

        ctx.restore();
      }
    };

    vintageScatterChart = new Chart(ctx, {
      plugins: [pointLabelPlugin],
      type: 'scatter',
      data: {
        datasets: [
          {
            label: pointGroupLabel,
            data: points,
            backgroundColor: 'rgba(0, 57, 166, 0.65)',
            borderColor: 'rgba(0, 57, 166, 1)',
            pointRadius: 5,
            pointHoverRadius: 7
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            top: 20,
            right: 60,
            bottom: 0,
            left: 10
          }
        },
        plugins: {
          legend: getVintageLegendOptions(false),
          title: getVintageTitleOptions(''),
          subtitle: getVintageSubtitleOptions(''),
          tooltip: getVintageTooltipOptions({
            callbacks: {
              label: function(context) {
                const raw = context.raw || {};
                return [
                  raw.label || '',
                  `Meta %: ${raw.x.toFixed(1)}%`,
                  `${mwpLabel}: ${raw.y.toFixed(1)}%`,
                  `Players: ${raw.players}`,
                  `${totalMatchesLabel}: ${raw.totalMatches}`
                ];
              }
            }
          })
        },
        scales: {
          x: {
            title: getVintageAxisTitle('Meta %'),
            ticks: getVintageTickOptions()
          },
          y: {
            title: getVintageAxisTitle(`${mwpLabel} %`),
            min: yMin,
            max: yMax,
            ticks: getVintageTickOptions({
              precision: 0,
              callback: function(value) {
                return `${Math.round(Number(value))}`;
              }
            })
          }
        }
      }
    });
  }).catch(error => {
    console.error('Error rendering vintage scatter chart:', error);
  });
}

function renderEventExplorerCharts(scatterRows, barRows, selectedEventIdValue) {
  if (!selectedEventIdValue) {
    if (vintageEventExplorerScatterChart) {
      vintageEventExplorerScatterChart.destroy();
      vintageEventExplorerScatterChart = null;
    }
    if (vintageEventPlayerBarChart) {
      vintageEventPlayerBarChart.destroy();
      vintageEventPlayerBarChart = null;
    }
    if (vintageEventMwpBarChart) {
      vintageEventMwpBarChart.destroy();
      vintageEventMwpBarChart = null;
    }
    return;
  }

  ensureChartJsLoaded().then(() => {
    const scatterCanvas = document.getElementById('event-explorer-subarch-scatter');
    const playersBarCanvas = document.getElementById('event-explorer-arch-players-bar');
    const mwpBarCanvas = document.getElementById('event-explorer-arch-mwp-bar');
    if (!scatterCanvas || !playersBarCanvas || !mwpBarCanvas) return;
    const scatterCtx = scatterCanvas.getContext('2d');
    const playersBarCtx = playersBarCanvas.getContext('2d');
    const mwpBarCtx = mwpBarCanvas.getContext('2d');
    if (!scatterCtx || !playersBarCtx || !mwpBarCtx) return;

    if (vintageEventExplorerScatterChart) {
      vintageEventExplorerScatterChart.destroy();
      vintageEventExplorerScatterChart = null;
    }
    if (vintageEventPlayerBarChart) {
      vintageEventPlayerBarChart.destroy();
      vintageEventPlayerBarChart = null;
    }
    if (vintageEventMwpBarChart) {
      vintageEventMwpBarChart.destroy();
      vintageEventMwpBarChart = null;
    }

    const points = (scatterRows || []).map(row => ({
      x: Number(row.players || 0),
      y: Number((row.mwp_no_mirrors || 0) * 100),
      label: row.name || '',
      totalMatchesNoMirrors: row.total_matches_no_mirrors || 0
    }));

    const playerSortedRows = [...(barRows || [])].sort((a, b) => (Number(b.players || 0) - Number(a.players || 0)));
    const playerLabels = playerSortedRows.map(row => row.name || '');
    const playersData = playerSortedRows.map(row => Number(row.players || 0));
    const playerValues = playersData.filter(value => Number.isFinite(value));
    let playerMax = 1;
    if (playerValues.length > 0) {
      const rawPlayerMax = Math.max(...playerValues);
      const playerPadding = Math.max(rawPlayerMax * 0.12, 1);
      playerMax = Math.max(1, Math.round(rawPlayerMax + playerPadding));
    }

    const mwpSortedRows = [...(barRows || [])].sort((a, b) => (Number(b.mwp_no_mirrors || 0) - Number(a.mwp_no_mirrors || 0)));
    const mwpLabels = mwpSortedRows.map(row => row.name || '');
    const mwpData = mwpSortedRows.map(row => Number((row.mwp_no_mirrors || 0) * 100));

    const yValues = points.map(point => point.y).filter(value => Number.isFinite(value));
    const xValues = points.map(point => point.x).filter(value => Number.isFinite(value));
    let yMin = 0;
    let yMax = 100;
    let xMax = 10;
    if (yValues.length > 0) {
      const rawMin = Math.min(...yValues);
      const rawMax = Math.max(...yValues);
      const span = Math.max(rawMax - rawMin, 1);
      const padding = Math.max(span * 0.08, 0.5);
      yMin = Math.max(0, rawMin - padding);
      yMax = Math.min(100, rawMax + padding);
    }
    if (xValues.length > 0) {
      const rawXMax = Math.max(...xValues);
      const xPadding = Math.max(rawXMax * 0.12, 1);
      xMax = rawXMax + xPadding;
    }

    const pointLabelPlugin = {
      id: 'eventExplorerPointLabelPlugin',
      afterDatasetsDraw(chart) {
        const dataset = chart.data.datasets[0];
        const meta = chart.getDatasetMeta(0);
        const ctx = chart.ctx;

        ctx.save();
        ctx.font = '11px Arial';
        ctx.fillStyle = '#111';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';

        const placementCounts = new Map();
        const chartArea = chart.chartArea || {};

        meta.data.forEach((pointElement, index) => {
          const raw = dataset.data[index] || {};
          const label = raw.label || '';
          if (!label) return;
          const { x, y } = pointElement.getProps(['x', 'y'], true);
          const bucketKey = `${Math.round(x / 6)}|${Math.round(y / 6)}`;
          const placementIndex = placementCounts.get(bucketKey) || 0;
          placementCounts.set(bucketKey, placementIndex + 1);

          let dx = 8 + ((placementIndex % 3) * 8);
          let dy = -8 - (Math.floor(placementIndex / 3) * 10);

          if (chartArea.right && x > (chartArea.right - 70)) {
            dx = -8 - ((placementIndex % 3) * 8);
          }
          if (chartArea.left && x < (chartArea.left + 20)) {
            dx = 8 + ((placementIndex % 3) * 8);
          }
          if (chartArea.bottom && y > (chartArea.bottom - 18)) {
            dy = -12 - (placementIndex * 10);
          }
          if (chartArea.top && (y + dy) < (chartArea.top + 10)) {
            dy = 10 + ((placementIndex % 3) * 8);
          }

          ctx.textAlign = dx < 0 ? 'right' : 'left';
          ctx.fillText(label, x + dx, y + dy);
        });

        ctx.restore();
      }
    };

    const horizontalBarValueLabelPlugin = {
      id: 'horizontalBarValueLabelPlugin',
      afterDatasetsDraw(chart) {
        if (chart.config.type !== 'bar') return;
        const dataset = chart.data?.datasets?.[0];
        const meta = chart.getDatasetMeta(0);
        if (!dataset || !meta?.data?.length) return;

        const isMwpBar = (chart.canvas?.id === 'event-explorer-arch-mwp-bar');
        const ctx = chart.ctx;
        const chartArea = chart.chartArea || {};

        ctx.save();
        ctx.font = '11px Arial';
        ctx.fillStyle = '#111';
        ctx.textBaseline = 'middle';

        meta.data.forEach((barElement, index) => {
          const rawValue = Number(dataset.data[index] || 0);
          const labelText = isMwpBar ? `${rawValue.toFixed(1)}%` : `${Math.round(rawValue).toLocaleString()}`;
          const barPos = barElement.tooltipPosition();
          const desiredX = barPos.x + 6;
          const maxX = (chartArea.right || desiredX) - 2;
          const drawX = Math.min(desiredX, maxX);
          const drawY = barPos.y;

          ctx.textAlign = drawX >= maxX ? 'right' : 'left';
          ctx.fillText(labelText, drawX, drawY);
        });

        ctx.restore();
      }
    };

    vintageEventExplorerScatterChart = new Chart(scatterCtx, {
      plugins: [pointLabelPlugin],
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Subarchetypes',
            data: points,
            backgroundColor: 'rgba(15, 23, 42, 0.6)',
            borderColor: 'rgba(15, 23, 42, 1)',
            pointRadius: 5,
            pointHoverRadius: 7
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            right: 70,
            bottom: 0
          }
        },
        plugins: {
          legend: getVintageLegendOptions(false),
          title: getVintageTitleOptions(''),
          subtitle: getVintageSubtitleOptions(''),
          tooltip: getVintageTooltipOptions({
            callbacks: {
              label: function(context) {
                const raw = context.raw || {};
                return [
                  raw.label || '',
                  `Player Count: ${raw.x}`,
                  `MWP w/o Mirrors: ${raw.y.toFixed(1)}%`,
                  `Total Matches w/o Mirrors: ${raw.totalMatchesNoMirrors}`
                ];
              }
            }
          })
        },
        scales: {
          x: {
            title: getVintageAxisTitle('Player Count'),
            beginAtZero: true,
            max: xMax,
            ticks: getVintageTickOptions()
          },
          y: {
            title: getVintageAxisTitle('MWP w/o Mirrors %'),
            min: yMin,
            max: yMax,
            ticks: getVintageTickOptions()
          }
        }
      }
    });

    vintageEventPlayerBarChart = new Chart(playersBarCtx, {
      plugins: [horizontalBarValueLabelPlugin],
      type: 'bar',
      data: {
        labels: playerLabels,
        datasets: [
          {
            label: 'Player Count',
            data: playersData,
            backgroundColor: 'rgba(59, 130, 246, 0.75)',
            borderColor: 'rgba(59, 130, 246, 1)',
            borderWidth: 1
          }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            bottom: 0
          }
        },
        plugins: {
          legend: getVintageLegendOptions(false),
          title: getVintageTitleOptions(''),
          subtitle: getVintageSubtitleOptions('')
        },
        scales: {
          x: {
            beginAtZero: true,
            min: 0,
            max: playerMax,
            grid: { display: false },
            title: getVintageAxisTitle('Player Count'),
            ticks: getVintageTickOptions({ display: false })
          },
          y: {
            ticks: getVintageTickOptions({ autoSkip: false })
          }
        }
      }
    });

    const mwpValues = mwpData.filter(value => Number.isFinite(value));
    let mwpMin = 0;
    let mwpMax = 100;
    if (mwpValues.length > 0) {
      const rawMin = Math.min(...mwpValues);
      const rawMax = Math.max(...mwpValues);
      const span = Math.max(rawMax - rawMin, 1);
      const padding = Math.max(span * 0.08, 1);
      mwpMin = Math.max(0, rawMin - padding);
      mwpMax = Math.min(100, rawMax + padding);
      if ((mwpMax - mwpMin) < 5) {
        mwpMin = Math.max(0, mwpMin - 2.5);
        mwpMax = Math.min(100, mwpMax + 2.5);
      }
    }
    const mwpRightPadding = Math.max((mwpMax - mwpMin) * 0.1, 1);
    mwpMax = Math.min(100, mwpMax + mwpRightPadding);
    mwpMin = Math.max(0, Math.round(mwpMin));
    mwpMax = Math.min(100, Math.round(mwpMax));
    if (mwpMax <= mwpMin) {
      mwpMax = Math.min(100, mwpMin + 1);
    }

    vintageEventMwpBarChart = new Chart(mwpBarCtx, {
      plugins: [horizontalBarValueLabelPlugin],
      type: 'bar',
      data: {
        labels: mwpLabels,
        datasets: [
          {
            label: 'MWP w/o Mirrors %',
            data: mwpData,
            backgroundColor: 'rgba(16, 185, 129, 0.75)',
            borderColor: 'rgba(16, 185, 129, 1)',
            borderWidth: 1
          }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            bottom: 0
          }
        },
        plugins: {
          legend: getVintageLegendOptions(false),
          title: getVintageTitleOptions(''),
          subtitle: getVintageSubtitleOptions('')
        },
        scales: {
          x: {
            beginAtZero: false,
            min: mwpMin,
            max: mwpMax,
            grid: { display: false },
            title: getVintageAxisTitle('MWP w/o Mirrors %'),
            ticks: getVintageTickOptions({ display: false })
          },
          y: {
            ticks: getVintageTickOptions({ autoSkip: false })
          }
        }
      }
    });
  }).catch(error => {
    console.error('Error rendering event explorer charts:', error);
  });
}

function renderPlayerDecksPlayedChart(decksPlayedRows, selectedPlayer) {
  if (!selectedPlayer) return;

  ensureChartJsLoaded().then(() => {
    const canvas = document.getElementById('player-decks-played-bar');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (vintagePlayerDecksBarChart) {
      vintagePlayerDecksBarChart.destroy();
      vintagePlayerDecksBarChart = null;
    }

    const rows = (decksPlayedRows || []).slice().sort((a, b) => {
      const matchDiff = Number(b.total_matches || 0) - Number(a.total_matches || 0);
      if (matchDiff !== 0) return matchDiff;
      return Number(b.match_win_pct || 0) - Number(a.match_win_pct || 0);
    });

    const labels = rows.map(row => row.subarchetype || '');
    const matches = rows.map(row => Number(row.total_matches || 0));
    const winPcts = rows.map(row => Number(row.match_win_pct || 0));
    const maxValue = matches.length ? Math.max(...matches) : 0;
    const xPadding = Math.max(maxValue * 0.25, 2);

    const barLabelPlugin = {
      id: 'playerDecksBarLabelPlugin',
      afterDatasetsDraw(chart) {
        const datasetMeta = chart.getDatasetMeta(0);
        const localCtx = chart.ctx;
        localCtx.save();
        localCtx.font = '11px Arial';
        localCtx.fillStyle = '#111';
        localCtx.textAlign = 'left';
        localCtx.textBaseline = 'middle';

        datasetMeta.data.forEach((bar, index) => {
          const matchesValue = Number(matches[index] || 0);
          const winPctValue = Number(winPcts[index] || 0);
          const labelText = `${formatInteger(matchesValue)} - ${(winPctValue * 100).toFixed(1)}%`;
          localCtx.fillText(labelText, bar.x + 8, bar.y);
        });

        localCtx.restore();
      }
    };

    vintagePlayerDecksBarChart = new Chart(ctx, {
      type: 'bar',
      plugins: [barLabelPlugin],
      data: {
        labels,
        datasets: [
          {
            label: 'Total Matches',
            data: matches,
            backgroundColor: 'rgba(37, 99, 235, 0.72)',
            borderColor: 'rgba(37, 99, 235, 1)',
            borderWidth: 1
          }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: {
          padding: {
            bottom: 0
          }
        },
        plugins: {
          legend: getVintageLegendOptions(false),
          title: getVintageTitleOptions(''),
          subtitle: getVintageSubtitleOptions(''),
          tooltip: getVintageTooltipOptions({
            callbacks: {
              label: function(context) {
                const idx = context.dataIndex;
                const m = Number(matches[idx] || 0);
                const pct = Number(winPcts[idx] || 0);
                return `Matches: ${formatInteger(m)} | Match Win%: ${(pct * 100).toFixed(1)}%`;
              }
            }
          })
        },
        scales: {
          x: {
            beginAtZero: true,
            max: maxValue + xPadding,
            title: getVintageAxisTitle('Total Matches Played'),
            grid: { display: false },
            ticks: getVintageTickOptions()
          },
          y: {
            ticks: getVintageTickOptions({ autoSkip: false })
          }
        }
      }
    });
  }).catch(error => {
    console.error('Error rendering player decks played chart:', error);
  });
}

async function generateVintageDashboard() {
  const dashboardType = document.getElementById('dashboardType')?.value;
  const filters = getCurrentVintageFilterValues();
  const loadingState = document.getElementById('loadingState');
  const dashboardResults = document.getElementById('dashboardResults');

  try {
    updateVintageMetricsVisibility('', false);
    if (loadingState) {
      loadingState.style.display = 'block';
    }
    if (dashboardResults) {
      dashboardResults.style.display = 'none';
    }

    const response = await fetch('/api/vintage/dashboard/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-By': 'MTGO-Tracker'
      },
      body: JSON.stringify({
        dashboard_type: dashboardType,
        filters
      })
    });

    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `Failed to generate dashboard (${response.status})`);
    }
    if (dashboardType === 'metagame-breakdown') {
      renderVintageMetagameDashboard(result.data);
    } else if (dashboardType === 'event-explorer') {
      renderEventExplorerDashboard(result.data);
    } else if (dashboardType === 'player-leaderboard') {
      renderPlayerLeaderboardDashboard(result.data);
    } else if (dashboardType === 'matchup-heatmap') {
      renderMatchupHeatmapDashboard(result.data);
    } else if (dashboardType === 'matchup-graph') {
      renderMatchupGraphDashboard(result.data);
    } else {
      alert('This dashboard type is not implemented yet.');
    }

    // Keep table hover behavior aligned with /dashboards.
    setTimeout(() => {
      addVintageTableTooltips();
    }, 0);
  } catch (error) {
    console.error('Error generating vintage dashboard:', error);
  } finally {
    if (loadingState) {
      loadingState.style.display = 'none';
    }
    if (dashboardResults) {
      dashboardResults.style.display = 'block';
    }
  }
}