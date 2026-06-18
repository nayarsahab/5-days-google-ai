// State Management
let releaseNotes = [];
let filteredNotes = [];
let currentFilter = 'all';
let searchQuery = '';
let lastFetchedTime = null;

// DOM Elements
const feedContainer = document.getElementById('feedContainer');
const searchInput = document.getElementById('searchInput');
const tagFilters = document.getElementById('tagFilters');
const totalUpdatesCount = document.getElementById('totalUpdatesCount');
const lastFetchedTimeEl = document.getElementById('lastFetchedTime');
const refreshBtn = document.getElementById('refreshBtn');
const refreshIcon = document.getElementById('refreshIcon');
const loadingOverlay = document.getElementById('loadingOverlay');
const feedSubtitle = document.getElementById('feedSubtitle');
const themeToggleBtn = document.getElementById('themeToggleBtn');
const themeIcon = document.getElementById('themeIcon');
const exportCsvBtn = document.getElementById('exportCsvBtn');

// Modal Elements
const tweetModal = document.getElementById('tweetModal');
const tweetTextarea = document.getElementById('tweetTextarea');
const charCounter = document.getElementById('charCounter');
const closeModalBtn = document.getElementById('closeModalBtn');
const cancelTweetBtn = document.getElementById('cancelTweetBtn');
const confirmTweetBtn = document.getElementById('confirmTweetBtn');

// Toast Elements
const toast = document.getElementById('toast');
const toastIcon = document.getElementById('toastIcon');
const toastMessage = document.getElementById('toastMessage');

// Event Listeners
document.addEventListener('DOMContentLoaded', init);
searchInput.addEventListener('input', handleSearch);
tagFilters.addEventListener('click', handleFilterClick);
refreshBtn.addEventListener('click', refreshNotes);
themeToggleBtn.addEventListener('click', toggleTheme);
exportCsvBtn.addEventListener('click', exportToCSV);

// Modal listeners
closeModalBtn.addEventListener('click', closeTweetModal);
cancelTweetBtn.addEventListener('click', closeTweetModal);
tweetTextarea.addEventListener('input', updateCharCount);

// Init function
function init() {
    loadSavedTheme();
    loadReleaseNotes();
}

// Fetch notes from Flask backend
async function loadReleaseNotes() {
    showLoading(true);
    try {
        const response = await fetch('/api/release-notes');
        if (!response.ok) throw new Error('Failed to fetch release notes from API');
        
        releaseNotes = await response.json();
        lastFetchedTime = new Date();
        lastFetchedTimeEl.textContent = formatTime(lastFetchedTime);
        
        applyFiltersAndRender();
        showToast('Release notes loaded successfully!', 'success');
    } catch (error) {
        console.error('Error fetching release notes:', error);
        showToast(error.message || 'Error loading release notes.', 'error');
        renderEmptyState('Failed to load release notes. Please click Refresh to try again.');
    } finally {
        showLoading(false);
    }
}

// Force refresh notes
async function refreshNotes() {
    if (refreshBtn.disabled) return;
    
    // UI Loading state
    refreshBtn.disabled = true;
    refreshIcon.classList.add('fa-spin');
    showLoading(true);
    
    try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        if (!response.ok) throw new Error('Refresh failed');
        
        const result = await response.json();
        if (result.status === 'success') {
            await loadReleaseNotes();
            showToast('Release notes updated successfully!', 'success');
        } else {
            throw new Error(result.error || 'Failed to update release notes');
        }
    } catch (error) {
        console.error('Error refreshing release notes:', error);
        showToast(error.message || 'Failed to refresh release notes.', 'error');
    } finally {
        refreshBtn.disabled = false;
        refreshIcon.classList.remove('fa-spin');
        showLoading(false);
    }
}

// Handle search input
function handleSearch(e) {
    searchQuery = e.target.value.toLowerCase().trim();
    applyFiltersAndRender();
}

// Handle tag filter buttons
function handleFilterClick(e) {
    const btn = e.target.closest('.tag-filter');
    if (!btn) return;
    
    // Toggle active class
    document.querySelectorAll('.tag-filter').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    
    currentFilter = btn.getAttribute('data-type');
    applyFiltersAndRender();
}

