// Mobile Web Interface JavaScript
// Auto-refresh intervals
const STATS_REFRESH = 5000; // 5 seconds
const IMAGES_REFRESH = 10000; // 10 seconds
const LOGS_REFRESH = 3000; // 3 seconds
const GALLERY_INITIAL_LIMIT = 30; // Initial load for most recent day
const GALLERY_PAGE_LIMIT = 20;    // Subsequent batches while scrolling
const GALLERY_SCROLL_THRESHOLD = 250; // px from bottom to fetch more

// State
let isRestarting = false;
let autoScroll = true;
let currentTab = 'dashboard';
let autoRefreshPreview = true;
let previewInterval = null;

const galleryState = {
    currentDate: null,
    offset: 0,
    loading: false,
    allLoaded: false,
    totalLoaded: 0,
    initialized: false
};

// DOM elements
const elements = {
    appStatus: document.getElementById('app-status'),
    restartBtn: document.getElementById('restart-btn'),
    refreshImagesBtn: document.getElementById('refresh-images-btn'),
    cpuStat: document.getElementById('cpu-stat'),
    memoryStat: document.getElementById('memory-stat'),
    diskStat: document.getElementById('disk-stat'),
    imagesStat: document.getElementById('images-stat'),
    driveStatus: document.getElementById('drive-status'),
    driveFolder: document.getElementById('drive-folder'),
    driveUploaded: document.getElementById('drive-uploaded'),
    imagesGrid: document.getElementById('images-grid'),
    galleryGrid: document.getElementById('gallery-grid'),
    galleryEmpty: document.getElementById('gallery-empty'),
    galleryCount: document.getElementById('gallery-count'),
    galleryRefreshBtn: document.getElementById('gallery-refresh-btn'),
    galleryTab: document.getElementById('gallery-tab'),
    logsContainer: document.getElementById('logs-container'),
    modal: document.getElementById('image-modal'),
    modalImg: document.getElementById('modal-image'),
    modalCaption: document.getElementById('modal-caption')
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadImages();
    loadLogs();
    loadCameraSettings();
    
    // Set up auto-refresh (but not for images)
    setInterval(loadStats, STATS_REFRESH);
    setInterval(loadLogs, LOGS_REFRESH);
    
    // Update timestamp every second
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
    
    // Event listeners
    elements.restartBtn.addEventListener('click', restartApp);
    elements.refreshImagesBtn.addEventListener('click', refreshImages);
    document.querySelector('.close').addEventListener('click', closeModal);
    elements.modal.addEventListener('click', (e) => {
        if (e.target === elements.modal) closeModal();
    });
    
    // Tab navigation
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    if (elements.galleryRefreshBtn) {
        elements.galleryRefreshBtn.addEventListener('click', refreshGallery);
    }

    window.addEventListener('scroll', handleGalleryScroll, { passive: true });
    
    // Autoscroll toggle
    const autoscrollToggle = document.getElementById('autoscroll-toggle');
    autoscrollToggle.addEventListener('change', (e) => {
        autoScroll = e.target.checked;
    });
    
    // Camera settings
    setupCameraSettings();
    
    // Camera preview
    setupCameraPreview();
});

