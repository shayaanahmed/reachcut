// Shared by the library preview and deterministic video renderer.
const stage = document.querySelector('.st');
const grid = document.getElementById('grid');
grid.dataset.t = DATA.theme;
stage.style.cssText = DATA.design.style;
if (DATA.design.id === 'code-editor') stage.style.setProperty('--bg', '#6a3df5');
if (DATA.design.id === 'bento-stats') stage.style.setProperty('--caption-fg', '#fff');
if (DATA.design.id === 'game-hud') {
  stage.style.backgroundColor = '#1a1033';
  stage.style.backgroundImage = 'linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px)';
  stage.style.backgroundSize = '1em 1em';
}
if (DATA.design.id === 'blueprint') {
  stage.style.backgroundColor = '#0f3d7a';
  stage.style.backgroundImage = 'linear-gradient(rgba(255,255,255,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.08) 1px,transparent 1px)';
  stage.style.backgroundSize = '1.2em 1.2em';
}
stage.innerHTML = DATA.design.markup;
if (DATA.design.id === 'copy-command') {
  stage.querySelector('.fo').parentElement.style.width = '5.4em';
}

if (DATA.design.id === 'trading-card') {
  const panel = stage.querySelector('.flip>div');
  // The reference's star font also multiplied its 8em height; retain the intended card proportions.
  panel.children[1].style.height = `${8*parseFloat(getComputedStyle(panel).fontSize)}px`;
}
const read = path => path.split('.').reduce((value, key) => value?.[key], DATA.content) ?? '';
if (!DATA.sample) {
  if (DATA.design.bindings) {
    stage.querySelectorAll('[data-to]').forEach(node => node.removeAttribute('data-to'));
  }
  // Never carry illustrative measurements, rankings or fake poll votes into a story.
  for (const [selector, path] of DATA.bindings) {
    const textOnly = selector.endsWith('::text');
    for (const node of stage.querySelectorAll(selector.replace('::text', ''))) {
      if (textOnly) {
        const textNode = [...node.childNodes].find(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim());
        if (textNode) textNode.textContent = read(path);
      } else node.textContent = read(path);
      node.classList.add('bound');
      node.removeAttribute('data-to');
    }
  }
  if (DATA.design.id === 'code-editor') {
    stage.querySelectorAll('.type').forEach((node, i) => {
      node.textContent = DATA.content.items[i]?.body ?? '';
      node.classList.add('bound');
    });
  }
  stage.querySelectorAll('.type.bound').forEach(node => node.style.setProperty('--w', '100%'));
  // Replace a typing indicator's fixed width with space for the bound story copy.
  stage.querySelectorAll('.bb').forEach(node => {
    if (!node.querySelector('.bound')) return;
    node.style.width = 'fit-content';
    node.style.maxWidth = '80%';
    node.style.alignSelf = node.classList.contains('me') ? 'flex-end' : 'flex-start';
  });
  stage.querySelectorAll('.bb + .card .mono').forEach(node => {
    node.style.display = 'flex';
    node.style.flexWrap = 'wrap';
    node.style.columnGap = '.4em';
  });
  if (DATA.design.id === 'comment-section') {
    stage.querySelectorAll('.sl>span').forEach(node => node.remove());
  }
  if (DATA.design.id === 'settings-toggles') {
    stage.querySelectorAll('.tg').forEach((node, i) => {
      node.classList.toggle('on', DATA.content.items[i]?.body?.toLowerCase() === 'on');
    });
  }
  if (DATA.design.id === 'stock-ticker') {
    // Keep the visual motif without suggesting unsupported growth data.
    stage.querySelector('svg path').setAttribute('d', 'M2 20H98');
  }
  if (DATA.design.id === 'contributors') {
    stage.querySelectorAll('.av').forEach((node, i, nodes) => {
      node.textContent = i === nodes.length - 1 ? read('items.0.body') : String.fromCharCode(65+i);
    });
  }
  if (['leaderboard', 'language-bar', 'trading-card', 'speed-dial', 'story-poll'].includes(DATA.design.id)) {
    // Without sourced numeric fields, marks remain schematic and never imply a score.
    stage.querySelectorAll('[data-to]').forEach(node => node.remove());
    stage.querySelectorAll('.sx,.bar2 i').forEach(node => {
      node.style.width = '100%';
      node.style.flex = '1';
      node.style.opacity = '.35';
    });
  }
}
const caption = document.createElement('div');
caption.className = 'cp';
const text = DATA.sample ? DATA.design.caption : DATA.content.caption;
let wordIndex = 0;
for (const match of text.matchAll(/\[([^\]]+)\]|(\S+)/g)) {
  const highlight = Boolean(match[1]);
  for (const word of (match[1] || match[2]).split(' ')) {
    const span = document.createElement('span');
    span.className = `w${highlight ? ' k' : ''}`;
    span.style.animationDelay = `${0.3 + wordIndex++ * 0.22}s`;
    span.textContent = word;
    caption.append(span, ' ');
  }
}
stage.append(caption);
// Metric-sized type cannot safely hold prose. Reserve a fixed card area above
// the caption and fit each value independently, without splitting words.
if (!DATA.sample && DATA.design.id === 'bento-stats') {
  const panel = stage.querySelector('.a');
  panel.style.bottom = '28%';
  panel.style.gridTemplateColumns = 'minmax(0,1fr) minmax(0,1fr)';
  panel.style.gridTemplateRows = '1fr 1.2fr auto';
  for (const card of panel.children) {
    card.style.minHeight = '0';
    card.style.minWidth = '0';
    card.style.display = 'flex';
    card.style.flexDirection = 'column';
    card.style.gap = '5px';
    if (card.children.length === 2) {
      const value = card.lastElementChild;
      value.style.flex = '1';
      value.style.minHeight = '0';
      value.style.lineHeight = '1.15';
      value.style.overflowWrap = 'normal';
      value.dataset.fitBox = 'true';
    }
  }
}
function resize() {
  document.getElementById('viewport').style.transform = `scale(${Math.min(innerWidth/270,innerHeight/480)})`;
}
addEventListener('resize', resize);
resize();
const counters = [...stage.querySelectorAll('[data-to]')];
const format = (value, suffix='') => (value >= 1000 ? (value/1000).toFixed(1)+'K' : Math.round(value)) + suffix;
function counterAt(seconds) {
  for (const node of counters) {
    const p = Math.max(0, Math.min(1, seconds/1.4));
    node.textContent = format(Number(node.dataset.to)*(1-(1-p)**3), node.dataset.sf);
  }
}
let tick;
window.renderAt = seconds => {
  cancelAnimationFrame(tick);
  for (const animation of document.getAnimations()) {
    animation.pause();
    animation.currentTime = seconds * 1000;
  }
  counterAt(seconds);
};
window.layoutIssues = () => {
  const issues = [];
  for (const node of stage.querySelectorAll('.bound,.cp')) {
    if (node.closest('.mq')) continue; // Ticker intentionally travels through a clipped window.
    const rect = node.getBoundingClientRect();
    const bounds = stage.getBoundingClientRect();
    if (rect.right > bounds.right+1 || rect.bottom > bounds.bottom+1 || rect.left < bounds.left-1 || rect.top < bounds.top-1) {
      issues.push('Shorten visible text: '+node.textContent);
    }
  }
  for (const node of stage.querySelectorAll('[data-fit-box]')) {
    const rect = node.getBoundingClientRect();
    const captionRect = caption.getBoundingClientRect();
    if (node.scrollHeight > node.clientHeight+1 || node.scrollWidth > node.clientWidth+1 || rect.bottom > captionRect.top-8) {
      issues.push('Shorten card text to avoid clipping or caption overlap: '+node.textContent);
    }
  }
  for (const node of stage.querySelectorAll('.bb .bound,.card [data-copy].bound')) {
    const textNode = node.firstChild;
    if (!textNode || textNode.nodeType !== Node.TEXT_NODE) continue;
    for (const word of textNode.textContent.matchAll(/[A-Za-z0-9][A-Za-z0-9'-]*/g)) {
      const range = document.createRange();
      range.setStart(textNode, word.index);
      range.setEnd(textNode, word.index + word[0].length);
      if (range.getClientRects().length > 1) issues.push('Avoid breaking words in cards: '+word[0]);
    }
    const parent = node.closest('.bb,.card');
    const rect = node.getBoundingClientRect(), box = parent.getBoundingClientRect();
    if (rect.right > box.right+1 || rect.bottom > box.bottom+1 || rect.left < box.left-1) {
      issues.push('Shorten text to fit its card: '+node.textContent);
    }
  }
  return issues;
};
// Fit dynamic copy inside each original design instead of changing its layout.
window.renderAt(5);
for (const node of stage.querySelectorAll('.bound')) {
  if (node.closest('.mq')) { node.style.paddingRight = '2em'; continue; }
  let size = parseFloat(getComputedStyle(node).fontSize);
  const card = node.hasAttribute('data-copy') ? node.closest('.bb,.card') : null;
  const tooWide = () => node.scrollWidth > node.clientWidth+1 || node.getBoundingClientRect().right > 267 || (card && node.getBoundingClientRect().right > card.getBoundingClientRect().right+1);
  while (size > (node.dataset.fitBox ? 14 : 8) && (tooWide() || (node.dataset.fitBox && node.scrollHeight > node.clientHeight+1))) {
    node.style.fontSize = `${--size}px`;
  }
}
function play() {
  cancelAnimationFrame(tick);
  for (const animation of document.getAnimations()) {
    animation.currentTime = 0;
    animation.play();
  }
  const start = performance.now();
  const update = now => {
    counterAt((now-start)/1000);
    if (now-start < 1500) tick = requestAnimationFrame(update);
  };
  tick = requestAnimationFrame(update);
}
stage.addEventListener('click', play);
stage.addEventListener('keydown', event => {
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); play(); }
});
play();
