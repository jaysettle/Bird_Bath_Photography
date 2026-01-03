// Mobile Web Interface JavaScript
// Auto-refresh intervals
const STATS_REFRESH = 60000; // 5 seconds
const IMAGES_REFRESH = 10000; // 10 seconds
const LOGS_REFRESH = 120000;
const MAX_AUTO_LOAD = 60;  // Stop infinite scroll after this many images // 3 seconds
// Gallery load limits - controlled by dropdown
function getGalleryLoadLimit() {
    const select = document.getElementById('gallery-load-select');
    return select ? parseInt(select.value) : 60;
}
const GALLERY_SCROLL_THRESHOLD = 250; // px from bottom to fetch more

// State
let isRestarting = false;
let autoScroll = true;
window.currentTab = 'gallery';
// console.log('[INIT] window.currentTab initialized to:', window.currentTab);
let autoRefreshPreview = true;
let previewInterval = null;

const galleryState = {
    currentDate: null,
    offset: 0,
    loading: false,
    allLoaded: false,
    totalLoaded: 0,
    initialized: false,
    allImages: [],  // Store all loaded images for navigation
    currentIndex: 0  // Current image index in modal
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
    
    // Initialize gallery as default tab
    if(typeof ensureGalleryInitialized==="function") ensureGalleryInitialized();
    if(typeof loadCalendar==="function") loadCalendar();
    if(typeof startScrollCheck==="function") startScrollCheck();
    
    // Set up auto-refresh (but not for images)
    // Disabled: setInterval(loadStats, STATS_REFRESH);
    // Disabled: setInterval(loadLogs, LOGS_REFRESH);
    
    // Update timestamp every second
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
    
    // Event listeners
    if (elements.restartBtn) elements.restartBtn.addEventListener('click', restartApp);
    if (elements.refreshImagesBtn) elements.refreshImagesBtn.addEventListener('click', refreshImages);
    document.querySelector('.close').addEventListener('click', closeModal);
    elements.modal.addEventListener('click', (e) => {
        if (e.target === elements.modal) closeModal();
    });

    // Swipe gesture support for modal
    elements.modalImg.addEventListener('touchstart', handleTouchStart, { passive: true });
    elements.modalImg.addEventListener('touchend', handleTouchEnd, { passive: true });

    // Mobile scroll detection
    document.addEventListener('touchmove', () => {
        if (window.currentTab === 'gallery') {
            setTimeout(handleGalleryScroll, 100);
        }
    }, { passive: true });

    // Keyboard navigation for modal
    document.addEventListener('keydown', (e) => {
        if (elements.modal.style.display === 'block') {
            if (e.key === 'ArrowLeft') navigateGallery(-1);
            else if (e.key === 'ArrowRight') navigateGallery(1);
            else if (e.key === 'Escape') closeModal();
        }
    });
    
    // Tab navigation
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Gallery load dropdown - refresh gallery when changed
    const galleryLoadSelect = document.getElementById('gallery-load-select');
    if (galleryLoadSelect) {
        galleryLoadSelect.addEventListener('change', () => {
            refreshGallery();
        });
    }

    if (elements.galleryRefreshBtn) {
        elements.galleryRefreshBtn.addEventListener('click', refreshGallery);
    }

    document.addEventListener('scroll', handleGalleryScroll, { passive: true, capture: true });
    window.addEventListener('scroll', handleGalleryScroll, { passive: true });
    
    
    // Check URL hash for direct tab navigation
    if (window.location.hash) {
        const tabName = window.location.hash.slice(1); // Remove #
        if (tabName === 'gallery' || tabName === 'dashboard') {
            switchTab(tabName);
        }
    }

    // Autoscroll toggle
    const autoscrollToggle = document.getElementById('autoscroll-toggle');
    autoscrollToggle?.addEventListener('change', (e) => {
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
        // console.error('Error loading stats:', error);
    }
}

// Load recent images
async function loadImages() {
    try {
        const response = await fetch('/api/images?limit=12');
        const images = await response.json();
        
        elements.imagesGrid.innerHTML = images.map(img => `
            <div class="image-item" onclick="openImage('${img.rel_path || img.filename}', '${img.timestamp}')">
                <img src="/api/thumbnail/${img.rel_path || img.filename}" alt="Bird capture" loading="lazy">
                <div class="image-timestamp">${formatTime(img.timestamp)}</div>
            </div>
        `).join('');
    } catch (error) {
        // console.error('Error loading images:', error);
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
    galleryState.allImages = [];
    galleryState.currentIndex = 0;

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
    // Setup intersection observer for infinite scroll
    setTimeout(setupGalleryObserver, 500);
}

function ensureDateSection(dateStr) {
    if (!elements.galleryGrid) return null;
    let section = elements.galleryGrid.querySelector(`[data-gallery-date="${dateStr}"]`);
    if (!section) {
        section = document.createElement('div');
        section.className = 'gallery-day';
        section.dataset.galleryDate = dateStr;

        const header = document.createElement('h3');
        header.innerHTML = `<span class="collapse-icon">▼</span> ${dateStr} <span class="day-photo-count"></span>`;
        header.addEventListener('click', () => {
            section.classList.toggle('collapsed');
        });
        section.appendChild(header);

        const grid = document.createElement('div');
        grid.className = 'gallery-day-grid';
        section.appendChild(grid);

        elements.galleryGrid.appendChild(section);
    }
    return section.querySelector('.gallery-day-grid');
}

// Update photo count for a day section
function updateDayPhotoCount(dateStr) {
    const section = document.querySelector(`[data-gallery-date="${dateStr}"]`);
    if (section) {
        const count = section.querySelectorAll('.image-item').length;
        const countSpan = section.querySelector('.day-photo-count');
        if (countSpan) {
            countSpan.textContent = `(${count} photos)`;
        }
    }
}

function appendGalleryImages(dateStr, images) {
    const grid = ensureDateSection(dateStr);
    if (!grid || !Array.isArray(images)) return;

    const fragment = document.createDocumentFragment();
    images.forEach(img => {
        // Store image in gallery state for navigation
        const imageData = {
            path: img.rel_path || img.filename,
            timestamp: img.timestamp,
            date: dateStr
        };
        galleryState.allImages.push(imageData);
        const imageIndex = galleryState.allImages.length - 1;

        const item = document.createElement('div');
        item.className = 'image-item';
        item.addEventListener('click', () => openGalleryImage(imageIndex));

        const imageEl = document.createElement('img');
        imageEl.src = `/api/thumbnail/${img.rel_path || img.filename}`;
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
    // Update the photo count for this day
    const daySection = grid.closest('.gallery-day');
    if (daySection) {
        const count = grid.querySelectorAll('.image-item').length;
        const countSpan = daySection.querySelector('.day-photo-count');
        if (countSpan) {
            countSpan.textContent = `(${count} photos)`;
        }
    }
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
        const limit = getGalleryLoadLimit();
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
        // console.log('[GALLERY] API response - has_more:', data.has_more, 'next_date:', data.next_date, 'date:', data.date);
        if (data.has_more) {
            galleryState.currentDate = data.date;
            galleryState.offset = data.offset;
            // console.log('[GALLERY] More images for this date, offset:', data.offset);
        } else if (data.next_date) {
            galleryState.currentDate = data.next_date;
            galleryState.offset = 0;
            // console.log('[GALLERY] Moving to next date:', data.next_date);
        } else {
            galleryState.currentDate = null;
            galleryState.offset = 0;
            galleryState.allLoaded = true;
            // console.log('[GALLERY] No more dates - allLoaded = true');
        }

        // Automatically continue if current date had no images but a next date exists
        if ((!data.images || data.images.length === 0) && data.next_date) {
            shouldAutoLoadNext = true;
        }
    } catch (error) {
        // console.error('Error loading gallery:', error);
        if (elements.galleryEmpty) {
            elements.galleryEmpty.textContent = 'Failed to load gallery.';
            elements.galleryEmpty.style.display = 'block';
        }
        if (initial) {
            galleryState.initialized = false;
        }
    } finally {
        galleryState.loading = false;
        updateLoadMoreButton();
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
        // console.error('Error refreshing images:', error);
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
        // console.error('Error loading logs:', error);
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

// Open image in modal (for non-gallery images like Recent Captures)
function openImage(imagePath, timestamp) {
    elements.modal.style.display = 'block';
    
    // Show loading indicator
    const loadingEl = document.getElementById('modal-loading');
    if (loadingEl) loadingEl.classList.add('visible');
    elements.modalImg.style.opacity = '0.3';
    
    // Hide loading when image loads
    elements.modalImg.onload = function() {
        if (loadingEl) loadingEl.classList.remove('visible');
        elements.modalImg.style.opacity = '1';
    };
    elements.modalImg.src = `/api/image-resized/${imagePath}`;
    elements.modalCaption.innerHTML = `Captured: ${formatTime(timestamp)}`;
    // Hide nav buttons for non-gallery images
    hideModalNav();
}

// Cascade loading state
const cascadeState = {
    sizes: [300, 600, 1200, 2400],
    currentSizeIndex: 0,
    currentImagePath: null,
    isLoading: false,
    aborted: false
};

// Progressive cascade loading for modal images
function startCascadeLoad(imagePath) {
    // Abort any previous cascade
    cascadeState.aborted = true;

    // Reset state for new image
    cascadeState.currentImagePath = imagePath;
    cascadeState.currentSizeIndex = 0;
    cascadeState.isLoading = false;
    cascadeState.aborted = false;

    console.log(`[CASCADE] Starting progressive load for: ${imagePath}`);

    // Load first (smallest) size immediately
    loadCascadeSize();
}

function loadCascadeSize() {
    if (cascadeState.aborted) {
        console.log('[CASCADE] Aborted - modal closed or new image');
        return;
    }

    const size = cascadeState.sizes[cascadeState.currentSizeIndex];
    const imagePath = cascadeState.currentImagePath;

    console.log(`[CASCADE] Loading size ${size}px (level ${cascadeState.currentSizeIndex + 1}/${cascadeState.sizes.length})`);

    // Create a new image to load in background
    const bgImg = new Image();

    bgImg.onload = function() {
        if (cascadeState.aborted || cascadeState.currentImagePath !== imagePath) {
            console.log('[CASCADE] Aborted during load - discarding');
            return;
        }

        // Swap in the higher quality image
        elements.modalImg.src = bgImg.src;
        console.log(`[CASCADE] Displayed size ${size}px`);

        // Update the "Showing" display
        updateCascadeMetadata(size);

        // Hide loading indicator after first image
        const loadingEl = document.getElementById('modal-loading');
        if (loadingEl) loadingEl.classList.remove('visible');
        elements.modalImg.style.opacity = '1';

        // Load next size if available
        cascadeState.currentSizeIndex++;
        if (cascadeState.currentSizeIndex < cascadeState.sizes.length) {
            // Small delay before loading next size
            setTimeout(loadCascadeSize, 100);
        } else {
            console.log('[CASCADE] Reached maximum quality');
        }
    };

    bgImg.onerror = function() {
        console.log(`[CASCADE] Error loading size ${size}px`);
    };

    bgImg.src = `/api/image-resized/${imagePath}?size=${size}`;
}

function updateCascadeMetadata(currentSize) {
    const metadataEl = document.querySelector('.metadata');
    if (metadataEl) {
        const maxSize = cascadeState.sizes[cascadeState.sizes.length - 1];
        const quality = currentSize >= maxSize ? 'Full' : `${currentSize}px`;
        metadataEl.textContent = `Showing: ${quality}`;
    }
}

function stopCascadeLoad() {
    console.log('[CASCADE] Stopping cascade load');
    cascadeState.aborted = true;
}

// Open gallery image with navigation support
function openGalleryImage(index) {
    if (index < 0 || index >= galleryState.allImages.length) return;

    galleryState.currentIndex = index;
    const img = galleryState.allImages[index];

    elements.modal.style.display = 'block';

    // Show loading indicator
    const loadingEl = document.getElementById('modal-loading');
    if (loadingEl) loadingEl.classList.add('visible');
    elements.modalImg.style.opacity = '0.3';

    // Start cascade loading
    startCascadeLoad(img.path);

    updateModalCaption(img);
    showModalNav();
    updateNavButtons();
}

// Update modal caption with image info and email button

// Track which images have been pushed to Instagram folder (per session)
const instaPushedImages = new Set();

// Handle InstaPush checkbox change
async function handleInstaPushChange(checkbox, imagePath) {
    console.log('[INSTAPUSH] Checkbox changed:', checkbox.checked, 'for image:', imagePath);

    if (!checkbox.checked) {
        console.log('[INSTAPUSH] Unchecked - no action needed');
        return;
    }

    // Check if already pushed this session
    if (instaPushedImages.has(imagePath)) {
        console.log('[INSTAPUSH] Already pushed this session, skipping');
        return;
    }

    // Mark as pushed to prevent duplicate copies
    instaPushedImages.add(imagePath);

    // Disable checkbox while copying
    checkbox.disabled = true;
    const label = checkbox.nextElementSibling;
    if (label) label.textContent = ' Copying...';

    try {
        console.log('[INSTAPUSH] Sending copy request for:', imagePath);
        const response = await fetch(`/api/instapush/${imagePath}`, {
            method: 'POST'
        });
        const result = await response.json();
        console.log('[INSTAPUSH] Response:', result);

        if (result.success) {
            const clearedMsg = result.cleared > 0 ? ` (cleared ${result.cleared} old)` : '';
            console.log('[INSTAPUSH] Success:', result.message, clearedMsg);
            if (label) label.textContent = ' Copied to InstaPush ✓';
            checkbox.disabled = true;  // Keep disabled after success
        } else {
            console.log('[INSTAPUSH] Failed:', result.error);
            if (label) label.textContent = ' Copy failed';
            checkbox.checked = false;
            checkbox.disabled = false;
            instaPushedImages.delete(imagePath);  // Allow retry
        }
    } catch (e) {
        console.log('[INSTAPUSH] Error:', e);
        if (label) label.textContent = ' Copy error';
        checkbox.checked = false;
        checkbox.disabled = false;
        instaPushedImages.delete(imagePath);  // Allow retry
    }
}

// Update modal caption with image info, metadata, and email button
async function updateModalCaption(img) {
    const emailBtn = `<button class="modal-email-btn" onclick="shareFullImage()">📧 Email Full Size</button>`;
    const alreadyPushed = instaPushedImages.has(img.path);
    const instaPushCheckbox = `
        <label class="instapush-label" style="margin-left: 10px; cursor: pointer;">
            <input type="checkbox" id="instapush-cb" ${alreadyPushed ? 'checked disabled' : ''}
                   onchange="handleInstaPushChange(this, '${img.path}')" style="cursor: pointer;">
            <span>${alreadyPushed ? ' Copied to InstaPush ✓' : ' Push to Instagram'}</span>
        </label>
    `;

    console.log('[METADATA] Fetching metadata for:', img.path);

    // Show loading state first
    elements.modalCaption.innerHTML = `
        <div class="modal-info">
            <span>Captured: ${formatTime(img.timestamp)}</span>
            <span class="metadata-loading">Loading metadata...</span>
            ${emailBtn}
            ${instaPushCheckbox}
        </div>
    `;

    // Fetch metadata
    try {
        const response = await fetch(`/api/image-metadata/${img.path}`);
        console.log('[METADATA] Response status:', response.status);
        if (response.ok) {
            const meta = await response.json();
            console.log('[METADATA] Received:', meta);
            elements.modalCaption.innerHTML = `
                <div class="modal-info">
                    <span>Captured: ${formatTime(img.timestamp)}</span>
                    <span class="metadata">Original: ${meta.original_width}x${meta.original_height} (${meta.file_size_mb}MB)</span>
                    <span class="metadata">Showing: ${meta.display_width}x${meta.display_height}</span>
                    ${emailBtn}
                    ${instaPushCheckbox}
                </div>
            `;
        } else {
            console.log('[METADATA] Error response:', response.status, response.statusText);
            elements.modalCaption.innerHTML = `
                <div class="modal-info">
                    <span>Captured: ${formatTime(img.timestamp)}</span>
                    <span class="metadata">Metadata unavailable</span>
                    ${emailBtn}
                    ${instaPushCheckbox}
                </div>
            `;
        }
    } catch (e) {
        console.log('[METADATA] Fetch error:', e);
        elements.modalCaption.innerHTML = `
            <div class="modal-info">
                <span>Captured: ${formatTime(img.timestamp)}</span>
                <span class="metadata">Metadata error</span>
                ${emailBtn}
                ${instaPushCheckbox}
            </div>
        `;
    }
}


// Show navigation buttons
function showModalNav() {
    let navContainer = document.querySelector('.modal-nav');
    if (!navContainer) {
        navContainer = document.createElement('div');
        navContainer.className = 'modal-nav';
        navContainer.innerHTML = `
            <button class="nav-btn nav-prev" onclick="navigateGallery(-1)">‹</button>
            <button class="nav-btn nav-next" onclick="navigateGallery(1)">›</button>
        `;
        elements.modal.querySelector('.modal-content').appendChild(navContainer);
    }
    navContainer.style.display = 'flex';
}

// Hide navigation buttons
function hideModalNav() {
    const navContainer = document.querySelector('.modal-nav');
    if (navContainer) {
        navContainer.style.display = 'none';
    }
}

// Update nav button states
function updateNavButtons() {
    const prevBtn = document.querySelector('.nav-prev');
    const nextBtn = document.querySelector('.nav-next');
    if (prevBtn) prevBtn.disabled = galleryState.currentIndex <= 0;
    if (nextBtn) nextBtn.disabled = galleryState.currentIndex >= galleryState.allImages.length - 1;
}

// Navigate gallery
function navigateGallery(direction) {
    const newIndex = galleryState.currentIndex + direction;
    if (newIndex >= 0 && newIndex < galleryState.allImages.length) {
        openGalleryImage(newIndex);
    }
}

// Email current image
async function emailCurrentImage() {
    const img = galleryState.allImages[galleryState.currentIndex];
    if (!img) return;

    const emailBtn = document.querySelector('.modal-email-btn');
    if (emailBtn) {
        emailBtn.disabled = true;
        emailBtn.textContent = 'Sending...';
    }

    try {
        const response = await fetch('/api/email-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_path: img.path })
        });
        const data = await response.json();

        if (data.success) {
            if (emailBtn) {
                emailBtn.textContent = '✓ Sent!';
                setTimeout(() => {
                    emailBtn.textContent = '📧 Email';
                    emailBtn.disabled = false;
                }, 2000);
            }
        } else {
            throw new Error(data.error || 'Email failed');
        }
    } catch (error) {
        alert('Failed to send email: ' + error.message);
        if (emailBtn) {
            emailBtn.textContent = '📧 Email';
            emailBtn.disabled = false;
        }
    }
}
async function shareFullImage() {
    console.log('[EMAIL] Share button clicked');
    const img = galleryState.allImages[galleryState.currentIndex];
    if (!img) {
        console.log('[EMAIL] No image found at current index');
        return;
    }
    console.log('[EMAIL] Sharing image:', img.path);
    const btn = document.querySelector('.modal-email-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading...'; }
    try {
        console.log('[EMAIL] Fetching full image from /api/image/' + img.path);
        const startTime = Date.now();
        const response = await fetch('/api/image/' + img.path);
        console.log('[EMAIL] Fetch response status:', response.status, 'time:', (Date.now() - startTime) + 'ms');
        if (!response.ok) {
            console.log('[EMAIL] Fetch failed:', response.status, response.statusText);
            alert('Failed to load image: ' + response.status);
            return;
        }
        const blob = await response.blob();
        console.log('[EMAIL] Blob received, size:', (blob.size / 1024 / 1024).toFixed(2) + 'MB');
        const filename = img.path.split('/').pop() || 'bird_photo.jpg';
        const file = new File([blob], filename, { type: blob.type });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
            console.log('[EMAIL] Using native share');
            await navigator.share({ files: [file], title: 'Bird Photo', text: 'Check out this bird photo!' });
        } else {
            console.log('[EMAIL] Native share not available, downloading');
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = filename;
            a.click();
            URL.revokeObjectURL(a.href);
            alert('Image downloaded. Please attach it to your email manually.');
        }
        console.log('[EMAIL] Share complete');
    } catch (err) {
        console.log('[EMAIL] Error:', err.name, err.message);
        if (err.name !== 'AbortError') {
            alert('Error sharing image: ' + err.message);
        }
    }
    if (btn) { btn.disabled = false; btn.textContent = '📧 Email Full Size'; }
}

// Close modal
function closeModal() {
    stopCascadeLoad();  // Stop any ongoing cascade loading
    elements.modal.style.display = 'none';
    hideModalNav();
}

// Handle swipe gestures on modal
let touchStartX = 0;
let touchEndX = 0;

function handleTouchStart(e) {
    touchStartX = e.changedTouches[0].screenX;
}

function handleTouchEnd(e) {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
}

function handleSwipe() {
    const swipeThreshold = 50;
    const diff = touchStartX - touchEndX;

    if (Math.abs(diff) > swipeThreshold) {
        if (diff > 0) {
            // Swipe left - next image
            navigateGallery(1);
        } else {
            // Swipe right - previous image
            navigateGallery(-1);
        }
    }
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
    window.currentTab = tabName;
    
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
    
    // Initialize gallery as default tab
    if(typeof ensureGalleryInitialized==="function") ensureGalleryInitialized();
    if(typeof loadCalendar==="function") loadCalendar();
    if(typeof startScrollCheck==="function") startScrollCheck();
        startPreviewRefresh();
    } else {
        stopPreviewRefresh();
    }

    if (tabName === 'gallery') {
        ensureGalleryInitialized();
    }
}


// Timer-based scroll check for infinite scroll (works on all browsers)
let scrollCheckInterval = null;

function startScrollCheck() {
    scrollCheckInterval = setInterval(() => {
        const galleryVisible = document.getElementById('gallery-tab').style.display !== 'none';
        if (!galleryVisible || galleryState.loading || galleryState.allLoaded ) return;

        const scrollTop = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
        const scrollHeight = Math.max(
            document.body.scrollHeight,
            document.documentElement.scrollHeight,
            document.body.offsetHeight,
            document.documentElement.offsetHeight
        );
        const clientHeight = window.innerHeight || document.documentElement.clientHeight;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

        if (distanceFromBottom < 600) {
            // console.log('[TIMER] Near bottom, loading more... distance:', distanceFromBottom);
            loadGallery();
        }
    }, 500);
    // console.log('[TIMER] Scroll check started');
}

function stopScrollCheck() {
    if (scrollCheckInterval) {
        clearInterval(scrollCheckInterval);
        scrollCheckInterval = null;
        // console.log('[TIMER] Scroll check stopped');
    }
}

function handleGalleryScroll() {
    const galleryVisible = document.getElementById('gallery-tab').style.display !== 'none';
        if (!galleryVisible || galleryState.loading || galleryState.allLoaded ) return;

    // Check if we're near the bottom of the page
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = document.documentElement.clientHeight;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    if (distanceFromBottom < 500) {
        // console.log('[SCROLL] Near bottom, loading more... distance:', distanceFromBottom);
        loadGallery();
    }
}


// Update Load More button state
function updateLoadMoreButton() {
    const btn = document.getElementById('load-more-btn');
    if (!btn) return;

    if (galleryState.allLoaded) {
        btn.textContent = 'No more photos';
        btn.disabled = true;
        btn.style.opacity = '0.5';
    } else if (galleryState.loading) {
        btn.textContent = 'Loading...';
        btn.disabled = true;
    } else {
        btn.textContent = 'Load More';
        btn.disabled = false;
        btn.style.opacity = '1';
    }
}

// Intersection Observer for reliable infinite scroll
let galleryObserver = null;

function setupGalleryObserver() {
    // console.log('[OBSERVER] Setting up gallery observer...');

    // Use existing trigger element from HTML
    const galleryLoadTrigger = document.getElementById('gallery-load-trigger');
    if (!galleryLoadTrigger) {
        // console.log('[OBSERVER] No trigger element found!');
        return;
    }

    // Disconnect old observer if exists
    if (galleryObserver) {
        galleryObserver.disconnect();
    }

    // Create new observer
    galleryObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // console.log('[OBSERVER] Trigger visible - tab:', window.currentTab, 'loading:', galleryState.loading, 'allLoaded:', galleryState.allLoaded);
                if (window.currentTab === 'gallery' && !galleryState.loading && !galleryState.allLoaded ) {
                    // console.log('[OBSERVER] Loading more...');
                    loadGallery();
                }
            }
        });
    }, {
        root: null,
        rootMargin: '400px',
        threshold: 0
    });

    galleryObserver.observe(galleryLoadTrigger);
    // console.log('[OBSERVER] Observer attached');
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
        // console.error('Error loading camera settings:', error);
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
            
            if (autoRefreshPreview && window.currentTab === 'camera') {
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

// Calendar state and functions
const calendarState = {
    currentMonth: new Date().getMonth(),
    currentYear: new Date().getFullYear(),
    photoCounts: {}
};

async function loadPhotoCountsByDate() {
    try {
        const response = await fetch('/api/photo-counts');
        const data = await response.json();
        if (data.success && data.counts) {
            calendarState.photoCounts = data.counts;
            renderCalendar();
        }
    } catch (error) {
        // console.error('Error loading photo counts:', error);
    }
}

function renderCalendar() {
    const calGrid = document.getElementById('calendar-grid');
    const monthYearSpan = document.getElementById('cal-month-year');
    if (!calGrid || !monthYearSpan) return;

    const months = ['January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'];
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    monthYearSpan.textContent = `${months[calendarState.currentMonth]} ${calendarState.currentYear}`;

    const firstDay = new Date(calendarState.currentYear, calendarState.currentMonth, 1).getDay();
    const daysInMonth = new Date(calendarState.currentYear, calendarState.currentMonth + 1, 0).getDate();
    const today = new Date();

    let html = days.map(d => `<div class="cal-day-header">${d}</div>`).join('');

    // Empty cells before first day
    for (let i = 0; i < firstDay; i++) {
        html += '<div class="cal-day empty"></div>';
    }

    // Days of month
    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${calendarState.currentYear}-${String(calendarState.currentMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const hasPhotos = calendarState.photoCounts[dateStr] > 0;
        const isToday = today.getDate() === day &&
                        today.getMonth() === calendarState.currentMonth &&
                        today.getFullYear() === calendarState.currentYear;

        let classes = 'cal-day';
        if (hasPhotos) classes += ' has-photos';
        if (isToday) classes += ' today';

        const count = calendarState.photoCounts[dateStr] || 0;
        html += `<div class="${classes}" data-date="${dateStr}" onclick="jumpToDate('${dateStr}')">
            <span class="day-num">${day}</span>
            ${count > 0 ? `<span class="bird-count">${count}</span>` : ''}
        </div>`;
    }

    calGrid.innerHTML = html;
}

function jumpToDate(dateStr) {
    if (!calendarState.photoCounts[dateStr]) return;

    // Reset gallery state but keep allLoaded false so we can continue to next days
    galleryState.currentDate = dateStr;
    galleryState.offset = 0;
    galleryState.loading = false;
    galleryState.allLoaded = false;  // Allow flowing to next days
    galleryState.totalLoaded = 0;
    galleryState.initialized = true;
    galleryState.allImages = [];
    galleryState.currentIndex = 0;

    // Clear existing gallery
    if (elements.galleryGrid) {
        elements.galleryGrid.innerHTML = '';
    }
    if (elements.galleryEmpty) {
        elements.galleryEmpty.textContent = 'Loading...';
        elements.galleryEmpty.style.display = 'block';
    }
    if (elements.galleryCount) {
        elements.galleryCount.textContent = '0 photos';
    }

    // Load from this date (will continue to next days on scroll)
    loadGallery({ initial: true });

    // Setup observer after load
    setTimeout(setupGalleryObserver, 500);

    // Scroll to gallery
    document.getElementById('gallery-grid')?.scrollIntoView({ behavior: 'smooth' });
}

function changeMonth(delta) {
    calendarState.currentMonth += delta;
    if (calendarState.currentMonth > 11) {
        calendarState.currentMonth = 0;
        calendarState.currentYear++;
    } else if (calendarState.currentMonth < 0) {
        calendarState.currentMonth = 11;
        calendarState.currentYear--;
    }
    renderCalendar();
}

// Collapse all toggle
let allCollapsed = false;
function toggleCollapseAll() {
    allCollapsed = !allCollapsed;
    document.querySelectorAll('.gallery-day').forEach(day => {
        if (allCollapsed) {
            day.classList.add('collapsed');
        } else {
            day.classList.remove('collapsed');
        }
    });
    const btn = document.getElementById('collapse-all-btn');
    if (btn) {
        btn.textContent = allCollapsed ? '▶ All' : '▼ All';
    }
}

// Initialize calendar controls
document.addEventListener('DOMContentLoaded', () => {
    const calPrev = document.getElementById('cal-prev');
    const calNext = document.getElementById('cal-next');
    const collapseAllBtn = document.getElementById('collapse-all-btn');

    if (calPrev) calPrev.addEventListener('click', () => changeMonth(-1));
    if (calNext) calNext.addEventListener('click', () => changeMonth(1));
    if (collapseAllBtn) collapseAllBtn.addEventListener('click', toggleCollapseAll);

    // Load calendar data when gallery tab is shown
    loadPhotoCountsByDate();
});


// Hamburger menu functionality
document.addEventListener('DOMContentLoaded', () => {
    const hamburgerBtn = document.getElementById('hamburger-btn');
    const settingsDropdown = document.getElementById('settings-dropdown');
    const restartAppMenu = document.getElementById('restart-app-menu');
    const clearCacheMenu = document.getElementById('clear-cache-menu');
    const toggleNotificationsMenu = document.getElementById('toggle-notifications-menu');
    const notificationsLabel = document.getElementById('notifications-label');

    // Toggle dropdown
    if (hamburgerBtn && settingsDropdown) {
        hamburgerBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            settingsDropdown.classList.toggle('hidden');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!settingsDropdown.contains(e.target) && e.target !== hamburgerBtn) {
                settingsDropdown.classList.add('hidden');
            }
        });
    }

    // Restart App from menu
    if (restartAppMenu) {
        restartAppMenu.addEventListener('click', async () => {
            if (confirm('Restart the Bird Detection application?')) {
                try {
                    const response = await fetch('/api/restart', { method: 'POST' });
                    const data = await response.json();
                    if (data.success) {
                        alert('Application is restarting...');
                    } else {
                        alert('Failed to restart: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    alert('Error restarting app: ' + error.message);
                }
            }
            settingsDropdown.classList.add('hidden');
        });
    }

    // Clear thumbnail cache
    if (clearCacheMenu) {
        clearCacheMenu.addEventListener('click', async () => {
            if (confirm('Clear all thumbnail cache? This will free up disk space.')) {
                try {
                    const response = await fetch('/api/clear-thumbnail-cache', { method: 'POST' });
                    const data = await response.json();
                    if (data.success) {
                        alert(`Cleared ${data.cleared || 0} cached thumbnails`);
                    } else {
                        alert('Failed to clear cache: ' + (data.error || 'Unknown error'));
                    }
                } catch (error) {
                    alert('Error clearing cache: ' + error.message);
                }
            }
            settingsDropdown.classList.add('hidden');
        });
    }

    // Toggle notifications
    if (toggleNotificationsMenu && notificationsLabel) {
        // Check current permission
        const updateNotificationLabel = () => {
            if ('Notification' in window) {
                if (Notification.permission === 'granted') {
                    notificationsLabel.textContent = 'Notifications Enabled';
                } else if (Notification.permission === 'denied') {
                    notificationsLabel.textContent = 'Notifications Blocked';
                } else {
                    notificationsLabel.textContent = 'Enable Notifications';
                }
            } else {
                notificationsLabel.textContent = 'Notifications Not Supported';
            }
        };
        updateNotificationLabel();

        toggleNotificationsMenu.addEventListener('click', async () => {
            if ('Notification' in window && Notification.permission === 'default') {
                const permission = await Notification.requestPermission();
                updateNotificationLabel();
            }
            settingsDropdown.classList.add('hidden');
        });
    }

    // SUPER DEBUG INFINITE SCROLL
    // console.log('[INIT] Setting up infinite scroll - window.currentTab is:', window.currentTab);

    // Log window.currentTab every 2 seconds regardless
    setInterval(() => {
        // console.log('[TAB-CHECK] window.currentTab =', window.currentTab, 'type:', typeof window.currentTab);
    }, 2000);

    let debugCounter = 0;
    setInterval(() => {
        debugCounter++;

        const pct = Math.round((window.scrollY + window.innerHeight) / document.body.scrollHeight * 100);

        // Always log current state
        // console.log('[SCROLL #' + debugCounter + '] tab=' + window.currentTab +
        //             ' loading=' + galleryState.loading +
        //             ' allLoaded=' + galleryState.allLoaded +
        //             ' pct=' + pct + '%');

        // Check if on gallery
        if (window.currentTab !== 'gallery') {
            return; // Silent skip
        }

        // console.log('[SCROLL] On gallery tab! Checking conditions...');

        if (galleryState.loading) {
            // console.log('[SCROLL] Skip - loading');
            return;
        }
        if (galleryState.allLoaded) {
            // console.log('[SCROLL] Skip - allLoaded');
            return;
        }

        if (pct > 70) {
            // console.log('[SCROLL] *** LOADING MORE *** pct=' + pct);
            loadGallery();
        } else {
            // console.log('[SCROLL] Not at 70% yet, pct=' + pct);
        }
    }, 1000);

    // console.log('[INIT] Infinite scroll started');
});
