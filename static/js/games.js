(function() {
    var cfg = document.getElementById('page-config').dataset;
    var urls = JSON.parse(cfg.urls);
    const statusEl = document.getElementById('save-status');

    /* ── Removal: undo chips ── */
    const ejectList = document.getElementById('eject-list');

    /* Undo buttons on existing chips */
    ejectList.addEventListener('click', function(e) {
        const btn = e.target.closest('.undo-btn');
        if (!btn) return;
        const chip = btn.closest('.eject-chip');
        doUneject(chip.dataset.badge, chip.dataset.game, chip);
    });

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
            // Mark entrant rows if expanded
            updateEntrantRowState(badgeId, gameId, true);
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
        })
        .catch(function() {});
    }

    function updateEntrantRowState(badgeId, gameId, ejected) {
        document.querySelectorAll('.entrant-row').forEach(function(row) {
            if (row.dataset.badge !== badgeId) return;
            if (gameId !== '*' && row.dataset.game !== gameId) return;
            row.classList.toggle('ejected', ejected);
            const btn = row.querySelector('.entrant-eject-btn');
            if (btn) {
                btn.className = 'entrant-eject-btn ' + (ejected ? 'uneject' : 'eject');
                btn.textContent = ejected ? 'Undo' : 'Eject';
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
                    const btnText = ent.ejected ? 'Undo' : 'Remove';
                    tr.innerHTML = '<td colspan="2">' + escapeHtml(ent.name) +
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
    document.querySelector('.game-table').addEventListener('click', function(e) {
        const btn = e.target.closest('.entrant-eject-btn');
        if (!btn) return;
        const badgeId = btn.dataset.badge;
        const gameId = btn.dataset.game;
        if (btn.dataset.action === 'eject') {
            doEject(badgeId, gameId);
        } else {
            // Find the matching chip to remove
            const chip = ejectList.querySelector('.eject-chip[data-badge="' + badgeId + '"][data-game="' + gameId + '"]') ||
                         ejectList.querySelector('.eject-chip[data-badge="' + badgeId + '"][data-game="*"]');
            if (chip) doUneject(badgeId, chip.dataset.game, chip);
        }
    });

    function escapeHtml(s) {
        const d = document.createElement('div');
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
            }
            if (va === vb) {
                // Secondary sort by name
                var na = a.dataset.gameName || '', nb = b.dataset.gameName || '';
                return na.localeCompare(nb);
            }
            return dir === 'asc' ? va - vb : vb - va;
        });
        // Re-append rows (and their entrant-row children)
        rows.forEach(function(row) {
            tbody.appendChild(row);
            // Move any entrant rows that belong to this game row
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
                    dir = key === 'entries' || key === 'premium' ? 'desc' : 'asc';
                }
                currentSort = key;
                currentDir = dir;

                // Update header indicators
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

    /* Search */
    searchInput.addEventListener('input', function() {
        var query = searchInput.value.trim().toLowerCase();
        var rows = getGameRows();
        var total = rows.length;
        var visible = 0;

        rows.forEach(function(row) {
            var name = row.dataset.gameName || '';
            var match = !query || name.indexOf(query) !== -1;
            row.style.display = match ? '' : 'none';
            if (match) visible++;

            // Also hide entrant rows for hidden games
            var gameId = row.dataset.gameId;
            if (tbody) {
                tbody.querySelectorAll('.entrant-row[data-game="' + gameId + '"]').forEach(function(er) {
                    er.style.display = match ? '' : 'none';
                });
            }
        });

        if (query) {
            searchCount.innerHTML = '<strong>' + visible + '</strong> of <strong>' + total + '</strong>';
        } else {
            searchCount.textContent = '';
        }
    });

    document.querySelectorAll('.premium-toggle').forEach(function(toggle) {
        toggle.addEventListener('change', savePremiumGames);
    });

    /* ── Premium toggle ── */
    function savePremiumGames() {
        const checked = document.querySelectorAll('.premium-toggle:checked');
        const gameIds = Array.from(checked).map(cb => cb.dataset.gameId);

        // Update row styling immediately
        document.querySelectorAll('.game-table tbody tr').forEach(function(row) {
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
})();
