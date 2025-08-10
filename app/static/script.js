// Static asset paths - defined once at the top for maintainability
const STATIC_ASSETS = {
    FLACCY_IMAGE: '/static/flaccy.png',
    BACKGROUND_IMAGE: '/static/bg.jpg',
    FALLBACK_IMAGE: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDgiIGhlaWdodD0iNDgiIHZpZXdCb3g9IjAgMCA0OCA0OCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3Qgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQ4IiBmaWxsPSJyZ2JhKDI1NSwgMjU1LCAyNTUsIDAuMSkiIHJ4PSI0Ii8+PC9zdmc+'
};

// Helper functions for consistent asset handling
function getAlbumArtSrc(albumArtUrl) {
    return albumArtUrl || STATIC_ASSETS.FLACCY_IMAGE;
}

function createImageElement(albumArtUrl, altText = "Album Art", className = "toast-album-art") {
    const src = getAlbumArtSrc(albumArtUrl);
    const isFlaccyImage = src === STATIC_ASSETS.FLACCY_IMAGE;
    
    if (isFlaccyImage) {
        return `<img src="${src}" alt="${altText}" class="${className}" style="width: 100%; height: 100%; object-fit: cover; object-position: center;" onerror="this.src='${STATIC_ASSETS.FALLBACK_IMAGE}'">`;
    }
    
    return `<img src="${src}" alt="${altText}" class="${className}" onerror="this.src='${STATIC_ASSETS.FALLBACK_IMAGE}'">`;
}

let eventSource = null;
const activeToasts = new Map();
const toastQueue = [];
let isProcessingQueue = false;

// --- Infinite Scroll Globals ---
let currentQuery = '';
let currentSearchType = 'track';
let currentOffset = 0;
let isLoading = false;
let noMoreResults = false;
const SEARCH_LIMIT = 28;
let displayedIds = new Set();

function processToastQueue() {
    if (isProcessingQueue || toastQueue.length === 0) return;
    
    isProcessingQueue = true;
    const { downloadId, trackInfo } = toastQueue.shift();
    
    createToast(downloadId, trackInfo);
    
    setTimeout(() => {
        isProcessingQueue = false;
        processToastQueue();
    }, 150);
}

function createToast(downloadId, trackInfo) {
    if (activeToasts.has(downloadId)) {
        return;
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = 'toast';

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(trackInfo.albumArtUrl)}
            <div class="toast-progress-overlay">0%</div>
        </div>
        <div class="toast-content">
            <div class="toast-track-title" title="${trackInfo.title}">${trackInfo.title}</div>
            <div class="toast-track-details" title="${trackInfo.artist} - ${trackInfo.album}">${trackInfo.artist} - ${trackInfo.album}</div>
            <div class="toast-step" aria-hidden="true"></div>
            <div class="toast-progress-bar-container">
                <div class="toast-progress-bar"></div>
            </div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        progress: 0,
        completed: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });
}

function updateToastProgress(downloadId, progress) {
    const toastData = activeToasts.get(downloadId);
    if (!toastData || toastData.completed) return;

    const { element } = toastData;
    const progressBar = element.querySelector('.toast-progress-bar');
    const progressOverlay = element.querySelector('.toast-progress-overlay');
    
    if (progressBar && progressOverlay) {
        progressBar.style.width = `${progress}%`;
        progressOverlay.textContent = `${Math.round(progress)}%`;
        
        toastData.progress = progress;

        if (progress >= 100 && !toastData.completed) {
            toastData.completed = true;
            toastData.completedAt = Date.now();
            progressOverlay.textContent = '✓';
            progressBar.classList.add('complete');
            
            setTimeout(() => {
                removeToast(downloadId);
            }, 2500);
        }
    }
}

function updateToastAlbumArt(downloadId, albumArtUrl) {
    const toastData = activeToasts.get(downloadId);
    if (!toastData) return;
    
    const albumArtImg = toastData.element.querySelector('.toast-album-art');
    if (albumArtImg && albumArtUrl) {
        const img = new Image();
        img.onload = function() {
            albumArtImg.src = albumArtUrl;
        };
        img.src = albumArtUrl;
    }
}

