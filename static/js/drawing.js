(function() {
    var cfg = document.getElementById('page-config').dataset;
    var urls = JSON.parse(cfg.urls);
    var notHereSet = new Set(JSON.parse(cfg.notHere));
    var warningDismissed = cfg.warningDismissed === 'true';
    var pendingNotHereBadge = null;
    var pendingNotHereName = null;

    window.toggleRedrawMode = function() {
        document.body.classList.toggle('redraw-mode');
        var btn = document.getElementById('redraw-toggle');
        btn.classList.toggle('active');
        var active = document.body.classList.contains('redraw-mode');
        btn.textContent = active ? 'Exit Redraw Mode' : 'Enter Redraw Mode';
        if (active) { sessionStorage.setItem('redrawMode', '1'); } else { sessionStorage.removeItem('redrawMode'); }
    };

    // Restore redraw mode after page reload
    if (sessionStorage.getItem('redrawMode') === '1') {
        document.body.classList.add('redraw-mode');
        var btn = document.getElementById('redraw-toggle');
        if (btn) { btn.classList.add('active'); btn.textContent = 'Exit Redraw Mode'; }
    }

    /* ── Expand/collapse entrant list ── */
    document.querySelectorAll('.expand-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var gameId = btn.dataset.gameId;
            var row = btn.closest('tr');
            var isExpanded = btn.dataset.expanded === '1';

            if (isExpanded) {
                var next = row.nextElementSibling;
                while (next && next.classList.contains('entrant-row')) {
                    var toRemove = next;
                    next = next.nextElementSibling;
                    toRemove.remove();
                }
                btn.innerHTML = '&#9654;';
                btn.dataset.expanded = '0';
                return;
            }

            btn.innerHTML = '&#9660;';
            btn.dataset.expanded = '1';
            var colCount = row.cells.length;
            fetch(urls.drawingEntrants.replace('__GID__', gameId))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.ok) return;
                var insertAfter = row;
                data.entrants.forEach(function(ent) {
                    var tr = document.createElement('tr');
                    var cls = 'entrant-row';
                    if (ent.is_winner) cls += ' is-winner';
                    if (ent.is_not_here) cls += ' is-not-here';
                    tr.className = cls;
                    tr.innerHTML = '<td colspan="' + colCount + '">' +
                        '<span style="color:#999;font-size:0.8rem;margin-right:0.5rem;">' + ent.position + '.</span>' +
                        escHtml(ent.name) +
                        ' <span style="color:#999;font-size:0.8rem">(#' + escHtml(ent.badge_id) + ')</span>' +
                        (ent.is_winner ? ' <span style="color:#27ae60;font-size:0.75rem;font-weight:700;">★ WINNER</span>' : '') +
                        (ent.is_not_here ? ' <span style="color:#e74c3c;font-size:0.75rem;">Not Here</span>' : '') +
                        '</td>';
                    insertAfter.after(tr);
                    insertAfter = tr;
                });
            })
            .catch(function() {
                btn.innerHTML = '&#9654;';
                btn.dataset.expanded = '0';
            });
        });
    });

    window.switchView = function(view) {
        document.getElementById('tab-by-game').classList.toggle('active', view === 'by-game');
        document.getElementById('tab-by-winner').classList.toggle('active', view === 'by-winner');
        document.getElementById('panel-by-game').classList.toggle('active', view === 'by-game');
        document.getElementById('panel-by-winner').classList.toggle('active', view === 'by-winner');
        sessionStorage.setItem('activeTab', view);
    };

    // Restore active tab after page reload
    var savedTab = sessionStorage.getItem('activeTab');
    if (savedTab === 'by-game') {
        switchView('by-game');
    }

    window.togglePickup = function(gameId) {
        var btns = document.querySelectorAll('.pickup-btn[data-game-id="' + gameId + '"]');
        btns.forEach(function(b) { b.disabled = true; b.textContent = 'Saving...'; });

        fetch(urls.togglePickup, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({game_id: gameId})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                btns.forEach(function(b) { b.disabled = false; b.textContent = 'Mark Picked Up'; });
                return;
            }
            window.location.reload();
        })
        .catch(function() {
            btns.forEach(function(b) {
                b.disabled = false;
                b.textContent = 'Error — Retry';
                b.style.borderColor = '#e74c3c';
                setTimeout(function() { b.style.borderColor = ''; }, 3000);
            });
        });
    };

    window.awardNext = function(gameId) {
        var btn = document.querySelector('.award-next-btn[data-game-id="' + gameId + '"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Advancing...'; }

        fetch(urls.awardNext, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({game_id: gameId})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                if (btn) { btn.disabled = false; btn.textContent = 'Award to Next'; }
                if (data.error) alert(data.error);
                return;
            }
            if (!data.has_winner) {
                alert('No more players for ' + (data.game_name || 'this game') + '. To the box!');
            }
            window.location.reload();
        })
        .catch(function() {
            if (btn) { btn.disabled = false; btn.textContent = 'Error — Retry'; }
        });
    };

    window.confirmNotHere = function(badgeId, personName) {
        if (warningDismissed) {
            doNotHere(badgeId, false);
            return;
        }
        pendingNotHereBadge = badgeId;
        pendingNotHereName = personName;
        document.getElementById('modal-person-name').textContent = personName;
        document.getElementById('modal-dismiss-checkbox').checked = false;
        document.getElementById('not-here-modal').classList.add('active');
    };

    window.closeNotHereModal = function() {
        document.getElementById('not-here-modal').classList.remove('active');
        pendingNotHereBadge = null;
        pendingNotHereName = null;
    };

    window.executeNotHere = function() {
        var dismissWarning = document.getElementById('modal-dismiss-checkbox').checked;
        if (dismissWarning) warningDismissed = true;
        var badge = pendingNotHereBadge;
        closeNotHereModal();
        doNotHere(badge, dismissWarning);
    };

    function doNotHere(badgeId, dismissWarning) {
        document.querySelectorAll('.not-here-btn[data-badge-id="' + badgeId + '"]').forEach(function(b) {
            b.disabled = true;
            b.textContent = 'Marking...';
        });

        fetch(urls.markNotHere, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({badge_id: badgeId, dismiss_warning: dismissWarning})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                document.querySelectorAll('.not-here-btn[data-badge-id="' + badgeId + '"]').forEach(function(b) {
                    b.disabled = false;
                    b.textContent = 'Not Here';
                });
                if (data.error) alert(data.error);
                return;
            }
            notHereSet.add(badgeId);
            window.location.reload();
        })
        .catch(function() {
            document.querySelectorAll('.not-here-btn[data-badge-id="' + badgeId + '"]').forEach(function(b) {
                b.disabled = false;
                b.textContent = 'Not Here';
            });
        });
    }

    window.redrawUnclaimed = function() {
        var sameRules = document.getElementById('redraw-same-rules').checked;
        if (!confirm('This will redraw all unclaimed games with a fresh shuffle. Proceed?')) return;

        var btn = document.getElementById('redraw-btn');
        btn.disabled = true;
        btn.textContent = 'Redrawing...';

        fetch(urls.redrawAllUnclaimed, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({same_rules: sameRules})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                btn.disabled = false;
                btn.textContent = 'Redraw All Unclaimed';
                alert('Error: ' + (data.error || 'Unknown'));
                return;
            }
            sessionStorage.setItem('redrawMode', '1');
            window.location.reload();
        })
        .catch(function() {
            btn.disabled = false;
            btn.textContent = 'Redraw All Unclaimed';
            alert('Network error — please try again.');
        });
    };

    window.resolveConflict = function(badgeId, gameId) {
        var item = document.querySelector('.conflict-item[data-badge-id="' + badgeId + '"]');
        if (item) {
            item.classList.add('resolving');
        }

        fetch(urls.resolveConflicts, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({resolutions: [{badge_id: badgeId, keep_game_id: gameId}]})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                if (item) item.classList.remove('resolving');
                alert('Error: ' + (data.error || 'Unknown'));
                return;
            }
            if (item) {
                item.classList.add('resolved');
                setTimeout(function() { window.location.reload(); }, 400);
            } else {
                window.location.reload();
            }
        })
        .catch(function() {
            if (item) item.classList.remove('resolving');
            alert('Network error — please try again.');
        });
    };

    window.resolveConflictRandom = function(btn) {
        var badgeId = btn.getAttribute('data-badge-id');
        var gameIds = JSON.parse(btn.getAttribute('data-game-ids'));
        var randomId = pickRandomGameId(gameIds);
        window.resolveConflict(badgeId, randomId);
    };

    function pickRandomGameId(gameIds) {
        var premiumGames = JSON.parse(cfg.premiumGames || '[]');
        var premiumIds = gameIds.filter(function(gid) { return premiumGames.indexOf(gid) !== -1; });
        var pool = premiumIds.length > 0 ? premiumIds : gameIds;
        return pool[Math.floor(Math.random() * pool.length)];
    }

    window.resolveAllRemainingRandom = function() {
        var items = document.querySelectorAll('.conflict-item:not(.resolved):not(.resolving)');
        if (items.length === 0) { alert('No unresolved conflicts remaining.'); return; }

        var msg = 'Randomly resolve all ' + items.length + ' remaining conflict' +
            (items.length > 1 ? 's' : '') + '?\n\n' +
            'Each current conflict will be resolved at random. Premium games will be ' +
            'given priority; otherwise, no consideration is made for game value.\n\n' +
            'This may cause new conflicts which will need to be resolved.';
        if (!confirm(msg)) return;

        var resolutions = [];
        items.forEach(function(item) {
            var badgeId = item.getAttribute('data-badge-id');
            var btn = item.querySelector('.conflict-random-btn');
            var gameIds = JSON.parse(btn.getAttribute('data-game-ids'));
            resolutions.push({badge_id: badgeId, keep_game_id: pickRandomGameId(gameIds)});
            item.classList.add('resolving');
        });

        fetch(urls.resolveConflicts, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({resolutions: resolutions})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                items.forEach(function(item) { item.classList.remove('resolving'); });
                alert('Error: ' + (data.error || 'Unknown'));
                return;
            }
            items.forEach(function(item) { item.classList.add('resolved'); });
            setTimeout(function() { window.location.reload(); }, 400);
        })
        .catch(function() {
            items.forEach(function(item) { item.classList.remove('resolving'); });
            alert('Network error — please try again.');
        });
    };

    window.dismissConflictGame = function(badgeId, gameId, btn) {
        var gameName = btn ? btn.closest('label').textContent.trim().replace(/\s*✕$/, '') : 'this game';
        if (!confirm('Dismiss "' + gameName + '"? This will award it to the next person in the list.')) return;

        var item = document.querySelector('.conflict-item[data-badge-id="' + badgeId + '"');
        if (item) {
            item.classList.add('resolving');
        }

        fetch(urls.dismissConflictGame, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({badge_id: badgeId, game_id: gameId})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                if (item) item.classList.remove('resolving');
                alert('Error: ' + (data.error || 'Unknown'));
                return;
            }
            if (item) {
                item.classList.add('resolved');
            }
            setTimeout(function() { window.location.reload(); }, 400);
        })
        .catch(function() {
            if (item) item.classList.remove('resolving');
            alert('Network error — please try again.');
        });
    };

    // ── Search / Filter ──────────────────────────────────────────────
    var searchInput = document.getElementById('search-input');
    var searchCount = document.getElementById('search-count');

    function filterResults() {
        var query = searchInput.value.trim().toLowerCase();
        var byGameActive = document.getElementById('panel-by-game').classList.contains('active');

        if (byGameActive) {
            filterByGameView(query);
        } else {
            filterByWinnerView(query);
        }
    }

    function filterByGameView(query) {
        var tables = ['awaiting-table', 'picked-up-table', 'no-entries-table'];
        var totalRows = 0;
        var visibleRows = 0;

        tables.forEach(function(tableId) {
            var table = document.getElementById(tableId);
            if (!table) return;
            var rows = table.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                totalRows++;
                if (!query) {
                    row.style.display = '';
                    visibleRows++;
                    return;
                }
                var cells = row.querySelectorAll('td');
                var text = '';
                for (var i = 0; i < cells.length; i++) text += ' ' + cells[i].textContent;
                var match = text.toLowerCase().indexOf(query) !== -1;
                row.style.display = match ? '' : 'none';
                if (match) visibleRows++;
            });
        });

        updateSearchCount(query, visibleRows, totalRows);
    }

    function filterByWinnerView(query) {
        var tables = ['winner-awaiting-table', 'winner-picked-table', 'winner-no-winner-table'];
        var totalRows = 0;
        var visibleRows = 0;

        tables.forEach(function(tableId) {
            var table = document.getElementById(tableId);
            if (!table) return;
            var rows = table.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                totalRows++;
                if (!query) {
                    row.style.display = '';
                    visibleRows++;
                    return;
                }
                var cells = row.querySelectorAll('td');
                var text = '';
                for (var i = 0; i < cells.length; i++) text += ' ' + cells[i].textContent;
                var match = text.toLowerCase().indexOf(query) !== -1;
                row.style.display = match ? '' : 'none';
                if (match) visibleRows++;
            });
        });

        updateSearchCount(query, visibleRows, totalRows);
    }

    function updateSearchCount(query, visible, total) {
        if (!query) {
            searchCount.textContent = '';
        } else {
            searchCount.innerHTML = '<strong>' + visible + '</strong> of <strong>' + total + '</strong> shown';
        }
    }

    searchInput.addEventListener('input', filterResults);

    // Re-filter when switching tabs
    var origSwitchView = window.switchView;
    window.switchView = function(view) {
        origSwitchView(view);
        filterResults();
    };

    function escHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function escAttr(str) {
        return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    window.pushToTTE = function() {
        var count = document.getElementById('pickup-count').textContent;
        if (!confirm('This will update ' + count + ' games in TTE. Proceed?')) return;

        var btn = document.getElementById('push-btn');
        var resultDiv = document.getElementById('push-result');
        btn.disabled = true;
        btn.textContent = 'Pushing...';
        resultDiv.style.display = 'block';
        resultDiv.className = 'push-result';
        resultDiv.textContent = 'Pushing results to TTE...';

        fetch(urls.pushToTte, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.ok) {
                resultDiv.className = 'push-result error';
                resultDiv.textContent = 'Error: ' + (data.error || 'Unknown error');
                btn.disabled = false;
                btn.textContent = 'Push to TTE';
                return;
            }
            if (data.failures.length === 0) {
                resultDiv.className = 'push-result success';
                resultDiv.innerHTML = '<strong>Success!</strong> Updated ' + data.successes + ' of ' + data.total + ' games in TTE.';
            } else {
                resultDiv.className = 'push-result partial';
                var html = '<strong>Partial success:</strong> ' + data.successes + ' of ' + data.total + ' updated.<br>';
                html += '<strong>Failures:</strong><ul>';
                data.failures.forEach(function(f) {
                    html += '<li>Game ' + escHtml(f.game_id) + ': ' + escHtml(f.error) + '</li>';
                });
                html += '</ul>';
                resultDiv.innerHTML = html;
            }
            btn.textContent = 'Push to TTE';
            btn.disabled = false;
        })
        .catch(function() {
            resultDiv.className = 'push-result error';
            resultDiv.textContent = 'Network error — please try again.';
            btn.disabled = false;
            btn.textContent = 'Push to TTE';
        });
    };
})();