// Filter release notes and trigger rendering
function applyFiltersAndRender() {
    filteredNotes = [];
    let totalCount = 0;
    
    // Deep clone/filter logic
    releaseNotes.forEach(entry => {
        // Filter updates inside the entry
        const matchingUpdates = entry.updates.filter(update => {
            const matchesCategory = (currentFilter === 'all' || update.type.toLowerCase() === currentFilter.toLowerCase());
            const matchesSearch = (
                searchQuery === '' || 
                update.text.toLowerCase().includes(searchQuery) ||
                update.type.toLowerCase().includes(searchQuery) ||
                entry.date.toLowerCase().includes(searchQuery)
            );
            return matchesCategory && matchesSearch;
        });
        
        if (matchingUpdates.length > 0) {
            filteredNotes.push({
                ...entry,
                updates: matchingUpdates
            });
            totalCount += matchingUpdates.length;
        }
    });
    
    totalUpdatesCount.textContent = totalCount;
    renderFeed();
}

// Helper for getting category icons
function getCategoryIcon(type) {
    const category = type.toLowerCase();
    switch (category) {
        case 'feature':
            return '<i class="fa-solid fa-circle-check"></i>';
        case 'announcement':
            return '<i class="fa-solid fa-circle-info"></i>';
        case 'change':
            return '<i class="fa-solid fa-sliders"></i>';
        case 'breaking':
            return '<i class="fa-solid fa-triangle-exclamation"></i>';
        case 'issue':
            return '<i class="fa-solid fa-bug"></i>';
        default:
            return '<i class="fa-solid fa-asterisk"></i>';
    }
}

// Render feed list
function renderFeed() {
    feedContainer.innerHTML = '';
    
    if (filteredNotes.length === 0) {
        renderEmptyState('No updates found matching your search or filters.');
        return;
    }
    
    filteredNotes.forEach(entry => {
        // Create Date Section
        const dateSection = document.createElement('section');
        dateSection.className = 'date-section';
        
        const dateHeader = document.createElement('div');
        dateHeader.className = 'date-header';
        dateHeader.innerHTML = `<span>${entry.date}</span>`;
        dateSection.appendChild(dateHeader);
        
        // Cards Grid Container (for desktop responsive multi-column layout)
        const cardsGrid = document.createElement('div');
        cardsGrid.className = 'cards-grid';
        
        // Render each update card
        entry.updates.forEach(update => {
            const card = document.createElement('div');
            const catClass = update.type.toLowerCase();
            card.className = `update-card category-${catClass}`;
            
            // Generate clean markup
            card.innerHTML = `
                <div class="card-header">
                    <span class="category-pill ${catClass}">${getCategoryIcon(update.type)} &nbsp;${update.type}</span>
                </div>
                <div class="card-body">
                    ${update.html}
                </div>
                <div class="card-footer">
                    <button class="btn btn-action-copy" title="Copy text to clipboard">
                        <i class="fa-solid fa-copy"></i>
                        <span>Copy</span>
                    </button>
                    <button class="btn btn-action-tweet" data-date="${entry.date}" data-type="${update.type}">
                        <i class="fa-brands fa-x-twitter"></i> Tweet Update
                    </button>
                </div>
            `;
            
            // Add click event for the tweet button
            const tweetBtn = card.querySelector('.btn-action-tweet');
            tweetBtn.addEventListener('click', () => openTweetComposer(entry.date, update));
            
            // Add click event for the copy button
            const copyBtn = card.querySelector('.btn-action-copy');
            copyBtn.addEventListener('click', async () => {
                try {
                    const fullText = `BigQuery Update (${entry.date}) [${update.type}]: ${update.text}`;
                    await navigator.clipboard.writeText(fullText);
                    
                    const span = copyBtn.querySelector('span');
                    const icon = copyBtn.querySelector('i');
                    
                    span.textContent = 'Copied!';
                    icon.className = 'fa-solid fa-circle-check';
                    copyBtn.style.color = 'var(--color-feature)';
                    copyBtn.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                    
                    showToast('Update copied to clipboard!', 'success');
                    
                    setTimeout(() => {
                        span.textContent = 'Copy';
                        icon.className = 'fa-solid fa-copy';
                        copyBtn.style.color = '';
                        copyBtn.style.borderColor = '';
                    }, 2000);
                } catch (err) {
                    console.error('Copy failed:', err);
                    showToast('Failed to copy to clipboard.', 'error');
                }
            });
            
            cardsGrid.appendChild(card);
        });
        
        dateSection.appendChild(cardsGrid);
        feedContainer.appendChild(dateSection);
    });
}

// Render empty state if list is empty
function renderEmptyState(message) {
    feedContainer.innerHTML = `
        <div class="empty-state">
            <i class="fa-solid fa-magnifying-glass"></i>
            <p>${message}</p>
        </div>
    `;
}

// Tweet Composer Modal Logic
let currentTweetText = '';
const maxTweetLength = 280;
const TWEET_URL = 'https://cloud.google.com/bigquery/docs/release-notes';