function removeToast(downloadId) {
    const toastData = activeToasts.get(downloadId);
    if (!toastData || toastData.isRemoving) return;

    toastData.isRemoving = true;
    
    const { element } = toastData;
    
    // Force the toast to animate out by removing show class
    element.classList.remove('show');
    
    
    const remove = () => {
        if (document.body.contains(element)) {
            element.remove();
        }
        activeToasts.delete(downloadId);
    };

    // Listen for transition end
    element.addEventListener('transitionend', remove, { once: true });
    
    // Shorter fallback timeout since your transition is 0.4s
    setTimeout(() => {
        remove();
    }, 500);
}

function showPlaylistLoadedToast(totalTracks) {
    const downloadId = 'playlist-download';
    if (activeToasts.has(downloadId)) {
        removeToast(downloadId);
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = 'toast';

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(null, "Album Art", "toast-album-art")}
        </div>
        <div class="toast-content">
            <div class="toast-track-title">Playlist Loaded</div>
            <div class="toast-track-details">${totalTracks} tracks ready to download.</div>
            <div class="toast-message">Click "Download Playlist" to start.</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        completed: false,
        isRemoving: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });

    // Auto-remove the "playlist loaded" toast after 10 seconds if user doesn't start download
    setTimeout(() => {
        const currentToastData = activeToasts.get(downloadId);
        // Only remove if it's still the "playlist loaded" state (title hasn't changed)
        if (currentToastData && !currentToastData.isRemoving) {
            const titleElement = currentToastData.element.querySelector('.toast-track-title');
            if (titleElement && titleElement.textContent === 'Playlist Loaded') {
                removeToast(downloadId);
            }
        }
    }, 5000);
}

function createPlaylistToast(totalTracks) {
    const downloadId = 'playlist-download';
    if (activeToasts.has(downloadId)) {
        // Update existing toast if it's already there
        const toastData = activeToasts.get(downloadId);
        const messageElement = toastData.element.querySelector('.toast-message');
        if (messageElement) {
            messageElement.textContent = `Queued ${totalTracks} tracks. Starting download...`;
        }
        return;
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = 'toast';

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(null, "Album Art", "toast-album-art")}
        </div>
        <div class="toast-content">
            <div class="toast-track-title">Playlist Download</div>
            <div class="toast-track-details">Preparing to download...</div>
            <div class="toast-message">Queued ${totalTracks} tracks. Starting download...</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        completed: false,
        isRemoving: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });
}

function removeAllToasts() {
    activeToasts.forEach((toastData, downloadId) => {
        removeToast(downloadId);
    });
}

function createErrorToast(message) {
    const toastId = `error-${Date.now()}`;
    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = 'toast error-toast';

    toast.innerHTML = `
        <div class="toast-content">
            <div class="toast-track-title">Error</div>
            <div class="toast-track-details">${message}</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(toastId, {
        element: toast,
        isRemoving: false
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });

    setTimeout(() => {
        removeToast(toastId);
    }, 5000);
}

function createSimpleToast(downloadId, trackInfo, message, type = 'info') {
    if (activeToasts.has(downloadId)) {
        return;
    }

    const toastContainer = document.getElementById('toast-queue-container');
    const toast = document.createElement('div');
    toast.id = `toast-${downloadId}`;
    toast.className = `toast ${type === 'error' ? 'error-toast' : ''}`;

    toast.innerHTML = `
        <div class="toast-album-art-container">
            ${createImageElement(trackInfo.albumArtUrl)}
        </div>
        <div class="toast-content">
            <div class="toast-track-title" title="${trackInfo.title}">${trackInfo.title}</div>
            <div class="toast-track-details" title="${trackInfo.artist} - ${trackInfo.album}">${trackInfo.artist} - ${trackInfo.album}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    activeToasts.set(downloadId, {
        element: toast,
        completed: type === 'success',
        isRemoving: false,
        createdAt: Date.now()
    });

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
    });
}

// Function to update simple toast
function updateSimpleToast(downloadId, message, type = 'info') {
    const toastData = activeToasts.get(downloadId);
    if (!toastData) return;

    const { element } = toastData;
    const messageElement = element.querySelector('.toast-message');
    const statusOverlay = element.querySelector('.toast-status-overlay');
    
    if (messageElement) {
        messageElement.textContent = message;
    }
    
    if (statusOverlay) {
        statusOverlay.textContent = type === 'success' ? '✓' : type === 'error' ? '✗' : '⏳';
    }

    element.classList.remove('error-toast', 'success-toast');
    if (type === 'error') {
        element.classList.add('error-toast');
    } else if (type === 'success') {
        element.classList.add('success-toast');
    }
    
    toastData.completed = type === 'success';
}

