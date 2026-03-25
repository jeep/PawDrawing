/* PawLibrary — Library Management JavaScript */
(function() {
    'use strict';

    // ── Utility ───────────────────────────────────────────────────────

    let searchTimeout = null;

    function debounce(fn, delay) {
        return function(...args) {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    // ── Toast Notifications ───────────────────────────────────────────

    function showToast(message, type, duration) {
        type = type || 'info';
        duration = duration || 4000;
        var container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        var toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(function() {
            toast.classList.add('toast-fade');
            setTimeout(function() { toast.remove(); }, 300);
        }, duration);
    }

    // ── Fetch with Timeout + Retry ────────────────────────────────────

    var FETCH_TIMEOUT = 15000;
    var MAX_RETRIES = 2;

    function fetchWithTimeout(url, opts, timeoutMs) {
        timeoutMs = timeoutMs || FETCH_TIMEOUT;
        var controller = new AbortController();
        opts = opts || {};
        opts.signal = controller.signal;
        var timer = setTimeout(function() { controller.abort(); }, timeoutMs);
        return fetch(url, opts).finally(function() { clearTimeout(timer); });
    }

    function apiPost(url, body, retries) {
        retries = (retries === undefined) ? MAX_RETRIES : retries;
        return fetchWithTimeout(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        }).then(function(r) {
            if (r.status === 429) {
                if (retries > 0) {
                    showToast('Rate limit reached — retrying shortly\u2026', 'warning', 3000);
                    return new Promise(function(resolve) {
                        setTimeout(function() { resolve(apiPost(url, body, retries - 1)); }, 2000);
                    });
                }
            }
            return r.json();
        }).catch(function(err) {
            if (err.name === 'AbortError' && retries > 0) {
                showToast('Request timed out — retrying\u2026', 'warning', 3000);
                return apiPost(url, body, retries - 1);
            }
            throw err;
        });
    }

    function apiGet(url, retries) {
        retries = (retries === undefined) ? MAX_RETRIES : retries;
        return fetchWithTimeout(url).then(function(r) {
            if (r.status === 429) {
                if (retries > 0) {
                    showToast('Rate limit reached — retrying shortly\u2026', 'warning', 3000);
                    return new Promise(function(resolve) {
                        setTimeout(function() { resolve(apiGet(url, retries - 1)); }, 2000);
                    });
                }
            }
            return r.json();
        }).catch(function(err) {
            if (err.name === 'AbortError' && retries > 0) {
                showToast('Request timed out — retrying\u2026', 'warning', 3000);
                return apiGet(url, retries - 1);
            }
            throw err;
        });
    }

    // ── Offline Queue (§12 Q2) ────────────────────────────────────────

    var QUEUE_KEY = 'pawlibrary_offline_queue';
    var offlineBanner = null;

    function getQueue() {
        try {
            return JSON.parse(localStorage.getItem(QUEUE_KEY)) || [];
        } catch (e) { return []; }
    }

    function saveQueue(q) {
        localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
        updateOfflineBanner();
    }

    function enqueueOperation(op) {
        var q = getQueue();
        op.queued_at = new Date().toISOString();
        q.push(op);
        saveQueue(q);
    }

    function updateOfflineBanner() {
        var q = getQueue();
        if (!offlineBanner) {
            offlineBanner = document.getElementById('offline-banner');
        }
        var offlineText = document.getElementById('offline-text');
        if (offlineBanner && offlineText) {
            if (q.length > 0) {
                offlineText.textContent = '\u26a0 Offline mode: ' + q.length + ' operation(s) queued. Track manually as backup.';
                offlineBanner.classList.remove('hidden');
            } else {
                offlineBanner.classList.add('hidden');
            }
        }
    }

    function syncQueue() {
        var q = getQueue();
        if (q.length === 0) return;

        var op = q[0];
        apiPost(op.url, op.body)
            .then(function(data) {
                if (!data.error) {
                    q.shift();
                    saveQueue(q);
                    if (q.length > 0) {
                        setTimeout(syncQueue, 1500);
                    }
                }
            })
            .catch(function() {
                // Still offline, try again later
            });
    }

    // Try syncing when we come online
    window.addEventListener('online', syncQueue);
    // Initial banner update
    document.addEventListener('DOMContentLoaded', function() {
        updateOfflineBanner();
        syncQueue();

        // Offline retry button
        var retryBtn = document.getElementById('offline-retry-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', function() {
                syncQueue();
            });
        }

        // Catalog refresh loading indicator
        var refreshForm = document.getElementById('refresh-catalog-form');
        if (refreshForm) {
            refreshForm.addEventListener('submit', function() {
                var btn = document.getElementById('refresh-catalog-btn');
                btn.disabled = true;
                btn.textContent = 'Refreshing\u2026';
                btn.classList.add('btn-loading');
            });
        }

        // Non-P2W settings toggle
        var nonP2WToggle = document.getElementById('include-non-p2w');
        if (nonP2WToggle) {
            nonP2WToggle.addEventListener('change', function() {
                apiPost('/library-mgmt/update-settings', {
                    include_non_p2w: this.checked
                });
            });
        }
    });

    // ── Game Search (shared between checkout and checkin) ─────────────

    function setupGameSearch(inputId, resultsId, onSelect) {
        const input = document.getElementById(inputId);
        const resultsDiv = document.getElementById(resultsId);
        if (!input || !resultsDiv) return;

        input.addEventListener('input', debounce(function() {
            const query = this.value.trim();
            if (query.length < 2) {
                resultsDiv.classList.remove('active');
                return;
            }

            apiGet('/library-mgmt/game-search?q=' + encodeURIComponent(query))
                .then(data => {
                    if (!data.results || data.results.length === 0) {
                        resultsDiv.innerHTML = '<div class="search-result-item">No games found</div>';
                        resultsDiv.classList.add('active');
                        return;
                    }

                    resultsDiv.innerHTML = data.results.map(game => {
                        let statusClass = 'status-available';
                        let statusText = 'Available';
                        if (!game.is_in_circulation) {
                            statusClass = 'status-unavailable';
                            statusText = 'Not in circulation';
                        } else if (game.is_checked_out) {
                            statusClass = 'status-out';
                            statusText = 'Checked out';
                        }

                        return `<div class="search-result-item" data-id="${game.id}" data-name="${game.name}" data-checked-out="${game.is_checked_out}" data-p2w="${game.is_play_to_win}">
                            <span>${game.name} <small>(${game.catalog_number || 'N/A'})</small></span>
                            <span class="game-status ${statusClass}">${statusText}</span>
                        </div>`;
                    }).join('');
                    resultsDiv.classList.add('active');

                    resultsDiv.querySelectorAll('.search-result-item').forEach(item => {
                        if (item.dataset.id) {
                            item.addEventListener('click', () => {
                                onSelect(item.dataset);
                                resultsDiv.classList.remove('active');
                                input.value = '';
                            });
                        }
                    });
                });
        }, 300));

        // Close results on outside click
        document.addEventListener('click', (e) => {
            if (!input.contains(e.target) && !resultsDiv.contains(e.target)) {
                resultsDiv.classList.remove('active');
            }
        });
    }

    // ── Checkout Flow ─────────────────────────────────────────────────

    let selectedCheckoutGame = null;

    setupGameSearch('checkout-game-search', 'checkout-game-results', function(dataset) {
        if (dataset.checkedOut === '1' || dataset.checkedOut === 'true' ||
            dataset.checkedOut === 'True' || parseInt(dataset.checkedOut)) {
            showToast('This game is currently checked out.', 'warning');
            return;
        }
        selectedCheckoutGame = { id: dataset.id, name: dataset.name, p2w: dataset.p2w };
        document.getElementById('checkout-game-name').textContent = dataset.name;
        document.getElementById('checkout-form').classList.remove('hidden');
        document.getElementById('checkout-badge').focus();
    });

    // Badge lookup on blur
    const checkoutBadge = document.getElementById('checkout-badge');
    const checkoutName = document.getElementById('checkout-name');
    if (checkoutBadge) {
        checkoutBadge.addEventListener('blur', function() {
            const badge = this.value.trim();
            if (!badge) return;

            apiGet('/library-mgmt/badge-lookup?badge_number=' + encodeURIComponent(badge))
                .then(data => {
                    if (data.name) {
                        checkoutName.value = data.name;
                    }
                })
                .catch(() => {/* ignore — user can type name manually */});
        });
    }

    // Checkout button
    const checkoutBtn = document.getElementById('checkout-btn');
    if (checkoutBtn) {
        checkoutBtn.addEventListener('click', function() {
            if (!selectedCheckoutGame) return;

            const badge = checkoutBadge.value.trim();
            const name = checkoutName.value.trim();
            if (!name) {
                alert('Please enter the renter\'s name.');
                return;
            }

            this.disabled = true;
            apiPost('/library-mgmt/checkout', {
                game_id: selectedCheckoutGame.id,
                renter_name: name,
                badge_number: badge,
            }).then(data => {
                this.disabled = false;
                if (data.error) {
                    showToast('Checkout failed: ' + data.error, 'error');
                    return;
                }

                // Show P2W modal if applicable
                if (data.is_play_to_win) {
                    showP2WModal(selectedCheckoutGame, name, badge);
                } else {
                    showToast('Checked out: ' + selectedCheckoutGame.name, 'success');
                    resetCheckoutForm();
                }
            }).catch(function() {
                this.disabled = false;
                enqueueOperation({
                    type: 'checkout',
                    url: '/library-mgmt/checkout',
                    body: { game_id: selectedCheckoutGame.id, renter_name: name, badge_number: badge },
                    description: 'Checkout: ' + selectedCheckoutGame.name + ' → ' + name,
                });
                showToast('Network error — checkout queued for retry.', 'warning', 6000);
                resetCheckoutForm();
            }.bind(this));
        });
    }

    function resetCheckoutForm() {
        selectedCheckoutGame = null;
        document.getElementById('checkout-form').classList.add('hidden');
        document.getElementById('checkout-badge').value = '';
        document.getElementById('checkout-name').value = '';
        document.getElementById('checkout-game-name').textContent = '';
    }

    // ── Check-In Flow ─────────────────────────────────────────────────

    let selectedCheckinData = null;

    setupGameSearch('checkin-game-search', 'checkin-game-results', function(dataset) {
        if (!parseInt(dataset.checkedOut) && dataset.checkedOut !== '1' &&
            dataset.checkedOut !== 'true' && dataset.checkedOut !== 'True') {
            showToast('This game is not currently checked out.', 'warning');
            return;
        }

        // Fetch active checkout for this game to get checkout_id
        apiGet('/library-mgmt/active-checkout?game_id=' + encodeURIComponent(dataset.id))
            .then(data => {
                if (data.error) {
                    showToast('Could not find active checkout: ' + data.error, 'error');
                    return;
                }
                document.getElementById('checkin-game-name').textContent = dataset.name;
                var renterInfo = data.renter_name ? ('Checked out by: ' + data.renter_name) : '';
                document.getElementById('checkin-renter').textContent = renterInfo;
                document.getElementById('checkin-confirm').classList.remove('hidden');
                selectedCheckinData = {
                    gameId: dataset.id,
                    gameName: dataset.name,
                    checkoutId: data.checkout_id,
                    renterName: data.renter_name,
                    isP2W: dataset.p2w,
                };
            })
            .catch(() => {
                showToast('Could not fetch checkout details.', 'error');
            });
    });

    // Check-in button
    var checkinBtn = document.getElementById('checkin-btn');
    if (checkinBtn) {
        checkinBtn.addEventListener('click', function() {
            if (!selectedCheckinData || !selectedCheckinData.checkoutId) return;

            this.disabled = true;
            apiPost('/library-mgmt/checkin', {
                checkout_id: selectedCheckinData.checkoutId,
                game_id: selectedCheckinData.gameId,
            }).then(data => {
                this.disabled = false;
                if (data.error) {
                    showToast('Check-in failed: ' + data.error, 'error');
                    return;
                }
                if (data.is_play_to_win) {
                    showP2WModal(
                        { id: selectedCheckinData.gameId, name: selectedCheckinData.gameName },
                        selectedCheckinData.renterName, ''
                    );
                } else {
                    showToast('Checked in: ' + selectedCheckinData.gameName, 'success');
                }
                resetCheckinForm();
            }).catch(function() {
                this.disabled = false;
                if (selectedCheckinData) {
                    enqueueOperation({
                        type: 'checkin',
                        url: '/library-mgmt/checkin',
                        body: { checkout_id: selectedCheckinData.checkoutId, game_id: selectedCheckinData.gameId },
                        description: 'Check-in: ' + selectedCheckinData.gameName,
                    });
                    showToast('Network error — check-in queued for retry.', 'warning', 6000);
                    resetCheckinForm();
                } else {
                    showToast('Check-in failed — please try again.', 'error');
                }
            }.bind(this));
        });
    }

    function resetCheckinForm() {
        selectedCheckinData = null;
        document.getElementById('checkin-confirm').classList.add('hidden');
        document.getElementById('checkin-game-name').textContent = '';
        document.getElementById('checkin-renter').textContent = '';
        document.getElementById('checkin-game-search').value = '';
    }

    // ── P2W Entry Modal ───────────────────────────────────────────────

    let p2wGameId = null;
    let p2wEntrants = [];

    function showP2WModal(game, renterName, renterBadge) {
        p2wGameId = game.id;
        p2wEntrants = [{ name: renterName, badge_id: null, isRenter: true }];

        document.getElementById('p2w-game-name').textContent = game.name;

        // Load suggestions
        apiGet('/library-mgmt/p2w-suggestions?name=' + encodeURIComponent(renterName))
            .then(data => {
                const sugDiv = document.getElementById('p2w-suggestions');
                if (data.suggestions && data.suggestions.length > 0) {
                    sugDiv.innerHTML = '<p style="font-size:0.85rem;color:#666;margin:0.5rem 0 0.25rem">Suggested:</p>' +
                        data.suggestions.map(s =>
                            `<label class="p2w-entrant-row">
                                <input type="checkbox" class="p2w-suggestion-cb" data-name="${s.name}" data-badge-id="${s.badge_id || ''}">
                                ${s.name}
                            </label>`
                        ).join('');
                } else {
                    sugDiv.innerHTML = '';
                }
            });

        // Set renter in the entrant list
        const entrantsDiv = document.getElementById('p2w-entrants');
        entrantsDiv.innerHTML = `<div class="p2w-entrant-row">
            <input type="text" value="${renterName}" disabled>
            <input type="checkbox" checked disabled>
            <label>Renter</label>
        </div>`;

        document.getElementById('p2w-modal').classList.remove('hidden');
    }

    // Add entrant button
    const p2wAddBtn = document.getElementById('p2w-add-btn');
    if (p2wAddBtn) {
        p2wAddBtn.addEventListener('click', function() {
            const nameInput = document.getElementById('p2w-add-name');
            const badgeInput = document.getElementById('p2w-add-badge');
            const name = nameInput.value.trim();
            if (!name) return;

            p2wEntrants.push({ name: name, badge_id: null });
            const entrantsDiv = document.getElementById('p2w-entrants');
            entrantsDiv.innerHTML += `<div class="p2w-entrant-row">
                <input type="text" value="${name}" disabled>
                <input type="checkbox" checked>
            </div>`;
            nameInput.value = '';
            badgeInput.value = '';
        });
    }

    // Submit P2W entries
    const p2wSubmit = document.getElementById('p2w-submit');
    if (p2wSubmit) {
        p2wSubmit.addEventListener('click', function() {
            // Collect checked suggestions
            document.querySelectorAll('.p2w-suggestion-cb:checked').forEach(cb => {
                p2wEntrants.push({ name: cb.dataset.name, badge_id: cb.dataset.badgeId || null });
            });

            if (p2wEntrants.length === 0) {
                alert('No entrants selected.');
                return;
            }

            this.disabled = true;
            apiPost('/library-mgmt/p2w-entry', {
                game_id: p2wGameId,
                entrants: p2wEntrants,
            }).then(data => {
                this.disabled = false;
                if (data.error) {
                    showToast('P2W entry failed: ' + data.error, 'error');
                    return;
                }
                var msg = data.created.length + ' entries created';
                if (data.skipped && data.skipped.length > 0) {
                    msg += ', ' + data.skipped.length + ' already entered';
                }
                if (data.errors && data.errors.length > 0) {
                    msg += ', ' + data.errors.length + ' failed';
                }
                showToast(msg, 'success', 5000);
                closeP2WModal();
                resetCheckoutForm();
            }).catch(() => {
                this.disabled = false;
                showToast('P2W entry failed — please try again.', 'error');
            });
        });
    }

    // Skip P2W
    const p2wSkip = document.getElementById('p2w-skip');
    if (p2wSkip) {
        p2wSkip.addEventListener('click', function() {
            closeP2WModal();
            resetCheckoutForm();
        });
    }

    function closeP2WModal() {
        document.getElementById('p2w-modal').classList.add('hidden');
        p2wGameId = null;
        p2wEntrants = [];
    }

    // ── Quick check-in buttons (game detail / person detail) ──────────

    document.querySelectorAll('.checkin-quick-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const checkoutId = this.dataset.checkoutId;
            const gameId = this.dataset.gameId;
            if (!confirm('Check in this game?')) return;

            this.disabled = true;
            apiPost('/library-mgmt/checkin', {
                checkout_id: checkoutId,
                game_id: gameId,
            }).then(data => {
                if (data.error) {
                    showToast('Check-in failed: ' + data.error, 'error');
                    this.disabled = false;
                    return;
                }
                this.closest('.checkout-item').style.opacity = '0.4';
                this.textContent = 'Returned';
            }).catch(() => {
                this.disabled = false;
                showToast('Check-in failed — please try again.', 'error');
            });
        });
    });

    // ── Reset checkout time buttons (game detail) ─────────────────────

    document.querySelectorAll('.reset-time-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            var checkoutId = this.dataset.checkoutId;
            if (!confirm('Reset the checkout timestamp to now?')) return;

            this.disabled = true;
            apiPost('/library-mgmt/reset-checkout-time', {
                checkout_id: checkoutId,
            }).then(data => {
                if (data.error) {
                    showToast('Reset failed: ' + data.error, 'error');
                    this.disabled = false;
                    return;
                }
                this.textContent = 'Time Reset';
                var dateSpan = this.closest('.checkout-item').querySelector('.checkout-date');
                if (dateSpan) dateSpan.textContent = 'since just now';
            }).catch(() => {
                this.disabled = false;
                showToast('Reset failed — please try again.', 'error');
            });
        });
    });

})();
