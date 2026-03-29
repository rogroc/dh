export class ArqueoRender {
    constructor() {
        this.notesData = {};
        this.idToLevel = {};
        this.lockedIds = [];
        this.currentPopupIds = "";
    }

    async init(notesJsonPath) {
        try {
            const response = await fetch(notesJsonPath);
            this.notesData = await response.json();
            // Solidifiquem colors de notes.json per garantir contrast acadèmic
            Object.keys(this.notesData).forEach(id => {
                let c = this.notesData[id].color;
                if (c && c.includes('rgba')) this.notesData[id].color = c.replace(/0\.\d+\)/, '1.0)');
            });
        } catch (e) { console.error("Error carregant notes:", e); }
    }

    render(text, containerId) {
        // Renderitzat de Markdown bàsic tal com està a l'offline
        const html = text.replace(/^# (.*)/gm, '<h1>$1</h1>').replace(/^## (.*)/gm, '<h2>$1</h2>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n\n/g, '</p><p>');
        document.getElementById(containerId).innerHTML = `<p>${this.processStratigraphy(html)}</p>`;
        this.attachEvents(containerId);
    }

    processStratigraphy(html) {
        const markerRegex = /<m-(start|end)\s+id=["'](.*?)["']>/g;
        let parts = [], lastIndex = 0, match;
        while ((match = markerRegex.exec(html)) !== null) {
            parts.push({ type: 'text', content: html.substring(lastIndex, match.index) });
            parts.push({ type: match[1], id: match[2] });
            lastIndex = match.index + match[0].length;
        }
        parts.push({ type: 'text', content: html.substring(lastIndex) });
        const noteIntervals = {}; let cursor = 0;
        parts.forEach(p => {
            if (p.type === 'start') noteIntervals[p.id] = { start: cursor, end: 9999999 };
            if (p.type === 'end' && noteIntervals[p.id]) noteIntervals[p.id].end = cursor;
            if (p.type === 'text') cursor += p.content.length;
        });
        const sortedIds = Object.keys(noteIntervals).sort((a,b) => noteIntervals[a].start - noteIntervals[b].start);
        const levelOccupiedUntil = [];
        sortedIds.forEach(id => {
            let lvl = 0; while (levelOccupiedUntil[lvl] > noteIntervals[id].start) { lvl++; }
            this.idToLevel[id] = lvl; levelOccupiedUntil[lvl] = noteIntervals[id].end;
        });
        let result = "", activeIds = [];
        parts.forEach(part => {
            if (part.type === 'start') activeIds.push(part.id);
            else if (part.type === 'end') activeIds = activeIds.filter(id => id !== part.id);
            else {
                if (activeIds.length > 0) result += `<span class="layer-base" data-ids="${activeIds.join(',')}">${part.content}</span>`;
                else result += part.content;
            }
        });
        return result;
    }

    getOffset(level) {
        if (level === 0) return { x: 0, y: 0 };
        const magnitude = Math.ceil(level / 2);
        const direction = (level % 2 === 1) ? 1 : -1;
        return { x: magnitude * direction, y: magnitude * direction };
    }

    updateView(triggerIds, containerId) {
        const allLayers = document.querySelectorAll('.layer-base');
        const popup = document.getElementById('popup-container');
        allLayers.forEach(el => { el.style.backgroundColor = "transparent"; el.style.backgroundImage = "none"; });
        const effectiveIds = this.lockedIds.length > 0 ? this.lockedIds : triggerIds;
        const idsKey = effectiveIds.sort().join(',');
        if (effectiveIds.length === 0) { if(popup) popup.innerHTML = ''; this.currentPopupIds = ""; return; }
        if (popup && (this.currentPopupIds !== idsKey || this.lockedIds.length > 0)) {
            popup.innerHTML = '';
            effectiveIds.forEach(id => {
                const n = this.notesData[id]; if (!n) return;
                const card = document.createElement('div'); card.className = 'note-card visible';
                card.innerHTML = `<div class="tag-ref">${n.doc_ref}</div><h4>${n.titol}</h4><p>${n.explicacio}</p>`;
                popup.appendChild(card);
            });
            this.currentPopupIds = idsKey;
        }
        allLayers.forEach(el => {
            const elIds = el.getAttribute('data-ids').split(',');
            const activeInSpan = elIds.filter(id => effectiveIds.includes(id) && this.notesData[id]);
            if (activeInSpan.length > 0) {
                const newestFirst = activeInSpan.sort((a,b) => (this.idToLevel[b] - this.idToLevel[a]));
                let bgs = [], poss = [];
                newestFirst.forEach(id => {
                    const col = this.notesData[id].color;
                    const off = this.getOffset(this.idToLevel[id]);
                    bgs.push(`linear-gradient(${col}, ${col})`);
                    poss.push(`${off.x}px ${off.y}px`);
                });
                el.style.backgroundImage = bgs.join(',');
                el.style.backgroundPosition = poss.join(',');
                el.style.backgroundRepeat = "no-repeat";
                el.style.backgroundSize = "100% 100%";
                const baseId = activeInSpan.reduce((min, id) => (this.idToLevel[id] < this.idToLevel[min]) ? id : min, activeInSpan[0]);
                el.style.backgroundColor = this.notesData[baseId].color;
            }
        });
    }

    attachEvents(containerId) {
        const content = document.getElementById(containerId);
        content.onmouseover = e => { const target = e.target.closest('.layer-base'); if (target && this.lockedIds.length === 0) this.updateView(target.getAttribute('data-ids').split(','), containerId); };
        content.onmousemove = e => { const target = e.target.closest('.layer-base'); if (target && this.lockedIds.length === 0) {
            const ids = target.getAttribute('data-ids').split(',');
            if (ids.sort().join(',') !== this.currentPopupIds) this.updateView(ids, containerId);
        }};
        content.onmouseout = e => { if ((!e.relatedTarget || !e.relatedTarget.closest('.layer-base')) && this.lockedIds.length === 0) this.updateView([], containerId); };
        content.onclick = e => {
            const target = e.target.closest('.layer-base');
            if (target) {
                const ids = target.getAttribute('data-ids').split(',');
                this.lockedIds = (this.lockedIds.sort().join(',') === ids.sort().join(',')) ? [] : ids;
                this.updateView(this.lockedIds, containerId);
            } else { this.lockedIds = []; this.updateView([], containerId); }
        };
    }
}