// Clean up any stuck toasts periodically
setInterval(() => {
    activeToasts.forEach((toastData, downloadId) => {
        const now = Date.now();
        
        // Don't auto-remove playlist download toast while it's active
        if (downloadId === 'playlist-download' && !toastData.completed) {
            return; // Skip cleanup for active playlist downloads
        }
        
        // Remove completed toasts after 3 seconds
        if (toastData.completed && toastData.completedAt && now - toastData.completedAt > 3000) {
            removeToast(downloadId);
        }
        // Remove any toast that's been around for more than 30 seconds (safety net)
        else if (toastData.createdAt && now - toastData.createdAt > 30000) {
            removeToast(downloadId);
        }
    });
}, 2000);

function showTab(tabName) {
    // Remove all existing toasts
    activeToasts.forEach((toastData, downloadId) => {
        removeToast(downloadId);
    });

    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => tab.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');

    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => button.classList.remove('active'));
    document.querySelector(`.tab-button[onclick="showTab('${tabName}')"]`).classList.add('active');
}

function logMessage(message, type = 'info') {
    const log = document.getElementById('status-log');
    if (!log) {
        console.log(`[${type}] ${message}`);
        return;
    }
    const timestamp = new Date().toLocaleTimeString();
    const p = document.createElement('p');
    p.innerHTML = `<span style="color: var(--text-muted-color)">[${timestamp}]</span> ${message}`;
    
    if (type === 'error') {
        p.classList.add('error');
    } else if (type === 'success') {
        p.classList.add('success');
    }
    
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
}

function displaySearchResults(results, append = false) {
    const resultsContainer = document.getElementById('search-results');
    if (!resultsContainer) return; // Guard if container not found

    const resultsContainerWrapper = resultsContainer.parentElement;

    if (!append) {
        resultsContainer.innerHTML = '';
        displayedIds.clear();
    }

    if (!results || results.length === 0) {
        if (!append) {
            resultsContainer.innerHTML = '<p>No results found.</p>';
        }
        noMoreResults = true;
        return;
    }

    const newResults = results.filter(item => !displayedIds.has(item.id));
    newResults.forEach(item => displayedIds.add(item.id));

    newResults.forEach(item => {
        const itemElement = document.createElement('div');
        itemElement.classList.add('search-result-item');

        let albumArt, title, artist, buttonText;

        if (currentSearchType === 'track') {
            albumArt = getAlbumArtSrc(item.image && item.image.small ? item.image.small : null);
            title = item.title;
            artist = item.performer ? item.performer.name : 'Unknown Artist';
            buttonText = 'Download';
        } else if (currentSearchType === 'album') {
            albumArt = getAlbumArtSrc(item.image && item.image.small ? item.image.small : null);
            title = item.title;
            artist = item.artist ? item.artist.name : 'Unknown Artist';
            buttonText = 'Download Album';
        }

        let metadataHTML = '';
        if (currentSearchType === 'track' && item.bit_depth && item.sample_rate) {
            metadataHTML = `
                <div class="metadata">
                    <span>${item.bit_depth} bit / ${item.sample_rate} kHz</span>
                    <span>${item.codec}</span>
                </div>
            `;
        } else if (currentSearchType === 'album' && item.quality) {
            metadataHTML = `
                <div class="metadata">
                    <span>${item.quality}</span>
                </div>
            `;
        }

        let previewButtonHTML = '';
        if (currentSearchType === 'track' && item.preview_url) {
            previewButtonHTML = `<button class="preview-btn" data-preview-url="${item.preview_url}">Preview</button>`;
        }

        itemElement.innerHTML = `
            <div class="album-art-container">
                <img src="${albumArt}" alt="Album Art" class="album-art" onerror="this.src='${STATIC_ASSETS.FALLBACK_IMAGE}'">
                <div class="overlay">
                    ${metadataHTML}
                    ${previewButtonHTML}
                    <button class="download-btn">${buttonText}</button>
                </div>
            </div>
            <div class="track-info">
                <p class="track-title">${title}</p>
                <p class="track-artist">${artist}</p>
            </div>
        `;
        itemElement.dataset.item = JSON.stringify(item);
        resultsContainer.appendChild(itemElement);
    });

}