function openTweetComposer(date, update) {
    // Generate preset tweet text
    // E.g. BigQuery update (June 17, 2026): [Feature] Autonomous embedding generation generally available.
    let updateText = update.text;
    
    // Template: BigQuery Update [Date] ([Type]): [Text]
    const prefix = `BigQuery Update (${date}) - [${update.type}]: `;
    const suffix = `\n\n#BigQuery #GoogleCloud\n${TWEET_URL}`;
    
    // Calculate space left for the main update text
    const availableLength = maxTweetLength - prefix.length - suffix.length;
    
    if (updateText.length > availableLength) {
        updateText = updateText.substring(0, availableLength - 3) + '...';
    }
    
    const draftText = `${prefix}${updateText}${suffix}`;
    
    tweetTextarea.value = draftText;
    updateCharCount();
    
    // Open modal
    tweetModal.classList.remove('hidden');
    // Force CSS transition reflow
    setTimeout(() => tweetModal.classList.add('show'), 10);
    
    // Set up confirm action
    confirmTweetBtn.onclick = () => {
        const text = encodeURIComponent(tweetTextarea.value);
        const url = `https://twitter.com/intent/tweet?text=${text}`;
        window.open(url, '_blank');
        closeTweetModal();
        showToast('Twitter intent opened in new tab!', 'success');
    };
}

function closeTweetModal() {
    tweetModal.classList.remove('show');
    setTimeout(() => tweetModal.classList.add('hidden'), 300);
}

function updateCharCount() {
    const textLength = tweetTextarea.value.length;
    const remaining = maxTweetLength - textLength;
    
    charCounter.textContent = remaining;
    
    // Visual indicators
    charCounter.className = 'char-counter';
    if (remaining < 40 && remaining >= 0) {
        charCounter.classList.add('warning');
    } else if (remaining < 0) {
        charCounter.classList.add('danger');
    }
    
    // Disable confirm button if text is too long or empty
    if (remaining < 0 || textLength === 0) {
        confirmTweetBtn.disabled = true;
        confirmTweetBtn.style.opacity = 0.5;
        confirmTweetBtn.style.cursor = 'not-allowed';
    } else {
        confirmTweetBtn.disabled = false;
        confirmTweetBtn.style.opacity = 1;
        confirmTweetBtn.style.cursor = 'pointer';
    }
}

// Helpers
function showLoading(show) {
    if (show) {
        loadingOverlay.classList.remove('hidden');
    } else {
        loadingOverlay.classList.add('hidden');
    }
}

function formatTime(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

let toastTimeout;
function showToast(message, type = 'success') {
    clearTimeout(toastTimeout);
    
    toastMessage.textContent = message;
    
    // Set icon & border color based on type
    toastIcon.className = 'fa-solid toast-icon';
    if (type === 'success') {
        toastIcon.classList.add('fa-circle-check', 'success');
        toast.style.borderLeftColor = 'var(--color-feature)';
    } else {
        toastIcon.classList.add('fa-circle-exclamation', 'error');
        toast.style.borderLeftColor = 'var(--color-breaking)';
    }
    
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('show'), 10);
    
    toastTimeout = setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.classList.add('hidden'), 300);
    }, 4000);
}

// Theme Management Logic
function loadSavedTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        themeIcon.className = 'fa-solid fa-sun';
    } else {
        document.body.classList.remove('light-theme');
        themeIcon.className = 'fa-solid fa-moon';
    }
}

function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');
    if (isLight) {
        localStorage.setItem('theme', 'light');
        themeIcon.className = 'fa-solid fa-sun';
        showToast('Switched to light mode.', 'success');
    } else {
        localStorage.setItem('theme', 'dark');
        themeIcon.className = 'fa-solid fa-moon';
        showToast('Switched to dark mode.', 'success');
    }
}

// Export to CSV Logic
function exportToCSV() {
    if (filteredNotes.length === 0) {
        showToast('No updates available to export.', 'error');
        return;
    }
    
    // Header row
    let csvContent = "Date,Category,Link,Update Description\n";
    
    filteredNotes.forEach(entry => {
        entry.updates.forEach(update => {
            const escapeCSV = (text) => `"${text.replace(/"/g, '""')}"`;
            
            const dateStr = escapeCSV(entry.date);
            const typeStr = escapeCSV(update.type);
            const linkStr = escapeCSV(entry.link || '');
            const textStr = escapeCSV(update.text);
            
            csvContent += `${dateStr},${typeStr},${linkStr},${textStr}\n`;
        });
    });
    
    try {
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `bigquery_release_notes_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showToast('Exported updates to CSV successfully!', 'success');
    } catch (err) {
        console.error('CSV export failed:', err);
        showToast('Failed to export CSV.', 'error');
    }
}

