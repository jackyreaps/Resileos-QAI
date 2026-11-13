/* Presentational chat UI. Does not set API keys or change request bodies except
   optional /search and /tool shortcuts the server already accepts. */
(function () {
    var COMMANDS = [
        { name: '/search', insert: '/search ', description: 'Search the web. Results stay unverified.' },
        { name: '/tool', insert: '/tool ', description: 'Run a named tool. Optional shortcut.' }
    ];
    var TOOL_STEPS = {
        web_search: 'Searching the web',
        residual_consistency: 'Checking consistency',
        video_generate: 'Making an image',
        forge_video: 'Making an image',
        resileos_ask: 'Checking stored facts',
        resileos_answer: 'Checking stored facts',
        resileos_chain: 'Checking stored facts'
    };
    var pendingStep = '';
    var mode = '';
    var slashIndex = 0;
    var slashItems = [];

    function $(id) { return document.getElementById(id); }

    function plainToolStep(name) {
        if (TOOL_STEPS[name]) return TOOL_STEPS[name];
        if (/iris|metis|hermes|hades|apollo|athena|zeus|aphrodite|hephaestus|atropos|clotho|calliope|ligeia/i.test(name)) {
            return 'Running a tool';
        }
        return 'Running ' + String(name || 'a tool').replace(/_/g, ' ');
    }

    function stepsFor(data) {
        var steps = [];
        var status = String((data && data.status) || '').toLowerCase();
        var kind = (data && data.message_kind) || '';
        var source = (data && data.source) || '';
        var tools = ((data && data.tool_calls) || []).map(function (t) { return t.tool || t.name; }).filter(Boolean);
        var search = kind === 'search' || source === 'web_search' || tools.indexOf('web_search') !== -1;
        if (search) steps.push('Searching the web');
        else if (source === 'kin') steps.push('Running a learning cycle');
        else if (data && (data.patron || data.clotho_owner || data.stage)) steps.push('Making an image');
        else if (tools.length) tools.forEach(function (name) { steps.push(plainToolStep(name)); });
        else if (kind === 'residual' || source === 'memory' || (data && data.memory_chip)) steps.push('Checking stored facts');
        else if (kind === 'abstain' || status === 'abstained' || status === 'abstain' || status === 'no_rows') steps.push('Checking stored facts');
        else if (status || kind) steps.push('Checking facts');
        if (status === 'abstained' || status === 'abstain' || status === 'no_rows' || status === 'mouth_closed' || kind === 'abstain') steps.push('Abstained');
        else if (status === 'unavailable') steps.push('Unavailable');
        else if (status === 'conflict' || status === 'reject' || status === 'rejected') steps.push('Conflict');
        else if (status === 'refused') steps.push('Refused');
        else if (status === 'error') steps.push('Could not finish');
        else if (steps.length) steps.push('Done');
        return steps.filter(function (step, i) { return i === 0 || step !== steps[i - 1]; });
    }

    function honestBadge(data) {
        if (!data) return null;
        var status = String(data.status || '').toLowerCase();
        var kind = data.message_kind || '';
        if (!status && data.verified == null && !kind) return null;
        if (['abstained', 'abstain', 'no_rows', 'mouth_closed'].indexOf(status) !== -1 || kind === 'abstain') {
            return { text: 'Abstained', kind: 'abstained' };
        }
        if (['conflict', 'reject', 'rejected'].indexOf(status) !== -1) return { text: 'Conflict', kind: 'conflict' };
        if (status === 'unavailable') return { text: 'Unavailable', kind: 'unavailable' };
        if (status === 'refused') return { text: 'Refused', kind: 'refused' };
        if (status === 'error') return { text: 'Error', kind: 'error' };
        if (status === 'fully_stopped') return { text: 'Stopped', kind: 'accepted' };
        if (status === 'stop_requested') return { text: 'Stop requested', kind: 'abstained' };
        if (data.verified === true || data.cycle_verified === true || status === 'verified' || status === 'pass') {
            return { text: 'Verified', kind: 'accepted' };
        }
        if (data.verified === false || status === 'unverified' || kind === 'search' || data.source === 'web_search') {
            return { text: 'Unverified', kind: 'unverified' };
        }
        if (['accepted', 'answered', 'submitted'].indexOf(status) !== -1) {
            return { text: 'Unverified', kind: 'unverified' };
        }
        if (status) return { text: data.status, kind: '' };
        return null;
    }

    function technicalDetails(data, opts, notes) {
        var lines = [];
        var d = data || {};
        if (d.source) lines.push('Module: ' + d.source);
        if (typeof d.verified === 'boolean') lines.push('Verified: ' + (d.verified ? 'yes' : 'no'));
        if (typeof d.cycle_verified === 'boolean') lines.push('Cycle verified: ' + (d.cycle_verified ? 'yes' : 'no'));
        if (d.status) lines.push('Status: ' + d.status);
        if (d.message_kind) lines.push('Kind: ' + d.message_kind);
        if (d.router_class) lines.push('Router: ' + d.router_class);
        if (d.chip) lines.push('Chip: ' + d.chip);
        var tools = (d.tool_calls || []).map(function (t) { return t.tool || t.name; }).filter(Boolean);
        if (tools.length) lines.push('Tools: ' + tools.join(', '));
        if (Array.isArray(d.rows) && d.rows.length) lines.push('Residual: ' + d.rows.map(String).join(', '));
        if (d.subject) lines.push('Subject: ' + d.subject);
        if (opts && typeof opts.ms === 'number') lines.push('Timing: ' + Math.round(opts.ms) + ' ms');
        (notes || []).forEach(function (note) {
            if (!note || /^\d+\s*ms$/.test(note)) return;
            if (!/^(?:Module|Patron|Stage|Clotho owner|State):/.test(note) && note.charAt(0) !== '{' && note.charAt(0) !== '[') return;
            if (lines.indexOf(note) === -1) lines.push(note);
        });
        return lines;
    }

    function rewriteLine(line) {
        var text = line;
        var moved = [];
        var rules = [
            [/^Kin cycle complete\./, 'Learning cycle finished.', 'Module: kin cycle'],
            [/^Forge submitted a draft\.$/, 'A draft was submitted.', 'Module: forge'],
            [/^Forge submitted a video\.$/, 'A video was submitted.', 'Module: forge'],
            [/^Forge refused this stage\.$/, 'This request was refused.', 'Module: forge'],
            [/^Forge finished\.$/, 'Finished.', 'Module: forge'],
            [/^Forge verified\.$/, 'The result is verified.', 'Module: forge'],
            [/^Forge unverified\.$/, 'The result is unverified.', 'Module: forge'],
            [/^Atropos cut the owner\..*/, 'The job was stopped.', 'Module: stop'],
            [/^Atropos requested a stop.*/, 'A stop was requested.', 'Module: stop'],
            [/^No Clotho group is registered.*/, 'No running job was found for that name.', 'Module: stop'],
            [/^Tool .+ finished\.$/, 'Finished.', null],
            [/^Eat reviewed /, 'Reviewed ', 'Module: eat']
        ];
        rules.forEach(function (rule) {
            if (rule[0].test(text)) {
                text = text.replace(rule[0], rule[1]);
                if (rule[2]) moved.push(rule[2]);
            }
        });
        return { text: text, moved: moved };
    }

    function stripReply(text) {
        var moved = [];
        var body = String(text || '').replace(/\[(Hermes|Iris|Metis|Apollo|Hades|Athena|Hephaestus|Atropos|Clotho|Aphrodite|Zeus|Kin)\]\s*/g, function (_, name) {
            moved.push('Module: ' + name);
            return '';
        });
        var kept = [];
        body.split('\n').forEach(function (line) {
            var trimmed = line.trim();
            if (/^(?:source|verified|tools|router_class|module|kin)\s*:/i.test(trimmed) || /^(?:Patron|Stage|Clotho owner|State)\s*:/.test(trimmed)) {
                moved.push(trimmed);
                return;
            }
            var rewritten = rewriteLine(line);
            rewritten.moved.forEach(function (item) { moved.push(item); });
            kept.push(rewritten.text);
        });
        body = kept.join('\n').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
        if ((body.charAt(0) === '{' || body.charAt(0) === '[') && body.length > 1) {
            try {
                JSON.parse(body);
                moved.push(body);
                body = 'Finished. Open Details for the raw result.';
            } catch (err) { /* prose that happens to start with a bracket */ }
        }
        return { text: body, moved: moved };
    }

    function polishReply(bubble, data, opts) {
        if (!bubble || bubble.nodeType !== 1 || bubble.querySelector('.reply-status')) return;
        var notes = [];
        bubble.querySelectorAll('.meta').forEach(function (meta) {
            var text = (meta.textContent || '').trim();
            if (text) notes.push(text);
            meta.remove();
        });
        var reply = bubble.querySelector('.reply');
        if (reply) {
            var stripped = stripReply(reply.textContent);
            if (stripped.moved.length) reply.textContent = stripped.text || 'Finished. Open Details for the technical result.';
            stripped.moved.forEach(function (line) { notes.push(line); });
        }
        var steps = stepsFor(data);
        var badge = honestBadge(data);
        if (steps.length || badge || (data && data.memory_chip)) {
            var bar = document.createElement('div');
            bar.className = 'reply-status';
            if (steps.length) {
                var fold = document.createElement('details');
                fold.className = 'step-fold';
                var summary = document.createElement('summary');
                var current = document.createElement('span');
                current.className = 'step-current';
                current.textContent = steps[0];
                summary.appendChild(current);
                var list = document.createElement('ol');
                list.className = 'step-list';
                steps.forEach(function (step) {
                    var item = document.createElement('li');
                    item.textContent = step;
                    list.appendChild(item);
                });
                fold.append(summary, list);
                bar.appendChild(fold);
            }
            if (badge) {
                var chip = document.createElement('span');
                chip.className = 'chip ' + badge.kind;
                chip.textContent = badge.text;
                bar.appendChild(chip);
            }
            if (data && data.memory_chip) {
                var remembered = document.createElement('span');
                remembered.className = 'chip memory';
                remembered.textContent = 'Remembered';
                bar.appendChild(remembered);
            }
            bubble.insertBefore(bar, bubble.firstChild);
        }
        var detailLines = technicalDetails(data, opts, notes);
        if (!detailLines.length) return;
        var details = bubble.querySelector('.trace-fold, .raw-fold');
        if (!details) {
            details = document.createElement('details');
            details.className = 'trace-fold';
            var summaryNode = document.createElement('summary');
            summaryNode.textContent = 'Details';
            details.append(summaryNode, document.createElement('pre'));
            bubble.appendChild(details);
        }
        var summaryEl = details.querySelector('summary');
        if (summaryEl && summaryEl.textContent === 'Raw payload') summaryEl.textContent = 'Details';
        var pre = details.querySelector('pre');
        if (!pre) return;
        var existing = pre.textContent.trim();
        if (details.classList.contains('raw-fold')) {
            pre.textContent = detailLines.join('\n') + (existing ? '\n\n' + existing : '');
        } else {
            pre.textContent = detailLines.join('\n');
        }
    }

    function relabelLastUser(text, expected) {
        var rows = document.querySelectorAll('#chat .msg-row.user .bubble');
        var last = rows[rows.length - 1];
        if (!last) return;
        if (expected && last.textContent !== expected) return;
        last.textContent = text;
    }

    function syncMode() {
        var box = document.querySelector('.input-box');
        var input = $('input');
        var search = $('btn-search');
        var image = $('btn-image');
        if (box) box.dataset.mode = mode;
        if (search) search.setAttribute('aria-pressed', mode === 'search' ? 'true' : 'false');
        if (image) image.setAttribute('aria-pressed', mode === 'image' ? 'true' : 'false');
        if (!input) return;
        if (mode === 'search') input.placeholder = 'What should I look up?';
        else if (mode === 'image') input.placeholder = 'Describe the picture you want';
        else input.placeholder = 'Ask in a sentence, or teach a fact…';
    }

    function forceMode(next) {
        mode = next || '';
        syncMode();
    }

    function toggleMode(next) {
        forceMode(mode === next ? '' : next);
        var input = $('input');
        if (input) input.focus();
    }

    function bindMenu(button, menu) {
        if (!button || !menu) return { close: function () {}, isOpen: function () { return false; } };
        function isOpen() { return !menu.hidden; }
        function close(focusBack) {
            menu.hidden = true;
            button.setAttribute('aria-expanded', 'false');
            if (focusBack) button.focus();
        }
        function open() {
            menu.hidden = false;
            button.setAttribute('aria-expanded', 'true');
            var first = menu.querySelector('[role="menuitem"]');
            if (first) first.focus();
        }
        button.addEventListener('click', function (event) {
            event.stopPropagation();
            if (isOpen()) close(false);
            else open();
        });
        menu.addEventListener('keydown', function (event) {
            var items = Array.prototype.slice.call(menu.querySelectorAll('[role="menuitem"]'));
            if (!items.length) return;
            var index = items.indexOf(document.activeElement);
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End' || event.key === 'Tab') {
                event.preventDefault();
                var next = index;
                if (event.key === 'ArrowDown' || (event.key === 'Tab' && !event.shiftKey)) next = (index + 1) % items.length;
                else if (event.key === 'ArrowUp' || (event.key === 'Tab' && event.shiftKey)) next = (index - 1 + items.length) % items.length;
                else if (event.key === 'Home') next = 0;
                else next = items.length - 1;
                items[next < 0 ? 0 : next].focus();
            } else if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                close(true);
            }
        });
        menu.addEventListener('click', function (event) {
            if (event.target.closest('[role="menuitem"]')) close(false);
        });
        document.addEventListener('click', function (event) {
            if (!isOpen()) return;
            if (button.contains(event.target) || menu.contains(event.target)) return;
            close(false);
        });
        return { close: close, isOpen: isOpen };
    }

    function slashMatches(text) {
        var trimmed = String(text || '');
        if (!/^\/\S*$/.test(trimmed)) return [];
        var token = trimmed.toLowerCase();
        return COMMANDS.filter(function (cmd) { return cmd.name.indexOf(token) === 0 || token === '/'; });
    }

    function renderSlash() {
        var pop = $('slash-popover');
        var input = $('input');
        if (!pop || !input) return;
        slashItems = slashMatches(input.value);
        slashIndex = Math.max(0, Math.min(slashIndex, slashItems.length - 1));
        pop.replaceChildren();
        if (!slashItems.length) {
            pop.hidden = true;
            input.removeAttribute('aria-activedescendant');
            input.setAttribute('aria-expanded', 'false');
            return;
        }
        pop.hidden = false;
        var box = document.querySelector('.input-box');
        if (box) {
            var rect = box.getBoundingClientRect();
            pop.style.left = Math.max(8, rect.left) + 'px';
            pop.style.width = Math.min(rect.width, window.innerWidth - 16) + 'px';
            pop.style.bottom = (window.innerHeight - rect.top + 8) + 'px';
            pop.style.right = 'auto';
        }
        input.setAttribute('aria-expanded', 'true');
        slashItems.forEach(function (cmd, index) {
            var option = document.createElement('button');
            option.type = 'button';
            option.className = 'slash-option';
            option.id = 'slash-opt-' + index;
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', index === slashIndex ? 'true' : 'false');
            var name = document.createElement('span');
            name.className = 'slash-name';
            name.textContent = cmd.name;
            var desc = document.createElement('span');
            desc.className = 'slash-desc';
            desc.textContent = cmd.description;
            option.append(name, desc);
            option.addEventListener('mousedown', function (event) { event.preventDefault(); });
            option.addEventListener('click', function () { applySlash(cmd); });
            pop.appendChild(option);
        });
        input.setAttribute('aria-activedescendant', 'slash-opt-' + slashIndex);
    }

    function applySlash(cmd) {
        var input = $('input');
        if (!input || !cmd) return;
        input.value = cmd.insert;
        if (cmd.name === '/search') forceMode('search');
        else forceMode('');
        if (typeof window.growComposer === 'function') window.growComposer();
        slashIndex = 0;
        renderSlash();
        input.focus();
    }

    function selectedFileActive() {
        var chip = $('file-chip');
        return chip && !chip.hidden;
    }

    function armStep(text) {
        var trimmed = String(text || '').trim().toLowerCase();
        if (mode === 'search' || trimmed.indexOf('/search') === 0) pendingStep = 'Searching the web...';
        else if (mode === 'image') pendingStep = 'Making an image...';
        else if (trimmed.indexOf('/tool') === 0) pendingStep = 'Running a tool...';
        else if (/^remember\b/.test(trimmed)) pendingStep = 'Saving a fact...';
        else pendingStep = 'Checking facts...';
    }

    function install() {
        var input = $('input');
        var pop = document.createElement('div');
        pop.id = 'slash-popover';
        pop.className = 'slash-popover';
        pop.hidden = true;
        pop.setAttribute('role', 'listbox');
        pop.setAttribute('aria-label', 'Shortcuts');
        document.body.appendChild(pop);
        if (input) {
            input.setAttribute('role', 'combobox');
            input.setAttribute('aria-autocomplete', 'list');
            input.setAttribute('aria-expanded', 'false');
            input.setAttribute('aria-controls', 'slash-popover');
            input.addEventListener('input', function () {
                slashIndex = 0;
                renderSlash();
            });
            input.addEventListener('keydown', function (event) {
                if (pop.hidden) return;
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    slashIndex = event.key === 'ArrowDown'
                        ? (slashIndex + 1) % slashItems.length
                        : (slashIndex - 1 + slashItems.length) % slashItems.length;
                    renderSlash();
                } else if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    applySlash(slashItems[slashIndex]);
                } else if (event.key === 'Tab' && slashItems[slashIndex]) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    applySlash(slashItems[slashIndex]);
                } else if (event.key === 'Escape') {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    pop.hidden = true;
                    input.setAttribute('aria-expanded', 'false');
                }
            }, true);
        }

        var search = $('btn-search');
        var image = $('btn-image');
        if (search) search.addEventListener('click', function () { toggleMode('search'); });
        if (image) image.addEventListener('click', function () { toggleMode('image'); });
        syncMode();

        var menu = bindMenu($('btn-more'), $('more-menu'));
        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') return;
            if (pop && !pop.hidden) {
                pop.hidden = true;
                if (input) input.setAttribute('aria-expanded', 'false');
                event.stopPropagation();
                return;
            }
            if (menu.isOpen()) {
                menu.close(true);
                event.stopPropagation();
            }
        }, true);

        var suggestions = $('suggestions');
        if (suggestions) {
            suggestions.addEventListener('click', function (event) {
                var item = event.target.closest('.suggestion');
                if (!item || !item.dataset.fill || !input) return;
                input.value = item.dataset.fill;
                forceMode(item.dataset.mode || '');
                if (typeof window.growComposer === 'function') window.growComposer();
                input.focus();
            });
        }

        if (typeof window.setTyping === 'function') {
            var previousTyping = window.setTyping;
            window.setTyping = function (bubble) {
                previousTyping(bubble);
                if (!pendingStep || !bubble) return;
                var live = document.createElement('p');
                live.className = 'step-live';
                live.setAttribute('aria-live', 'polite');
                live.textContent = pendingStep;
                bubble.insertBefore(live, bubble.firstChild);
            };
        }
        if (typeof window.renderReply === 'function') {
            var previousReply = window.renderReply;
            window.renderReply = function (bubble, data, opts) {
                var result = previousReply(bubble, data, opts);
                polishReply(bubble, data, opts);
                return result;
            };
        }
        if (typeof window.renderStructured === 'function') {
            var previousStructured = window.renderStructured;
            window.renderStructured = function (target, data, opts) {
                var result = previousStructured(target, data, opts);
                polishReply(target, data, opts);
                return result;
            };
        }
        if (typeof window.sendMsg === 'function') {
            var previousSend = window.sendMsg;
            window.sendMsg = function () {
                var field = $('input');
                var raw = field ? field.value : '';
                var trimmed = raw.trim();
                if (!trimmed && !selectedFileActive()) return previousSend();
                if (mode === 'image' && trimmed && !selectedFileActive() && trimmed.charAt(0) !== '/') {
                    field.value = '';
                    if (typeof window.growComposer === 'function') window.growComposer();
                    forceMode('');
                    pendingStep = 'Making an image...';
                    var forge = $('forge-prompt');
                    if (forge) forge.value = trimmed;
                    var send = $('send');
                    if (send) send.disabled = true;
                    var job = window.runStudio('Make an image', '/studio/forge/video', { prompt: trimmed, stage: 'draft' }, $('forge-result'));
                    relabelLastUser(trimmed, 'Make an image');
                    pendingStep = '';
                    Promise.resolve(job).finally(function () {
                        if (send) send.disabled = false;
                        if (field) field.focus();
                    });
                    return job;
                }
                if (mode === 'search' && trimmed && !selectedFileActive() && trimmed.charAt(0) !== '/') {
                    field.value = '/search ' + trimmed;
                }
                var wire = field ? field.value.trim() : trimmed;
                armStep(wire);
                var sent = previousSend();
                var searchText = wire.match(/^\/search\s+([\s\S]+)$/i);
                if (searchText && searchText[1].trim()) relabelLastUser(searchText[1].trim(), wire);
                forceMode('');
                pendingStep = '';
                return sent;
            };
            var sendBtn = $('send');
            if (sendBtn) {
                sendBtn.removeEventListener('click', previousSend);
                sendBtn.addEventListener('click', window.sendMsg);
            }
        }
        if (typeof window.runKinCycle === 'function') {
            var previousCycle = window.runKinCycle;
            window.runKinCycle = function () {
                pendingStep = 'Running a learning cycle...';
                var result = previousCycle.apply(this, arguments);
                relabelLastUser('Run a learning cycle', 'Running Kin cycle…');
                pendingStep = '';
                return result;
            };
        }
        if (typeof window.listCheckpoints === 'function') {
            var previousList = window.listCheckpoints;
            window.listCheckpoints = function () {
                pendingStep = 'Checking saved checkpoints...';
                var result = previousList.apply(this, arguments);
                relabelLastUser('Saved checkpoints', 'Listing Hades checkpoints…');
                pendingStep = '';
                return result;
            };
        }
        if (typeof window.runResidualCheck === 'function') {
            var previousResidual = window.runResidualCheck;
            window.runResidualCheck = function () {
                pendingStep = 'Checking consistency...';
                var result = previousResidual.apply(this, arguments);
                relabelLastUser('Check consistency', 'Calling tool residual_consistency…');
                pendingStep = '';
                return result;
            };
        }
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
    else install();
})();