function pollJobStatus(jobId) {
    const interval = setInterval(() => {
        fetch(`/jobs/${jobId}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }

                updateToastProgress(jobId, data.progress);

                if (data.status === 'succeeded' || data.status === 'failed' || data.status === 'canceled') {
                    clearInterval(interval);
                    // Close any SSE subscription for this job if present
                    try {
                        if (window.jobEventSources && window.jobEventSources.has(jobId)) {
                            const es = window.jobEventSources.get(jobId);
                            try { es.close(); } catch (e) {}
                            window.jobEventSources.delete(jobId);
                        }
                    } catch (e) {}

                    if (data.status === 'succeeded') {
                        // Use the stored safe filename (filename) rather than the original display name.
                        // The backend stores files as { name: orig_name, filename: safe_stored_name }.
                        const storedFilename = data.result && data.result.files && data.result.files[0] && data.result.files[0].filename;
                        if (storedFilename) {
                            // Redirect to the app's files endpoint which will authorize the request
                            // and instruct Nginx to serve the file via X-Accel-Redirect.
                            window.location.href = `/files/${encodeURIComponent(storedFilename)}`;
                        } else {
                            logMessage('Download succeeded but no stored filename found.', 'error');
                            createErrorToast('Download succeeded but file metadata is missing.');
                        }
                    } else if (data.status === 'failed') {
                        const toastData = activeToasts.get(jobId);
                        if (toastData) {
                            toastData.element.classList.add('error-toast');
                        }
                        logMessage(`Download failed: ${data.error}`, 'error');
                        createErrorToast(`Download failed: ${data.error}`);
                    }
                }
            })
            .catch(error => {
                clearInterval(interval);
                logMessage(`Error polling job status: ${error.message}`, 'error');
                createErrorToast(`Error polling job status: ${error.message}`);
            });
    }, 2000);
}

// Map of active EventSource objects per job id (to avoid duplicate subscriptions)
window.jobEventSources = window.jobEventSources || new Map();

function subscribeToJobEvents(jobId) {
    // Avoid double-subscription
    if (window.jobEventSources.has(jobId)) return;

    try {
        const es = new EventSource(`/jobs/${jobId}/events`);
        es.onmessage = (e) => {
    try {
        const payload = JSON.parse(e.data);
        const type = payload.type;

        // Primary: server-mapped progress (preferred). Backend now sends mapped progress for albums (0..90 during download,
        // then zipping moves to 90..95 and completion to 100). Use this when present.
        if (type === 'progress' && typeof payload.progress !== 'undefined') {
            updateToastProgress(jobId, payload.progress);
            // Optionally surface raw progress in tooltip if provided (helpful debugging info)
            if (typeof payload.raw_progress !== 'undefined') {
                const toastData = activeToasts.get(jobId);
                if (toastData) {
                    const detailsEl = toastData.element.querySelector('.toast-track-details');
                    if (detailsEl) {
                        detailsEl.title = `${detailsEl.title || ''} (raw: ${payload.raw_progress}%)`.trim();
                    }
                }
            }
        }

        // Status updates may contain step info; surface them as a hover/title on details
        else if (type === 'status' && payload.step) {
            const toastData = activeToasts.get(jobId);
            if (toastData) {
                const detailsEl = toastData.element.querySelector('.toast-track-details');
                const stepEl = toastData.element.querySelector('.toast-step');
                if (detailsEl) {
                    detailsEl.title = payload.step;
                }
                if (stepEl) {
                    stepEl.textContent = payload.step;
                }
            }
        }

        // File-level events: backend emits these as each artifact is moved into the artifacts dir.
        // Use them to show which file was last stored and as a reliable fallback when download-phase
        // progress events are not available. We compute two fallbacks:
        //  - downloadFallback (0..70) : shows per-track completion during download when a track file appears.
        //  - storingFallback (70..95) : shows progress through the storing/aggregation phase after move.
        else if (type === 'file' && (payload.filename || payload.name)) {
            const toastData = activeToasts.get(jobId);
            const fileDisplay = payload.name || payload.filename;
            if (toastData) {
                const stepEl = toastData.element.querySelector('.toast-step');
                const detailsEl = toastData.element.querySelector('.toast-track-details');
                if (stepEl) {
                    stepEl.textContent = `Saved: ${fileDisplay}`;
                }
                if (detailsEl) {
                    detailsEl.title = `Saved: ${fileDisplay}`;
                }
            }

            if (typeof payload.index !== 'undefined' && typeof payload.total !== 'undefined' && payload.total > 0) {
                const idx = Number(payload.index);
                const total = Number(payload.total);

                // Download-phase fallback: each completed track advances 0..70.
                // Use (index-1)/total so the download-phase increment happens when the file is saved,
                // representing the prior track being fully downloaded.
                const downloadFallback = Math.floor(((idx - 1) / total) * 70);
                // Storing-phase fallback: stored files advance 70..95.
                const storingFallback = 70 + Math.floor((idx / total) * 25);

                const toastData2 = activeToasts.get(jobId);
                const current = toastData2 ? toastData2.progress || 0 : 0;

                // Prefer the larger of the sensible fallbacks, but avoid regressions.
                const candidate = Math.max(downloadFallback, storingFallback);
                if (candidate > current) {
                    updateToastProgress(jobId, Math.min(candidate, 95));
                }
            }
        }

        // Checkpoints indicate logical milestones; server may also emit progress events, but keep visual nudges as a fallback.
        else if (type === 'checkpoint') {
            if (payload.message === 'download_complete') {
                updateToastProgress(jobId, 90);
            } else if (payload.message === 'zip_complete') {
                updateToastProgress(jobId, 95);
            }
        }

        // Zip failure should not fail the overall job but should alert the user
        else if (type === 'zip_failed') {
            createSimpleToast(jobId, { title: jobId, artist: '', album: '' }, 'Album ZIP creation failed; individual tracks are available', 'error');
        }

        // Final result may include files; use it to redirect to the primary artifact
        else if (type === 'result' && Array.isArray(payload.files)) {
            const storedFilename = payload.files[0] && payload.files[0].filename;
            if (storedFilename) {
                // close ES before redirecting
                try { es.close(); } catch (e) {}
                window.jobEventSources.delete(jobId);
                window.location.href = `/files/${encodeURIComponent(storedFilename)}`;
            }
        }

        // Error events from backend
        else if (type === 'error') {
            createErrorToast(payload.message || 'Download error');
        }

    } catch (err) {
        // ignore parse/handler errors per job event
        console.error('Job SSE handler error', err);
    }
};

        es.onerror = () => {
            // On persistent SSE errors close and remove so future attempts can re-subscribe
            try { es.close(); } catch (e) {}
            window.jobEventSources.delete(jobId);
        };

        window.jobEventSources.set(jobId, es);
    } catch (err) {
        console.error('Failed to subscribe to job events', err);
    }
}

function performSearch(append = false) {
    if (isLoading || (append && noMoreResults)) return;

    const service = document.body.dataset.service;
    if (!service) {
        logMessage('Error: No service specified on the page.', 'error');
        createErrorToast('Client error: No service specified.');
        return;
    }

    isLoading = true;
    const searchBtn = document.getElementById('search-btn');
    if (searchBtn) {
        searchBtn.classList.add('loading');
    }
    const loadingSpinner = document.getElementById('loading-spinner');
    if (loadingSpinner) {
        loadingSpinner.classList.remove('hidden');
    }

    if (!append) {
        currentOffset = 0;
        noMoreResults = false;
    }
    
    logMessage(`Searching for ${currentSearchType}: "${currentQuery}" (offset: ${currentOffset})...`, 'info');

    fetch('/api/search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
            query: currentQuery, 
            type: currentSearchType,
            limit: SEARCH_LIMIT,
            offset: currentOffset,
            service: service
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            logMessage(data.error, 'error');
            createErrorToast(data.error);
            noMoreResults = true;
        } else {
            displaySearchResults(data, append);
            currentOffset += data.length;
            if (data.length < SEARCH_LIMIT) {
                noMoreResults = true;
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        logMessage('Search failed.', 'error');
        createErrorToast('Search failed. Check console for details.');
        noMoreResults = true;
    })
    .finally(() => {
        isLoading = false;
        if (searchBtn) {
            searchBtn.classList.remove('loading');
        }
        const loadingSpinner = document.getElementById('loading-spinner');
        if (loadingSpinner) {
            loadingSpinner.classList.add('hidden');
        }
    });
}

function downloadTrack(track) {
    const service = document.body.dataset.service;
    if (!service) {
        logMessage('Error: No service specified on the page.', 'error');
        createErrorToast('Client error: No service specified.');
        return;
    }

    logMessage(`Queueing download: ${track.performer.name} - ${track.title}`, 'info');

    const trackInfo = {
        title: track.title,
        artist: track.performer.name,
        album: track.album.title,
        albumArtUrl: track.image.small
    };

    const source = {
        service: service,
        id: track.id,
        type: 'track'
    };

    fetch('/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            throw new Error(data.error);
        }
        const jobId = data.id;
        createToast(jobId, trackInfo);
        pollJobStatus(jobId);
        // Subscribe to server-sent events for real-time progress/status updates (best-effort)
        subscribeToJobEvents(jobId);
    })
    .catch(error => {
        logMessage(`Failed to queue download: ${error.message}`, 'error');
        createErrorToast(`Failed to queue download: ${error.message}`);
    });
}

async function downloadPlaylistInChunks(queries, service) {
    const totalTracks = queries.length;
    createPlaylistToast(totalTracks);

    for (let i = 0; i < totalTracks; i++) {
        const query = queries[i];
        logMessage(`Searching for track: ${query}`, 'info');
        
        try {
            const searchResponse = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query, type: 'track', limit: 1, service: service })
            });

            const searchData = await searchResponse.json();

            if (searchData.error || searchData.length === 0) {
                throw new Error(searchData.error || "Track not found");
            }

            const track = searchData[0];
            downloadTrack(track);

        } catch (error) {
            logMessage(`Failed to process playlist item "${query}": ${error.message}`, 'error');
            createErrorToast(`Failed to process playlist item "${query}": ${error.message}`);
        }
    }
}

async function downloadAlbum(album) {
    const service = document.body.dataset.service;
    if (!service) {
        logMessage('Error: No service specified on the page.', 'error');
        createErrorToast('Client error: No service specified.');
        return;
    }

    logMessage(`Queueing album download: ${album.artist.name} - ${album.title}`, 'info');

    const albumInfo = {
        title: album.title,
        artist: album.artist.name,
        album: album.title,
        albumArtUrl: album.image.small
    };

    const source = {
        service: service,
        id: album.id,
        type: 'album'
    };

    fetch('/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            throw new Error(data.error);
        }
        const jobId = data.id;
        createToast(jobId, albumInfo);
        pollJobStatus(jobId);
        // Subscribe to server-sent events for real-time progress/status updates (best-effort)
        subscribeToJobEvents(jobId);
    })
    .catch(error => {
        logMessage(`Failed to queue album download: ${error.message}`, 'error');
        createErrorToast(`Failed to queue album download: ${error.message}`);
    });
}

function cancelDownloads() {
    fetch('/api/cancel-downloads', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            logMessage('All downloads have been cancelled.', 'info');
        } else {
            logMessage('Failed to cancel downloads.', 'error');
        }
        
        // Move button visibility changes inside the promise
        const cancelBtn = document.getElementById('cancel-playlist-btn');
        const startBtn = document.getElementById('start-playlist-btn');
        
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (startBtn) startBtn.style.display = 'inline-block';
    })
    .catch(error => {
        console.error('Error:', error);
        logMessage('Failed to send cancel request.', 'error');
        
        // Also handle button visibility on error
        const cancelBtn = document.getElementById('cancel-playlist-btn');
        const startBtn = document.getElementById('start-playlist-btn');
        
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (startBtn) startBtn.style.display = 'inline-block';
    });

}

function initializeSearch() {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');

    if (searchBtn) {
        const originalContent = searchBtn.innerHTML;
        searchBtn.addEventListener('click', () => {
            const query = searchInput.value;
            if (!query) {
                logMessage('Please enter a search query.', 'error');
                return;
            }
            
            currentQuery = query;
            const checkedRadio = document.querySelector('input[name="search-type"]:checked');
            currentSearchType = checkedRadio ? checkedRadio.value : 'track';
            
            performSearch(false);
        });
    }

    // Add Enter key support for search
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                if (searchBtn) {
                    searchBtn.click();
                }
            }
        });

        searchInput.addEventListener('input', () => {
            if (searchInput.value.length > 0) {
                searchBtn.classList.remove('hidden');
            } else {
                searchBtn.classList.add('hidden');
            }
        });
    }
}

function selectService(service) {
    document.body.dataset.service = service;
    document.querySelectorAll('.service-option').forEach(opt => {
        opt.classList.toggle('active', opt.dataset.service === service);
    });
    // Clear search results when switching services
    const resultsContainer = document.getElementById('search-results');
    if (resultsContainer) {
        resultsContainer.innerHTML = '';
    }
    currentQuery = '';
    currentOffset = 0;
    noMoreResults = false;
}

document.addEventListener('DOMContentLoaded', () => {
    let scrollTimeout;
    window.addEventListener('scroll', () => {
        if (isLoading || noMoreResults || !currentQuery) return;

        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
            if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
                performSearch(true);
            }
        }, 100);
    });

    let toastContainer = document.getElementById('toast-queue-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-queue-container';
        document.body.appendChild(toastContainer);
    }

    const servicePicker = document.querySelector('.service-picker');
    if (servicePicker) {
        servicePicker.addEventListener('click', (e) => {
            const serviceOption = e.target.closest('.service-option');
            if (serviceOption) {
                selectService(serviceOption.dataset.service);
            }
        });
    }

    // Set initial service
    selectService('tidal');

    const resultsContainer = document.getElementById('search-results');
    if (resultsContainer) {
        resultsContainer.addEventListener('click', function(e) {
            if (e.target.classList.contains('download-btn')) {
                const item = e.target.closest('.search-result-item');
                if (!item) return;
                
                const itemData = JSON.parse(item.dataset.item);
                
                if (currentSearchType === 'track') {
                    downloadTrack(itemData);
                } else if (currentSearchType === 'album') {
                    downloadAlbum(itemData);
                }
            } else if (e.target.classList.contains('preview-btn')) {
                const item = e.target.closest('.search-result-item');
                if (!item) return;

                const itemData = JSON.parse(item.dataset.item);
                const service = document.body.dataset.service;

                fetch('/api/preview', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        service: service,
                        track_id: itemData.id
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        createErrorToast(data.error);
                    } else {
                        const audio = new Audio(data.preview_url);
                        audio.play();
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    createErrorToast('Failed to play preview. Check console for details.');
                });
            }
        });
    }

    const playlistInput = document.getElementById('playlist-input');
    const startPlaylistBtn = document.getElementById('start-playlist-btn');
    const cancelBtn = document.getElementById('cancel-playlist-btn');

    if (playlistInput) {
        playlistInput.addEventListener('change', () => {
            const file = playlistInput.files[0];
            if (!file) {
                return;
            }
            const reader = new FileReader();
            reader.onload = (e) => {
                const content = e.target.result;
                const lines = content.split('\n').filter(line => line.includes(' - '));
                showPlaylistLoadedToast(lines.length);
            };
            reader.readAsText(file);
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelDownloads);
    }

    if (startPlaylistBtn) {
        startPlaylistBtn.addEventListener('click', () => {
            const file = playlistInput.files[0];
            if (!file) {
                logMessage('Please select a playlist file.', 'error');
                return;
            }
            
            const reader = new FileReader();
            reader.onload = function(e) {
                const content = e.target.result;
                const lines = content.split('\n').filter(line => line.includes(' - '));
                logMessage(`Queueing ${lines.length} tracks from playlist...`, 'info');

                startPlaylistBtn.style.display = 'none';
                const cancelBtn = document.getElementById('cancel-playlist-btn');
                if (cancelBtn) {
                    cancelBtn.style.display = 'inline-block';
                }

                const service = document.body.dataset.service;
                if (!service) {
                    logMessage('Error: No service specified on the page.', 'error');
                    createErrorToast('Client error: No service specified.');
                    if (startPlaylistBtn) startPlaylistBtn.style.display = 'inline-block';
                    if (cancelBtn) cancelBtn.style.display = 'none';
                    return;
                }

                downloadPlaylistInChunks(lines, service);
            };
            reader.readAsText(file);
        });
    }

    // If the search input exists on the current page, initialize it.
    if (document.getElementById('search-input')) {
        initializeSearch();
    }
});

// Clean up on page unload
window.addEventListener('beforeunload', () => {
});
