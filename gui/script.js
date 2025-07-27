let totalDownloads = 0;
let completedDownloads = 0;
let eventSource = null;

function resetProgressBar() {
    totalDownloads = 0;
    completedDownloads = 0;
    const progressBar = document.getElementById('progress-bar');
    progressBar.style.width = '0%';
}

function updateProgressBar() {
    if (totalDownloads > 0) {
        const percent = (completedDownloads / totalDownloads) * 100;
        const progressBar = document.getElementById('progress-bar');
        progressBar.style.width = `${percent}%`;
    }
}

function showTab(tabName) {
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(tab => tab.classList.remove('active'));
    document.getElementById(tabName).classList.add('active');

    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => button.classList.remove('active'));
    document.querySelector(`.tab-button[onclick="showTab('${tabName}')"]`).classList.add('active');
}

function logMessage(message, type = 'info') {
    const log = document.getElementById('status-log');
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

function displaySearchResults(results) {
    const contentArea = document.querySelector('.content-area');
    let resultsContainer = document.getElementById('search-results');

    if (!resultsContainer) {
        resultsContainer = document.createElement('div');
        resultsContainer.id = 'search-results';
        resultsContainer.classList.add('section');
        contentArea.insertBefore(resultsContainer, contentArea.firstChild);
    }
    
    resultsContainer.innerHTML = '';

    if (!results || results.length === 0) {
        resultsContainer.innerHTML = '<p>No results found.</p>';
        return;
    }

    const searchType = document.querySelector('input[name="search-type"]:checked').value;

    results.forEach(item => {
        const itemElement = document.createElement('div');
        itemElement.classList.add('search-result-item');

        if (searchType === 'track') {
            const albumArt = item.album && item.album.image ? item.album.image.small : 'flaccy.png';
            const title = item.title;
            const artist = item.performer ? item.performer.name : 'Unknown Artist';

            itemElement.innerHTML = `
                <img src="${albumArt}" alt="Album Art" class="album-art">
                <div class="track-info">
                    <p class="track-title">${title}</p>
                    <p class="track-artist">${artist}</p>
                </div>
                <button class="download-btn">Download</button>
            `;

            itemElement.querySelector('.download-btn').addEventListener('click', () => {
                resetProgressBar();
                totalDownloads = 1;
                fetch('/api/download-song', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ track: item })
                })
                .then(response => response.json())
                .then(data => logMessage(data.error || data.message, data.error ? 'error' : 'info'))
                .catch(error => logMessage('Failed to start song download.', 'error'));
            });
        } else if (searchType === 'album') {
            const albumArt = item.image ? item.image.small : 'flaccy.png';
            const title = item.title;
            const artist = item.artist ? item.artist.name : 'Unknown Artist';

            itemElement.innerHTML = `
                <img src="${albumArt}" alt="Album Art" class="album-art">
                <div class="track-info">
                    <p class="track-title">${title}</p>
                    <p class="track-artist">${artist}</p>
                </div>
                <button class="download-btn">Download Album</button>
            `;

            itemElement.querySelector('.download-btn').addEventListener('click', async () => {
                resetProgressBar();
                logMessage(`Fetching tracks for album: ${item.title}...`, 'info');
                try {
                    const response = await fetch('/api/get-album-tracks', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ album_id: item.id })
                    });
                    const tracks = await response.json();

                    if (tracks.error) {
                        logMessage(tracks.error, 'error');
                        return;
                    }

                    totalDownloads = tracks.length;
                    logMessage(`Queueing ${totalDownloads} tracks for download...`, 'info');

                    for (const track of tracks) {
                        await new Promise(resolve => setTimeout(resolve, 200)); // Delay between each track download start
                        fetch('/api/download-song', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ track: track })
                        });
                    }
                } catch (error) {
                    logMessage('Failed to get album tracks.', 'error');
                }
            });
        }
        resultsContainer.appendChild(itemElement);
    });
}

function setupEventSource() {
    if (eventSource) {
        eventSource.close();
    }
    
    eventSource = new EventSource("/api/status");
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'progress') {
            completedDownloads++;
            updateProgressBar();
        } else if (data.type !== 'heartbeat') {
            logMessage(data.message, data.type);
        }
    };
    
    eventSource.onerror = function(err) {
        console.error("EventSource failed:", err);
        logMessage("Connection lost. Reconnecting...", "error");
        eventSource.close();
        // Reconnect after 5 seconds
        setTimeout(setupEventSource, 5000);
    };
    
    return eventSource;
}

document.addEventListener('DOMContentLoaded', () => {
    // --- EventSource for Server-Sent Events ---
    setupEventSource();

    // --- Playlist Tab ---
    const playlistInput = document.getElementById('playlist-input');
    const startPlaylistBtn = document.getElementById('start-playlist-btn');

    startPlaylistBtn.addEventListener('click', () => {
        const file = playlistInput.files[0];
        if (!file) {
            logMessage('Please select a playlist file.', 'error');
            return;
        }
        resetProgressBar();
        
        // To get totalDownloads for a playlist, we'd have to read the file client-side.
        const reader = new FileReader();
        reader.onload = function(e) {
            const content = e.target.result;
            const lines = content.split('\n').filter(line => line.includes(' - '));
            totalDownloads = lines.length;

            const formData = new FormData();
            formData.append('playlist', file);

            fetch('/api/download-playlist', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    logMessage(data.error, 'error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                logMessage('Failed to start playlist download.', 'error');
            });
        };
        reader.readAsText(file);
    });

    // --- Search Tab ---
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');

    searchBtn.addEventListener('click', () => {
        const query = searchInput.value;
        if (!query) {
            logMessage('Please enter a search query.', 'error');
            return;
        }
        
        const searchType = document.querySelector('input[name="search-type"]:checked').value;
        logMessage(`Searching for ${searchType}: "${query}"...`, 'info');

        fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query: query, type: searchType })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                logMessage(data.error, 'error');
            } else {
                displaySearchResults(data);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            logMessage('Search failed.', 'error');
        });
    });
});