// Load statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        // Update system stats
        elements.cpuStat.textContent = `${data.system.cpu_percent.toFixed(1)}%`;
        elements.memoryStat.textContent = `${data.system.memory_percent.toFixed(1)}%`;
        elements.diskStat.textContent = `${data.system.disk_percent.toFixed(1)}%`;
        elements.imagesStat.textContent = data.system.total_images.toLocaleString();
        
        // Update drive stats
        elements.driveStatus.textContent = data.drive.enabled ? 'Enabled' : 'Disabled';
        elements.driveStatus.style.color = data.drive.enabled ? 'var(--success)' : 'var(--danger)';
        elements.driveFolder.textContent = data.drive.folder_name;
        elements.driveUploaded.textContent = data.drive.uploaded_count.toLocaleString();
        
        // Update app status
        updateAppStatus(data.app_running);
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Load recent images
async function loadImages() {
    try {
        const response = await fetch('/api/images?limit=12');
        const images = await response.json();
        
        elements.imagesGrid.innerHTML = images.map(img => `
            <div class="image-item" onclick="openImage('${img.rel_path || img.filename}', '${img.timestamp}')">
                <img src="/api/image/${img.rel_path || img.filename}" alt="Bird capture" loading="lazy">
                <div class="image-timestamp">${formatTime(img.timestamp)}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading images:', error);
    }
}

// Reset gallery state and UI
function resetGalleryState() {
    galleryState.currentDate = null;
    galleryState.offset = 0;
    galleryState.loading = false;
    galleryState.allLoaded = false;
    galleryState.totalLoaded = 0;
    galleryState.initialized = false;

    if (elements.galleryGrid) {
        elements.galleryGrid.innerHTML = '';
    }
    if (elements.galleryEmpty) {
        elements.galleryEmpty.textContent = 'Loading gallery...';
        elements.galleryEmpty.style.display = 'block';
    }
    if (elements.galleryCount) {
        elements.galleryCount.textContent = '0 photos';
    }
}

function ensureGalleryInitialized() {
    if (!galleryState.initialized) {
        resetGalleryState();
        loadGallery({ initial: true });
        galleryState.initialized = true;
    }
}

function ensureDateSection(dateStr) {
    if (!elements.galleryGrid) return null;
    let section = elements.galleryGrid.querySelector(`[data-gallery-date="${dateStr}"]`);
    if (!section) {
        section = document.createElement('div');
        section.className = 'gallery-day';
        section.dataset.galleryDate = dateStr;

        const header = document.createElement('h3');
        header.textContent = dateStr;
        section.appendChild(header);

        const grid = document.createElement('div');
        grid.className = 'gallery-day-grid';
        section.appendChild(grid);

        elements.galleryGrid.appendChild(section);
    }
    return section.querySelector('.gallery-day-grid');
}

function appendGalleryImages(dateStr, images) {
    const grid = ensureDateSection(dateStr);
    if (!grid || !Array.isArray(images)) return;

    const fragment = document.createDocumentFragment();
    images.forEach(img => {
        const item = document.createElement('div');
        item.className = 'image-item';
        item.addEventListener('click', () => openImage(img.rel_path || img.filename, img.timestamp));

        const imageEl = document.createElement('img');
        imageEl.src = `/api/image/${img.rel_path || img.filename}`;
        imageEl.alt = 'Bird capture';
        imageEl.loading = 'lazy';

        const ts = document.createElement('div');
        ts.className = 'image-timestamp';
        ts.textContent = formatTime(img.timestamp);

        item.appendChild(imageEl);
        item.appendChild(ts);
        fragment.appendChild(item);
    });

    grid.appendChild(fragment);
}

async function loadGallery({ initial = false } = {}) {
    if (!elements.galleryGrid || galleryState.loading || galleryState.allLoaded) return;

    galleryState.loading = true;

    if (elements.galleryEmpty) {
        elements.galleryEmpty.style.display = 'block';
    }

    let shouldAutoLoadNext = false;

    try {
        const params = new URLSearchParams();
        const limit = initial ? GALLERY_INITIAL_LIMIT : GALLERY_PAGE_LIMIT;
        params.set('limit', limit);

        if (galleryState.currentDate) {
            params.set('date', galleryState.currentDate);
        }
        if (!initial && galleryState.offset) {
            params.set('offset', galleryState.offset);
        }

        const response = await fetch(`/api/gallery?${params.toString()}`);
        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Gallery request failed');
        }

        if (!data.date) {
            galleryState.allLoaded = true;
            if (elements.galleryEmpty) {
                elements.galleryEmpty.textContent = 'No photos captured yet.';
            }
            return;
        }

        if (Array.isArray(data.images) && data.images.length > 0) {
            if (elements.galleryEmpty) {
                elements.galleryEmpty.style.display = 'none';
            }
            appendGalleryImages(data.date, data.images);
            galleryState.totalLoaded += data.images.length;
            if (elements.galleryCount) {
                const label = galleryState.totalLoaded === 1 ? 'photo' : 'photos';
                elements.galleryCount.textContent = `${galleryState.totalLoaded} ${label}`;
            }
        } else if (initial) {
            if (elements.galleryEmpty) {
                elements.galleryEmpty.textContent = 'No photos captured for the latest day.';
            }
        }

        // Prepare state for next fetch
        if (data.has_more) {
            galleryState.currentDate = data.date;
            galleryState.offset = data.offset;
        } else if (data.next_date) {
            galleryState.currentDate = data.next_date;
            galleryState.offset = 0;
        } else {
            galleryState.currentDate = null;
            galleryState.offset = 0;
            galleryState.allLoaded = true;
        }

        // Automatically continue if current date had no images but a next date exists
        if ((!data.images || data.images.length === 0) && data.next_date) {
            shouldAutoLoadNext = true;
        }
    } catch (error) {
        console.error('Error loading gallery:', error);
        if (elements.galleryEmpty) {
            elements.galleryEmpty.textContent = 'Failed to load gallery.';
            elements.galleryEmpty.style.display = 'block';
        }
        if (initial) {
            galleryState.initialized = false;
        }
    } finally {
        galleryState.loading = false;
        if (shouldAutoLoadNext) {
            loadGallery();
        }
    }
}

// Manual refresh for gallery
async function refreshGallery() {
    if (!elements.galleryRefreshBtn) return;

    elements.galleryRefreshBtn.classList.add('loading');
    elements.galleryRefreshBtn.disabled = true;

    resetGalleryState();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    ensureGalleryInitialized();

    setTimeout(() => {
        elements.galleryRefreshBtn.classList.remove('loading');
        elements.galleryRefreshBtn.disabled = false;
    }, 400);
}

// Manual refresh for Recent Captures
async function refreshImages() {
    if (!elements.refreshImagesBtn) return;
    
    // Add loading state
    elements.refreshImagesBtn.classList.add('loading');
    elements.refreshImagesBtn.disabled = true;
    
    try {
        await loadImages();
        
        // Show success feedback briefly
        setTimeout(() => {
            elements.refreshImagesBtn.classList.remove('loading');
            elements.refreshImagesBtn.disabled = false;
        }, 500);
    } catch (error) {
        console.error('Error refreshing images:', error);
        elements.refreshImagesBtn.classList.remove('loading');
        elements.refreshImagesBtn.disabled = false;
    }
}

// Load recent logs
async function loadLogs() {
    try {
        const response = await fetch('/api/logs');
        const data = await response.json();
        
        if (data.success && data.logs.length > 0) {
            elements.logsContainer.innerHTML = data.logs
                .slice(-20) // Last 20 lines
                .map(log => {
                    let className = 'log-entry';
                    if (log.includes('ERROR')) className += ' error';
                    else if (log.includes('WARNING')) className += ' warning';
                    else if (log.includes('INFO')) className += ' info';
                    
                    return `<div class="${className}">${escapeHtml(log)}</div>`;
                })
                .join('');
            
            // Auto-scroll to bottom if enabled
            if (autoScroll) {
                elements.logsContainer.scrollTop = elements.logsContainer.scrollHeight;
            }
        }
    } catch (error) {
        console.error('Error loading logs:', error);
    }
}

// Restart application
async function restartApp() {
    if (isRestarting) return;
    
    if (!confirm('Restart the Bird Detection application?')) return;
    
    isRestarting = true;
    elements.restartBtn.classList.add('loading');
    elements.restartBtn.innerHTML = '<span class="spinner"></span> Restarting...';
    
    try {
        const response = await fetch('/api/restart', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            // Show appropriate message based on watchdog management
            const message = data.watchdog_managed ? 
                'App stopped - watchdog restarting...' : 
                'App restarted manually';
                
            elements.restartBtn.innerHTML = `<span class="spinner"></span> ${message}`;
            
            // Wait a bit for the app to restart
            setTimeout(() => {
                loadStats();
                isRestarting = false;
                elements.restartBtn.classList.remove('loading');
                elements.restartBtn.innerHTML = `
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                    </svg>
                    Restart App
                `;
            }, data.watchdog_managed ? 6000 : 4000); // Wait longer for watchdog restarts
        } else {
            throw new Error(data.error || 'Restart failed');
        }
    } catch (error) {
        alert('Failed to restart: ' + error.message);
        isRestarting = false;
        elements.restartBtn.classList.remove('loading');
        elements.restartBtn.innerHTML = `
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
            </svg>
            Restart App
        `;
    }
}

// Update app status indicator
function updateAppStatus(isRunning) {
    if (isRunning) {
        elements.appStatus.classList.add('online');
        elements.appStatus.classList.remove('offline');
        elements.appStatus.querySelector('.status-text').textContent = 'Online';
    } else {
        elements.appStatus.classList.remove('online');
        elements.appStatus.classList.add('offline');
        elements.appStatus.querySelector('.status-text').textContent = 'Offline';
    }
}

// Open image in modal
function openImage(imagePath, timestamp) {
    elements.modal.style.display = 'block';
    elements.modalImg.src = `/api/image/${imagePath}`;
    elements.modalCaption.textContent = `Captured: ${formatTime(timestamp)}`;
}

// Close modal
function closeModal() {
    elements.modal.style.display = 'none';
}

// Utility functions
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    // Less than 1 minute
    if (diff < 60000) return 'Just now';
    
    // Less than 1 hour
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    
    // Less than 24 hours
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    
    // Default to date/time
    return date.toLocaleString('en-US', { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Tab switching
function switchTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `${tabName}-tab`);
    });
    
    // Load camera settings when switching to camera tab
    if (tabName === 'camera') {
        loadCameraSettings();
        startPreviewRefresh();
    } else {
        stopPreviewRefresh();
    }

    if (tabName === 'gallery') {
        ensureGalleryInitialized();
    }
}

function handleGalleryScroll() {
    if (currentTab !== 'gallery' || galleryState.loading || galleryState.allLoaded) return;

    const scrollPosition = window.innerHeight + window.scrollY;
    const triggerPoint = document.body.offsetHeight - GALLERY_SCROLL_THRESHOLD;

    if (scrollPosition >= triggerPoint) {
        loadGallery();
    }
}

// Load camera settings
async function loadCameraSettings() {
    try {
        const response = await fetch('/api/camera/settings');
        const data = await response.json();
        
        if (data.success && data.settings) {
            const settings = data.settings;
            
            // Update UI with current settings
            Object.entries(settings).forEach(([key, value]) => {
                const input = document.getElementById(key);
                const valueSpan = document.getElementById(`${key}-value`);
                
                if (input && valueSpan) {
                    input.value = value;
                    valueSpan.textContent = value;
                }
            });
        }
    } catch (error) {
        console.error('Error loading camera settings:', error);
    }
}

// Setup camera settings event handlers
function setupCameraSettings() {
    // Range sliders - update value display
    ['brightness', 'contrast', 'saturation', 'sharpness', 'exposure_compensation', 'threshold', 'min_area'].forEach(setting => {
        const input = document.getElementById(setting);
        const valueSpan = document.getElementById(`${setting}-value`);
        
        if (input && valueSpan) {
            input.addEventListener('input', (e) => {
                valueSpan.textContent = e.target.value;
            });
        }
    });
    
    // Save settings button
    const saveBtn = document.getElementById('save-settings-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveCameraSettings);
    }
    
    // Reset settings button
    const resetBtn = document.getElementById('reset-settings-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetCameraSettings);
    }
}

// Save camera settings
async function saveCameraSettings() {
    const saveBtn = document.getElementById('save-settings-btn');
    if (!saveBtn) return;
    
    saveBtn.classList.add('loading');
    saveBtn.innerHTML = '<span class="spinner"></span> Saving...';
    
    try {
        // Collect all settings
        const settings = {};
        ['brightness', 'contrast', 'saturation', 'sharpness', 'exposure_compensation', 'iso', 'threshold', 'min_area'].forEach(setting => {
            const input = document.getElementById(setting);
            if (input) {
                settings[setting] = parseInt(input.value);
            }
        });
        
        const response = await fetch('/api/camera/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success feedback
            saveBtn.style.backgroundColor = 'var(--success)';
            saveBtn.innerHTML = '✓ Saved';
            
            setTimeout(() => {
                saveBtn.style.backgroundColor = '';
                saveBtn.innerHTML = `
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                        <polyline points="17,21 17,13 7,13 7,21"/>
                        <polyline points="7,3 7,8 15,8"/>
                    </svg>
                    Save Settings
                `;
            }, 2000);
        } else {
            throw new Error(data.error || 'Save failed');
        }
    } catch (error) {
        alert('Failed to save settings: ' + error.message);
    } finally {
        saveBtn.classList.remove('loading');
    }
}

// Reset camera settings to defaults
async function resetCameraSettings() {
    if (!confirm('Reset all camera settings to defaults?')) return;
    
    const defaults = {
        brightness: 0,
        contrast: 0,
        saturation: 0,
        sharpness: 0,
        exposure_compensation: 0,
        iso: 0,
        threshold: 50,
        min_area: 500
    };
    
    // Update UI
    Object.entries(defaults).forEach(([key, value]) => {
        const input = document.getElementById(key);
        const valueSpan = document.getElementById(`${key}-value`);
        
        if (input && valueSpan) {
            input.value = value;
            valueSpan.textContent = value;
        }
    });
    
    // Save the defaults
    await saveCameraSettings();
}

// Camera preview functions
function setupCameraPreview() {
    const refreshBtn = document.getElementById('refresh-preview-btn');
    const autoToggle = document.getElementById('auto-refresh-toggle');
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            refreshPreview();
        });
    }
    
    if (autoToggle) {
        autoToggle.addEventListener('click', () => {
            autoRefreshPreview = !autoRefreshPreview;
            autoToggle.classList.toggle('active', autoRefreshPreview);
            
            if (autoRefreshPreview && currentTab === 'camera') {
                startPreviewRefresh();
            } else {
                stopPreviewRefresh();
            }
        });
    }
}

function refreshPreview() {
    const previewImg = document.getElementById('camera-preview');
    const timestampSpan = document.getElementById('preview-timestamp');
    
    if (previewImg) {
        // Add cache-busting parameter to force refresh
        const timestamp = new Date().getTime();
        previewImg.src = `/api/camera/preview?t=${timestamp}`;
        
        previewImg.onload = () => {
            if (timestampSpan) {
                timestampSpan.textContent = formatTime(new Date().toISOString());
            }
        };
        
        previewImg.onerror = () => {
            if (timestampSpan) {
                timestampSpan.textContent = 'Preview unavailable';
            }
        };
    }
}

function startPreviewRefresh() {
    if (previewInterval) {
        clearInterval(previewInterval);
    }
    
    if (autoRefreshPreview) {
        // Refresh immediately
        refreshPreview();
        
        // Then refresh every 3 seconds
        previewInterval = setInterval(refreshPreview, 3000);
    }
}

function stopPreviewRefresh() {
    if (previewInterval) {
        clearInterval(previewInterval);
        previewInterval = null;
    }
}

// Update real-time timestamp
function updateTimestamp() {
    const timestampEl = document.getElementById('current-time');
    if (timestampEl) {
        const now = new Date();
        const timeString = now.toLocaleTimeString('en-US', { 
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        timestampEl.textContent = timeString;
    }
}
