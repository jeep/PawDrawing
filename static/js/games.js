(function() {
    var cfg = document.getElementById('page-config').dataset;
    var urls = JSON.parse(cfg.urls);
    var currentMode = cfg.mode || 'management';
    const statusEl = document.getElementById('save-status');

    /* ── Toast notifications ── */
    function showToast(msg, type) {
        var toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.className = 'toast toast-' + (type || 'success');
        toast.style.display = 'block';
        setTimeout(function() { toast.style.display = 'none'; }, 3000);
    }

    /* ── Mode selector is now simple <a> links — no JS needed ── */

    /* ── Removal: undo chips ── */
    const ejectList = document.getElementById('eject-list');

    /* Undo buttons on existing chips */
    ejectList.addEventListener('click', function(e) {
        const btn = e.target.closest('.undo-btn');
        if (!btn) return;
        const chip = btn.closest('.eject-chip');
        doUneject(chip.dataset.badge, chip.dataset.game, chip);
    });

    function updateEjectCounts() {
        var count = ejectList.querySelectorAll('.eject-chip').length;
        var stat = document.getElementById('eject-stat');
        var statCount = document.getElementById('eject-stat-count');
        var panelCount = document.getElementById('eject-panel-count');
        var panelNum = document.getElementById('eject-panel-num');
        if (stat) stat.style.display = count ? '' : 'none';
        if (statCount) statCount.textContent = count;
        if (panelCount) panelCount.style.display = count ? '' : 'none';
        if (panelNum) panelNum.textContent = count;
    }

    function doEject(badgeId, gameId) {
        fetch(urls.ejectPlayer, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({badge_id: badgeId, game_id: gameId})
        })
        .then(r => { if (!r.ok && r.status !== 409) throw new Error(); return r.json(); })
        .then(function(data) {
            if (data.error) return;
            const chip = document.createElement('span');
            chip.className = 'eject-chip';
            chip.dataset.badge = badgeId;
            chip.dataset.game = gameId;
            chip.innerHTML = badgeId + (gameId === '*' ? ' (all)' : ' (1 game)') +
                ' <button class="undo-btn" title="Undo">&times;</button>';
            ejectList.appendChild(chip);
            updateEntrantRowState(badgeId, gameId, true);
            updateEjectCounts();
        })
        .catch(function() {});
    }

    function doUneject(badgeId, gameId, chip) {
        fetch(urls.unejectPlayer, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({badge_id: badgeId, game_id: gameId})
        })
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(function() {
            chip.remove();
            updateEntrantRowState(badgeId, gameId, false);
            updateEjectCounts();
        })
        .catch(function() {});
    }

    function updateEntrantRowState(badgeId, gameId, ejected) {
        document.querySelectorAll('.entrant-row').forEach(function(row) {
            if (row.dataset.badge !== badgeId) return;
            if (gameId !== '*' && row.dataset.game !== gameId) return;
            row.classList.toggle('ejected', ejected);
            var btn = row.querySelector('.entrant-eject-btn');
            if (btn) {
                btn.className = 'entrant-eject-btn ' + (ejected ? 'uneject' : 'eject');
                btn.textContent = ejected ? 'Restore' : 'Remove';
                btn.dataset.action = ejected ? 'uneject' : 'eject';
            }
        });
    }

    /* ── Expand/collapse entrants ── */
    document.querySelectorAll('.expand-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const gameId = btn.dataset.gameId;
            const row = btn.closest('tr');
            const isExpanded = btn.dataset.expanded === '1';

            if (isExpanded) {
                // Collapse: remove entrant rows
                let next = row.nextElementSibling;
                while (next && next.classList.contains('entrant-row')) {
                    const toRemove = next;
                    next = next.nextElementSibling;
                    toRemove.remove();
                }
                btn.innerHTML = '&#9654;';
                btn.dataset.expanded = '0';
                return;
            }

            // Expand: fetch entrants
            btn.innerHTML = '&#9660;';
            btn.dataset.expanded = '1';
            var colSpan = document.querySelectorAll('.game-table thead th').length;
            fetch(urls.getEntrants.replace('__GID__', gameId))
            .then(r => r.json())
            .then(function(data) {
                if (!data.ok) return;
                let insertAfter = row;
                data.entrants.forEach(function(ent) {
                    const tr = document.createElement('tr');
                    tr.className = 'entrant-row' + (ent.ejected ? ' ejected' : '');
                    tr.dataset.badge = ent.badge_id;
                    tr.dataset.game = gameId;
                    const action = ent.ejected ? 'uneject' : 'eject';
                    const btnClass = ent.ejected ? 'uneject' : 'eject';
                    const btnText = ent.ejected ? 'Restore' : 'Remove';
                    tr.innerHTML = '<td colspan="' + (colSpan - 1) + '">' + escapeHtml(ent.name) +
                        ' <span style="color:#999;font-size:0.8rem">(#' + escapeHtml(ent.badge_id) + ')</span></td>' +
                        '<td style="text-align:center"><button class="entrant-eject-btn ' + btnClass + '" ' +
                        'data-badge="' + escapeHtml(ent.badge_id) + '" data-game="' + escapeHtml(gameId) + '" ' +
                        'data-action="' + action + '">' + btnText + '</button></td>';
                    insertAfter.after(tr);
                    insertAfter = tr;
                });
            })
            .catch(function() {});
        });
    });

    /* Entrant-level eject/uneject via delegation */
    var gameTableEl = document.querySelector('.game-table');
    if (gameTableEl) {
        gameTableEl.addEventListener('click', function(e) {
            var btn = e.target.closest('.entrant-eject-btn');
            if (!btn) return;
            var badgeId = btn.dataset.badge;
            var gameId = btn.dataset.game;
            if (btn.dataset.action === 'eject') {
                doEject(badgeId, gameId);
            } else {
                var chip = ejectList.querySelector('.eject-chip[data-badge="' + badgeId + '"][data-game="' + gameId + '"]') ||
                             ejectList.querySelector('.eject-chip[data-badge="' + badgeId + '"][data-game="*"]');
                if (chip) doUneject(badgeId, chip.dataset.game, chip);
            }
        });
    }

    function escapeHtml(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    /* ── Sort & Search ── */
    const gameTable = document.getElementById('game-table');
    const tbody = gameTable ? gameTable.querySelector('tbody') : null;
    const searchInput = document.getElementById('game-search-input');
    const searchCount = document.getElementById('game-search-count');

    function getGameRows() {
        return tbody ? Array.from(tbody.querySelectorAll('tr:not(.entrant-row)')) : [];
    }

    /* Sorting */
    let currentSort = 'name';
    let currentDir = 'asc';

    function sortRows(key, dir) {
        const rows = getGameRows();
        rows.sort(function(a, b) {
            let va, vb;
            if (key === 'name') {
                va = a.dataset.gameName || '';
                vb = b.dataset.gameName || '';
                return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
            } else if (key === 'entries') {
                va = parseInt(a.dataset.entrantCount, 10) || 0;
                vb = parseInt(b.dataset.entrantCount, 10) || 0;
            } else if (key === 'premium') {
                va = parseInt(a.dataset.isPremium, 10) || 0;
                vb = parseInt(b.dataset.isPremium, 10) || 0;
            } else if (key === 'status') {
                va = a.dataset.checkedOut === '1' ? 1 : 0;
                vb = b.dataset.checkedOut === '1' ? 1 : 0;
            }
            if (va === vb) {
                var na = a.dataset.gameName || '', nb = b.dataset.gameName || '';
                return na.localeCompare(nb);
            }
            return dir === 'asc' ? va - vb : vb - va;
        });
        rows.forEach(function(row) {
            tbody.appendChild(row);
            var gameId = row.dataset.gameId;
            tbody.querySelectorAll('.entrant-row[data-game="' + gameId + '"]').forEach(function(er) {
                tbody.appendChild(er);
            });
        });
    }

    if (gameTable) {
        gameTable.querySelectorAll('th.sortable').forEach(function(th) {
            th.addEventListener('click', function() {
                var key = th.dataset.sort;
                var dir;
                if (currentSort === key) {
                    dir = currentDir === 'asc' ? 'desc' : 'asc';
                } else {
                    dir = key === 'entries' || key === 'premium' || key === 'status' ? 'desc' : 'asc';
                }
                currentSort = key;
                currentDir = dir;

                gameTable.querySelectorAll('th.sortable').forEach(function(h) {
                    h.classList.remove('sort-asc', 'sort-desc');
                    h.querySelector('.sort-arrow').textContent = '\u25B2';
                });
                th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
                th.querySelector('.sort-arrow').textContent = dir === 'asc' ? '\u25B2' : '\u25BC';

                sortRows(key, dir);
            });
        });
    }

    /* Search & P2W filter */
    const p2wFilter = document.getElementById('p2w-filter');

    function applyFilters() {
        var query = searchInput.value.trim().toLowerCase();
        var p2wOnly = p2wFilter && p2wFilter.checked;
        var rows = getGameRows();
        var total = rows.length;
        var visible = 0;

        rows.forEach(function(row) {
            var name = row.dataset.gameName || '';
            var matchText = !query || name.indexOf(query) !== -1;
            var matchP2w = !p2wOnly || row.dataset.isP2w === '1';
            var match = matchText && matchP2w;
            row.style.display = match ? '' : 'none';
            if (match) visible++;

            var gameId = row.dataset.gameId;
            if (tbody) {
                tbody.querySelectorAll('.entrant-row[data-game="' + gameId + '"]').forEach(function(er) {
                    er.style.display = match ? '' : 'none';
                });
            }
        });

        if (query || p2wOnly) {
            searchCount.innerHTML = '<strong>' + visible + '</strong> of <strong>' + total + '</strong>';
        } else {
            searchCount.textContent = '';
        }
    }

    searchInput.addEventListener('input', applyFilters);
    if (p2wFilter) p2wFilter.addEventListener('change', applyFilters);

    document.querySelectorAll('.premium-toggle').forEach(function(toggle) {
        toggle.addEventListener('change', savePremiumGames);
    });

    /* ── Premium toggle ── */
    function savePremiumGames() {
        const checked = document.querySelectorAll('.premium-toggle:checked');
        const gameIds = Array.from(checked).map(cb => cb.dataset.gameId);

        document.querySelectorAll('.game-table tbody tr:not(.entrant-row)').forEach(function(row) {
            const id = row.dataset.gameId;
            const isPremium = gameIds.includes(id);
            row.classList.toggle('premium', isPremium);
            row.dataset.isPremium = isPremium ? '1' : '0';
            const label = row.querySelector('.premium-label');
            if (isPremium && !label) {
                const td = row.querySelector('td');
                const span = document.createElement('span');
                span.className = 'premium-label';
                span.textContent = 'Premium';
                td.appendChild(span);
            } else if (!isPremium && label) {
                label.remove();
            }
        });

        fetch(urls.setPremiumGames, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({premium_games: gameIds})
        })
        .then(r => r.json())
        .then(function() {
            statusEl.textContent = 'Saved';
            statusEl.classList.add('visible');
            setTimeout(() => statusEl.classList.remove('visible'), 1500);
        })
        .catch(function() {
            statusEl.textContent = 'Save failed';
            statusEl.style.color = '#b71c1c';
            statusEl.classList.add('visible');
            setTimeout(() => {
                statusEl.classList.remove('visible');
                statusEl.style.color = '#27ae60';
                statusEl.textContent = 'Saved';
            }, 2000);
        });
    }

    /* ── Badge auto-lookup ── */
    function lookupBadge(badgeInput, nameInput, statusEl) {
        var badge = badgeInput.value.trim();
        if (!badge) return;
        statusEl.textContent = 'Looking up…';
        statusEl.className = 'badge-status';
        fetch(urls.badgeLookup + '?badge_number=' + encodeURIComponent(badge))
        .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
        .then(function(result) {
            if (result.ok && result.data.name) {
                nameInput.value = result.data.name;
                nameInput.dataset.badgeId = result.data.badge_id || '';
                statusEl.textContent = '✓ ' + result.data.name;
                statusEl.className = 'badge-status badge-found';
            } else {
                statusEl.textContent = result.data.error || 'Not found';
                statusEl.className = 'badge-status badge-notfound';
            }
        })
        .catch(function() {
            statusEl.textContent = 'Lookup failed';
            statusEl.className = 'badge-status badge-notfound';
        });
    }

    /* ── Checkout Modal ── */
    var checkoutModal = document.getElementById('checkout-modal');
    var checkoutGameId = document.getElementById('checkout-game-id');
    var checkoutGameName = document.getElementById('checkout-game-name');
    var checkoutBadge = document.getElementById('checkout-badge');
    var checkoutName = document.getElementById('checkout-name');
    var checkoutBadgeStatus = document.getElementById('checkout-badge-status');

    if (gameTableEl) {
        gameTableEl.addEventListener('click', function(e) {
            var btn = e.target.closest('.btn-checkout');
            if (btn) {
                checkoutGameId.value = btn.dataset.gameId;
                checkoutGameName.textContent = btn.dataset.gameName;
                checkoutBadge.value = '';
                checkoutName.value = '';
                checkoutName.dataset.badgeId = '';
                checkoutBadgeStatus.textContent = '';
                checkoutModal.style.display = 'flex';
                checkoutBadge.focus();
                return;
            }

            var checkinBtn = e.target.closest('.btn-checkin');
            if (checkinBtn) {
                openCheckinModal(checkinBtn);
            }
        });
    }

    checkoutBadge.addEventListener('blur', function() {
        lookupBadge(checkoutBadge, checkoutName, checkoutBadgeStatus);
    });
    checkoutBadge.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); checkoutBadge.blur(); }
    });

    document.getElementById('checkout-cancel').addEventListener('click', function() {
        checkoutModal.style.display = 'none';
    });

    document.getElementById('checkout-submit').addEventListener('click', function() {
        var gameId = checkoutGameId.value;
        var name = checkoutName.value.trim();
        var badge = checkoutBadge.value.trim();
        if (!name) { showToast('Name is required', 'error'); return; }

        this.disabled = true;
        var self = this;
        fetch(urls.checkout, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({game_id: gameId, renter_name: name, badge_number: badge})
        })
        .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
        .then(function(result) {
            self.disabled = false;
            if (!result.ok) {
                showToast(result.data.error || 'Checkout failed', 'error');
                return;
            }
            checkoutModal.style.display = 'none';
            updateGameRow(gameId, true, name, result.data.checkout_id || '');
            showToast(name + ' checked out successfully');
        })
        .catch(function() {
            self.disabled = false;
            showToast('Checkout failed', 'error');
        });
    });

    /* ── Check In Modal ── */
    var checkinModal = document.getElementById('checkin-modal');
    var checkinGameId = document.getElementById('checkin-game-id');
    var checkinCheckoutId = document.getElementById('checkin-checkout-id');
    var checkinGameName = document.getElementById('checkin-game-name');
    var checkinRenterName = document.getElementById('checkin-renter-name');
    var checkinIsP2w = document.getElementById('checkin-is-p2w');
    var p2wSection = document.getElementById('p2w-section');
    var p2wEntrants = document.getElementById('p2w-entrants');
    var p2wGameLabel = document.getElementById('p2w-game-label');

    function populateP2wEntrantsForRenter(renter) {
        p2wEntrants.innerHTML = '';
        if (!renter) return;

        // Add renter as default entrant (pre-checked).
        addP2wEntrant(renter, '', true);

        fetch(urls.p2wSuggestions + '?name=' + encodeURIComponent(renter))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            (data.suggestions || []).forEach(function(s) {
                if (s && s.name) {
                    addP2wEntrant(s.name, s.badge_id || '', false);
                }
            });
        })
        .catch(function() {});
    }

    function openCheckinModal(btn) {
        var gameId = btn.dataset.gameId;
        var checkoutId = btn.dataset.checkoutId;
        var renter = btn.dataset.renter;
        var gameName = btn.dataset.gameName;
        var isP2w = btn.dataset.isP2w === '1';

        checkinGameId.value = gameId;
        checkinCheckoutId.value = checkoutId;
        checkinGameName.textContent = gameName;
        checkinRenterName.textContent = renter;
        checkinIsP2w.value = isP2w ? '1' : '0';

        // Reset P2W section
        p2wEntrants.innerHTML = '';

        if (isP2w) {
            p2wSection.style.display = '';
            p2wGameLabel.textContent = gameName;
            document.getElementById('checkin-submit').textContent = 'Enter into Drawing';
            populateP2wEntrantsForRenter(renter);
        } else {
            p2wSection.style.display = 'none';
            document.getElementById('checkin-submit').textContent = 'Check In';
        }

        checkinModal.style.display = 'flex';

        // If no checkout_id, try to fetch it
        if (!checkoutId) {
            fetch(urls.activeCheckout + '?game_id=' + encodeURIComponent(gameId))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.checkout_id) {
                    checkinCheckoutId.value = data.checkout_id;
                    if (data.renter_name) {
                        checkinRenterName.textContent = data.renter_name;
                        if (isP2w && data.renter_name !== renter) {
                            populateP2wEntrantsForRenter(data.renter_name);
                        }
                    }
                }
            })
            .catch(function() {});
        }
    }

    function addP2wEntrant(name, badgeId, checked) {
        var div = document.createElement('div');
        div.className = 'p2w-entrant';
        var id = 'p2w-ent-' + Math.random().toString(36).substr(2, 6);
        div.innerHTML = '<label><input type="checkbox" id="' + id + '" ' +
            (checked ? 'checked' : '') + ' data-name="' + escapeHtml(name) + '" ' +
            'data-badge-id="' + escapeHtml(badgeId) + '"> ' +
            escapeHtml(name) + '</label>' +
            '<button class="p2w-remove-btn" title="Remove">&times;</button>';
        div.querySelector('.p2w-remove-btn').addEventListener('click', function() { div.remove(); });
        p2wEntrants.appendChild(div);
    }

    // P2W add row
    var p2wBadge = document.getElementById('p2w-badge');
    var p2wName = document.getElementById('p2w-name');
    p2wBadge.addEventListener('blur', function() {
        if (p2wBadge.value.trim()) {
            var tmpStatus = document.createElement('span');
            lookupBadge(p2wBadge, p2wName, tmpStatus);
        }
    });
    p2wBadge.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') { e.preventDefault(); p2wBadge.blur(); }
    });

    document.getElementById('p2w-add-btn').addEventListener('click', function() {
        var name = p2wName.value.trim();
        if (!name) return;
        addP2wEntrant(name, p2wName.dataset.badgeId || '', true);
        p2wBadge.value = '';
        p2wName.value = '';
        p2wName.dataset.badgeId = '';
    });

    document.getElementById('checkin-cancel').addEventListener('click', function() {
        checkinModal.style.display = 'none';
    });

    // Skip = check in without P2W
    document.getElementById('checkin-skip').addEventListener('click', function() {
        doCheckin(false);
    });

    // Submit = check in + P2W entries
    document.getElementById('checkin-submit').addEventListener('click', function() {
        var isP2w = checkinIsP2w.value === '1';
        doCheckin(isP2w);
    });

    function doCheckin(withP2w) {
        var gameId = checkinGameId.value;
        var checkoutId = checkinCheckoutId.value;
        if (!checkoutId) {
            showToast('Missing checkout ID — try refreshing', 'error');
            return;
        }

        // Collect P2W entrants if needed
        var p2wPayload = [];
        if (withP2w) {
            p2wEntrants.querySelectorAll('input[type="checkbox"]:checked').forEach(function(cb) {
                p2wPayload.push({name: cb.dataset.name, badge_id: cb.dataset.badgeId || null});
            });
        }

        fetch(urls.checkin, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({checkout_id: checkoutId, game_id: gameId})
        })
        .then(function(r) { return r.json().then(function(d) { return {ok: r.ok, data: d}; }); })
        .then(function(result) {
            if (!result.ok) {
                showToast(result.data.error || 'Check in failed', 'error');
                return;
            }
            checkinModal.style.display = 'none';
            updateGameRow(gameId, false, '', '');
            showToast('Game checked in');

            // Create P2W entries if any
            if (p2wPayload.length > 0) {
                fetch(urls.p2wEntry, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({game_id: gameId, entrants: p2wPayload})
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    applyP2wResultToGameRow(gameId, data);
                    if (data.created && data.created.length) {
                        showToast(data.created.length + ' P2W entry(s) added');
                    }
                })
                .catch(function() {});
            }
        })
        .catch(function() {
            showToast('Check in failed', 'error');
        });
    }

    function applyP2wResultToGameRow(gameId, data) {
        var createdCount = (data && data.created && data.created.length) ? data.created.length : 0;
        if (createdCount <= 0) return;

        var row = document.querySelector('tr[data-game-id="' + gameId + '"]');
        if (!row) return;

        var current = parseInt(row.dataset.entrantCount, 10) || 0;
        var next = current + createdCount;
        row.dataset.entrantCount = String(next);

        var entriesCell = row.children[1];
        if (entriesCell) {
            if (next === 0) {
                entriesCell.innerHTML = '<span class="badge-zero">No entries</span>';
            } else {
                entriesCell.textContent = String(next);
            }
        }
    }

    /* ── Update game row after checkout/checkin ── */
    function updateGameRow(gameId, checkedOut, renterName, checkoutId) {
        var row = document.querySelector('tr[data-game-id="' + gameId + '"]');
        if (!row) return;

        row.dataset.checkedOut = checkedOut ? '1' : '0';
        row.dataset.renter = renterName;
        row.dataset.checkoutId = checkoutId;

        // Update status cell
        var statusCell = row.querySelector('.td-status');
        if (statusCell) {
            if (checkedOut) {
                statusCell.innerHTML = '<span class="status-out">' + escapeHtml(renterName || 'Checked Out') + '</span>';
            } else {
                statusCell.innerHTML = '<span class="status-available">Available</span>';
            }
        }

        // Update action cell
        var actionCell = row.querySelector('.td-action');
        if (actionCell) {
            var gameName = row.dataset.gameName || '';
            // Get proper case name from first cell
            var firstTd = row.querySelector('td');
            var displayName = '';
            if (firstTd) {
                // Extract text, skipping buttons and spans
                firstTd.childNodes.forEach(function(n) {
                    if (n.nodeType === 3) displayName += n.textContent;
                });
                displayName = displayName.trim();
            }
            var isP2w = row.dataset.isP2w || '0';

            if (checkedOut) {
                actionCell.innerHTML = '<button class="btn-checkin" data-game-id="' + escapeHtml(gameId) + '"' +
                    ' data-checkout-id="' + escapeHtml(checkoutId) + '"' +
                    ' data-renter="' + escapeHtml(renterName) + '"' +
                    ' data-game-name="' + escapeHtml(displayName) + '"' +
                    ' data-is-p2w="' + isP2w + '">Check In</button>';
            } else {
                actionCell.innerHTML = '<button class="btn-checkout" data-game-id="' + escapeHtml(gameId) + '"' +
                    ' data-game-name="' + escapeHtml(displayName) + '"' +
                    ' data-is-p2w="' + isP2w + '">Check Out</button>';
            }
        }
    }

    /* Close modals on overlay click */
    document.querySelectorAll('.modal-overlay').forEach(function(overlay) {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) overlay.style.display = 'none';
        });
    });

    /* Close modals on Escape */
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            checkoutModal.style.display = 'none';
            checkinModal.style.display = 'none';
            var settingsModal = document.getElementById('settings-modal');
            if (settingsModal) settingsModal.style.display = 'none';
            var notifDropdown = document.getElementById('notif-dropdown');
            if (notifDropdown) notifDropdown.style.display = 'none';
        }
    });

    /* ── Settings modal ── */
    var settingsModal = document.getElementById('settings-modal');
    var settingsOpen = document.getElementById('settings-open');
    var settingsClose = document.getElementById('settings-close');
    var alertHoursInput = document.getElementById('alert-hours');

    if (settingsOpen && settingsModal) {
        settingsOpen.addEventListener('click', function() {
            settingsModal.style.display = 'flex';
        });
        settingsClose.addEventListener('click', function() {
            settingsModal.style.display = 'none';
        });
    }

    if (alertHoursInput) {
        alertHoursInput.addEventListener('change', function() {
            var hours = parseInt(alertHoursInput.value, 10);
            if (isNaN(hours) || hours < 1) hours = 1;
            if (hours > 24) hours = 24;
            alertHoursInput.value = hours;
            fetch(urls.updateSettings, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({checkout_alert_hours: hours})
            })
            .then(function(r) { return r.json(); })
            .then(function() { showToast('Alert threshold updated'); })
            .catch(function() { showToast('Failed to save setting', 'error'); });
        });
    }

    /* ── Mark All P2W button ── */
    var markAllP2WBtn = document.getElementById('mark-all-p2w-btn');
    if (markAllP2WBtn) {
        markAllP2WBtn.addEventListener('click', function() {
            if (!confirm('Mark all in-circulation games as Play-to-Win?')) return;
            markAllP2WBtn.disabled = true;
            markAllP2WBtn.textContent = 'Marking…';
            fetch(urls.markAllP2W, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast(data.message || 'Done');
                } else {
                    showToast(data.error || 'Failed', 'error');
                }
                markAllP2WBtn.disabled = false;
                markAllP2WBtn.textContent = 'Mark All Games as P2W';
            })
            .catch(function() {
                showToast('Failed to mark games', 'error');
                markAllP2WBtn.disabled = false;
                markAllP2WBtn.textContent = 'Mark All Games as P2W';
            });
        });
    }

    /* ── Notification bell ── */
    var notifBell = document.getElementById('notif-bell');
    var notifDropdown = document.getElementById('notif-dropdown');
    var notifList = document.getElementById('notif-list');
    var notifBadge = document.getElementById('notif-badge');

    if (notifBell && notifDropdown) {
        notifBell.addEventListener('click', function(e) {
            e.stopPropagation();
            var isOpen = notifDropdown.style.display !== 'none';
            if (isOpen) {
                notifDropdown.style.display = 'none';
                return;
            }
            // Fetch and show notifications
            fetch(urls.notifications)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var items = data.notifications || [];
                if (items.length === 0) {
                    notifList.innerHTML = '<p class="notif-empty">No notifications</p>';
                } else {
                    notifList.innerHTML = '';
                    items.forEach(function(n) {
                        var div = document.createElement('div');
                        div.className = 'notif-item notif-' + (n.type || 'info');
                        div.innerHTML = '<span class="notif-msg">' + escapeHtml(n.message) + '</span>' +
                            '<button class="notif-dismiss" data-id="' + escapeHtml(n.id) + '" title="Dismiss">✕</button>';
                        if (n.details && n.details.length) {
                            var detailEl = document.createElement('div');
                            detailEl.className = 'notif-details';
                            detailEl.textContent = n.details.join(', ');
                            div.appendChild(detailEl);
                        }
                        notifList.appendChild(div);
                    });
                }
                notifDropdown.style.display = 'block';
            })
            .catch(function() {
                notifList.innerHTML = '<p class="notif-empty">Failed to load</p>';
                notifDropdown.style.display = 'block';
            });
        });

        // Dismiss notification
        notifList.addEventListener('click', function(e) {
            var btn = e.target.closest('.notif-dismiss');
            if (!btn) return;
            var id = btn.dataset.id;
            var item = btn.closest('.notif-item');
            fetch(urls.dismissNotification, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: id})
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (item) item.remove();
                if (notifList.querySelectorAll('.notif-item').length === 0) {
                    notifList.innerHTML = '<p class="notif-empty">No notifications</p>';
                }
                var remaining = data.remaining || 0;
                if (remaining > 0) {
                    notifBadge.textContent = remaining;
                    notifBadge.style.display = '';
                } else {
                    notifBadge.style.display = 'none';
                }
            })
            .catch(function() {});
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('#notif-wrapper')) {
                notifDropdown.style.display = 'none';
            }
        });
    }

    /* ── Checkout status polling ── */
    if (currentMode === 'management' && urls.checkoutStatus) {
        var POLL_INTERVAL = 30000; // 30 seconds
        var pollTimer = null;

        function pollCheckoutStatus() {
            fetch(urls.checkoutStatus)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var changes = data.changes || {};
                    var keys = Object.keys(changes);
                    if (keys.length === 0) return;
                    keys.forEach(function(gameId) {
                        var c = changes[gameId];
                        updateGameRow(gameId, c.checked_out, c.renter, c.checkout_id);
                    });
                })
                .catch(function() { /* silent — will retry next interval */ });
        }

        function startPolling() {
            if (!pollTimer) {
                pollTimer = setInterval(pollCheckoutStatus, POLL_INTERVAL);
            }
        }

        function stopPolling() {
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        }

        // Pause polling when tab is hidden to save API calls
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                stopPolling();
            } else {
                // Poll immediately when tab becomes visible, then resume interval
                pollCheckoutStatus();
                startPolling();
            }
        });

        startPolling();
    }
})();
