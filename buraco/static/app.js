'use strict';
// Card identities distinguish two copies of the same rank and suit.
function newlyAddedCards(previous, next, highlighted = new Set()) {
  if (!previous || !next || previous.active !== next.active || previous.turn !== next.turn || next.ended) return new Set();
  const before = new Set(previous.hand.map(card => card.id));
  return new Set(next.hand.filter(card => !before.has(card.id) || highlighted.has(card.id)).map(card => card.id));
}
if (typeof module !== 'undefined') module.exports = {newlyAddedCards};
if (typeof document !== 'undefined') {
const $ = id => document.getElementById(id);
let snapshot = {version: 0, game: null};
let selected = new Set();
let staged = [];
let busy = false;
let targetMeld = '';
let newCards = new Set();

function element(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = error ? 'error' : '';
  $('notice').hidden = !message;
}
async function request(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({...data, version: snapshot.version})
  });
  const result = await response.json();
  if (!response.ok) {
    if (result.game) { newCards = newlyAddedCards(snapshot.game, result.game, newCards); snapshot = result; selected.clear(); staged = []; render(); }
    throw new Error(result.error || 'The request could not be completed.');
  }
  return result;
}
function setDefaults(defaults) {
  for (const [name, value] of Object.entries(defaults)) {
    const input = $('setup-form').elements.namedItem(name);
    if (input.type === 'checkbox') input.checked = value;
    else input.value = value;
  }
}
async function move(command, confirmed = false) {
  if (busy) return;
  busy = true; updateActions();
  try {
    const result = await request('/api/command', {command, confirmed});
    newCards = newlyAddedCards(snapshot.game, result.game, newCards);
    snapshot = result;
    selected.clear(); staged = [];
    render(); notice(snapshot.message);
    if (snapshot.game.ended) $('result').scrollIntoView({behavior: 'smooth', block: 'start'});
  } catch (error) { notice(error.message, true); }
  finally { busy = false; updateActions(); }
}
function cardNode(card, selectable = false, top = false) {
  const cls = 'card' + (['h','d'].includes(card.suit) ? ' red' : '') + (!card.suit ? ' joker' : '') + (top ? ' top-card' : '');
  const node = element(selectable ? 'button' : 'div', cls);
  node.append(element('span', 'rank', card.suit ? card.rank : 'Jok'), element('span', 'suit', card.symbol), element('span', 'bottom', card.suit ? card.rank : '★'));
  let label = card.label;
  if (card.wild) { node.append(element('span', 'wild-badge', `as ${card.represents}`)); label += `, wild as ${card.represents}`; }
  if (top) node.append(element('span', 'top-label', 'TOP'));
  if (selectable && newCards.has(card.id)) {
    node.classList.add('new-card');
    node.append(element('span', 'new-card-badge', 'NEW'));
    label += ', newly added this turn';
  }
  node.setAttribute('aria-label', label);
  node.title = label;
  if (selectable) {
    node.type = 'button';
    node.id = `card-${card.id}`;
    node.setAttribute('aria-pressed', selected.has(card.id));
    node.classList.toggle('selected', selected.has(card.id));
    node.disabled = staged.some(group => group.includes(card.id)) || snapshot.game.ended || busy;
    node.addEventListener('click', () => {
      if (selected.has(card.id)) selected.delete(card.id); else selected.add(card.id);
      node.classList.toggle('selected', selected.has(card.id));
      node.setAttribute('aria-pressed', selected.has(card.id));
      updateActions();
    });
  }
  return node;
}
function scoreTable(game) {
  const table = element('table','score-table');
  const head = element('thead'); const header = element('tr');
  ['Scoring','Team 1','Team 2'].forEach(value => header.append(element('th','',value)));
  head.append(header); table.append(head);
  const body = element('tbody');
  for (const [key, label] of [['table_cards','Table cards'],['canastra_bonuses','Canastra bonuses'],['going_out','Going out'],['morto_penalty','Morto penalty'],['hand_penalty','Cards in hand'],['total','Total']]) {
    const row = element('tr'); row.append(element('td','',label));
    game.scores.forEach(score => row.append(element('td','',!game.ended && ['morto_penalty','hand_penalty'].includes(key) ? 'Pending' : score[key]))); body.append(row);
  }
  table.append(body); return table;
}
function renderHand() {
  $('hand-cards').replaceChildren(...snapshot.game.hand.map(c => cardNode(c, true)));
  $('new-card-hint').hidden = newCards.size === 0;
  $('staged-area').hidden = staged.length === 0;
  $('staged-groups').replaceChildren();
  staged.forEach((ids, index) => {
    const cards = ids.map(id => snapshot.game.hand.find(c => c.id === id));
    const group = element('div','staged-group');
    group.append(element('span','',`${index + 1}. ${cards.map(c => c.label).join(' ')}`));
    const remove = element('button','', '✕'); remove.setAttribute('aria-label', `Remove queued meld ${index + 1}`);
    remove.disabled = busy;
    remove.onclick = () => { staged.splice(index, 1); renderHand(); updateActions(); };
    group.append(remove); $('staged-groups').append(group);
  });
}
function updateActions() {
  const game = snapshot.game;
  if (!game) return;
  const play = game.phase === 'play' && !game.ended && !busy;
  const draw = game.phase === 'draw' && !game.ended && !busy;
  $('draw-button').disabled = !draw || !game.stock_count;
  $('take-button').disabled = !draw || !game.discard.length;
  $('queue-button').disabled = !play || selected.size < 3;
  $('meld-button').disabled = !play || (!staged.length && selected.size < 3) || (selected.size > 0 && selected.size < 3);
  const meldCount = staged.length + (selected.size ? 1 : 0);
  $('meld-button').textContent = staged.length ? `Play ${meldCount} meld${meldCount === 1 ? '' : 's'}` : 'Lay meld';
  const ownMelds = game.teams.find(team => team.number === game.team).melds;
  const hasTarget = ownMelds.some(meld => String(meld.id) === targetMeld);
  $('add-button').disabled = !play || !selected.size || !hasTarget || staged.length > 0;
  $('discard-button').disabled = !play || selected.size !== 1 || staged.length > 0;
  $('clear-button').disabled = busy || (!selected.size && !staged.length);
  document.querySelectorAll('#target-melds button').forEach(button => {
    button.disabled = busy || game.ended;
    button.setAttribute('aria-pressed', button.dataset.meldId === targetMeld);
  });
  $('add-hint').textContent = game.ended ? 'This hand has ended.'
    : !ownMelds.length ? 'Your team has no melds yet. Use Lay meld to create one.'
    : game.phase === 'draw' ? 'Draw from stock or take the discard pile before adding cards. You can choose a target now.'
    : staged.length ? 'Play or clear your queued melds before adding cards.'
    : !selected.size ? 'Select one or more cards from your hand.'
    : !hasTarget ? 'Choose one of your team’s melds below, then click Add cards.'
    : `Add your selected cards to meld #${targetMeld}.`;
  $('quit-button').disabled = busy || game.ended;
  $('confirm-quit').disabled = busy;
  $('new-button').disabled = busy;
  $('selection-hint').textContent = selected.size ? `${selected.size} card${selected.size === 1 ? '' : 's'} selected · ${selectedCards().reduce((n,c) => n + c.points, 0)} card points` : 'Select cards to create a meld, extend one, or discard.';
  document.querySelectorAll('#hand-cards button').forEach(node => {
    const id = Number(node.id.slice(5));
    node.disabled = busy || game.ended || staged.some(group => group.includes(id));
  });
}
function selectedCards() { return snapshot.game.hand.filter(c => selected.has(c.id)); }
function selectors(ids) { return ids.map(id => snapshot.game.hand.find(c => c.id === id).selector).join(' '); }
function render() {
  const game = snapshot.game;
  $('setup').hidden = !!game; $('game').hidden = !game;
  if (!game) return;
  $('turn-label').textContent = `HAND 01 / TURN ${String(game.turn).padStart(2,'0')}`;
  $('active-label').textContent = game.ended ? 'The hand is complete.' : `Your move, Player ${game.active}.`;
  $('phase-label').textContent = game.ended ? game.end_reason : `Team ${game.team} · ${game.phase === 'draw' ? 'Draw from stock or take the discard pile.' : 'Build your melds, then discard to finish your turn.'}`;
  $('hand-label').textContent = `PLAYER ${game.active} / TEAM ${game.team}`;
  $('hand-count').textContent = `${game.hand.length} in hand`;
  $('players').replaceChildren(...game.players.map(player => {
    const node = element('div','player' + (player.player === game.active ? ' active' : ''));
    const detail = element('div','player-details');
    detail.append(element('span','',`Player ${player.player}`), element('small','',`Team ${player.team}`));
    node.append(element('span','avatar',player.player),detail,element('span','count',`${player.count} cards`));
    return node;
  }));
  $('stock-count').textContent = `${game.stock_count} cards`;
  $('discard-count').textContent = ` / ${game.discard.length}`;
  $('discard-cards').replaceChildren(...game.discard.map((c,i) => cardNode(c,false,i === game.discard.length - 1)));
  if (!game.discard.length) $('discard-cards').append(element('p','table-hint','The discard pile is empty.'));
  $('discard-cards').scrollLeft = $('discard-cards').scrollWidth;
  $('mortos').replaceChildren(...game.mortos.map((status,i) => element('span','',`Morto ${i + 1} · ${status}`)));
  $('progress-count').textContent = `No progress ${game.no_progress}/${game.rules.no_progress_turn_limit}`;
  if (!game.teams.find(team => team.number === game.team).melds.some(meld => String(meld.id) === targetMeld)) targetMeld = '';
  $('target-melds').replaceChildren();
  game.teams.forEach(team => {
    $(`team${team.number}-status`).textContent = team.opened ? 'Opening complete' : team.vulnerable ? `Vulnerable · ${game.rules.vulnerability_minimum_meld} to open` : 'Ready to open';
    const container = $(`team${team.number}-melds`); container.replaceChildren();
    if (!team.melds.length) container.append(element('p','empty-melds','Your next canastra starts here.'));
    team.melds.forEach(meld => {
      const node = element('div','meld'); const title = element('div','meld-title');
      title.append(element('span','',`#${meld.id} · ${meld.kind === 'ace_set' ? 'Aces' : 'Run'}`),element('span',meld.status === 'Clean canastra' ? 'clean' : '', `${meld.status} · ${meld.card_points + meld.bonus} pts`));
      const cards = element('div','card-strip'); cards.append(...meld.cards.map(c => cardNode(c)));
      node.append(title,cards); container.append(node);
      if (team.number === game.team) {
        const target = element('button', 'meld-target', `#${meld.id} · ${meld.cards.map(c => c.label).join(' ')}`);
        target.type = 'button';
        target.dataset.meldId = String(meld.id);
        target.setAttribute('aria-label', `Choose meld ${meld.id}: ${meld.cards.map(c => c.label).join(' ')}`);
        target.onclick = () => { targetMeld = String(meld.id); updateActions(); };
        $('target-melds').append(target);
      }
    });
  });
  $('live-score-title').textContent = game.ended ? 'Final score' : 'Table points';
  $('live-score-hint').textContent = game.ended ? 'Includes card points, bonuses, and all penalties.' : 'Cards and canastras on the table. Hand and morto penalties apply at hand end.';
  $('live-scores').replaceChildren(...game.scores.map((score,i) => {
    const node = element('div','score-tile'); node.append(element('span','',`Team ${i+1}`),element('strong','',score.total)); return node;
  }));
  $('events').replaceChildren(...game.events.slice(-5).reverse().map(event => element('li','',event)));
  $('result').hidden = !game.ended;
  $('quit-button').hidden = game.ended; $('new-button').hidden = !game.ended;
  $('winner').textContent = game.winner || ''; $('end-reason').textContent = game.end_reason || '';
  $('final-score').replaceChildren(scoreTable(game)); $('score-detail').replaceChildren(scoreTable(game));
  renderHand(); updateActions();
}

$('setup-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  busy = true; $('start-button').disabled = true;
  const form = $('setup-form'); const rules = {};
  for (const [name,value] of Object.entries(snapshot.defaults)) {
    const input = form.elements.namedItem(name);
    rules[name] = typeof value === 'boolean' ? input.checked : Number(input.value);
  }
  try {
    snapshot = await request('/api/start',{rules,prior_scores:[Number(form.elements.score1.value),Number(form.elements.score2.value)],seed:form.elements.seed.value.trim() || null});
    selected.clear(); staged = []; targetMeld = ''; newCards.clear(); render(); notice('Cards dealt. Player 1 begins.'); window.scrollTo(0,0);
  } catch(error) { notice(error.message,true); }
  finally { busy = false; $('start-button').disabled = false; updateActions(); }
});
$('draw-button').onclick = () => move('draw stock');
$('take-button').onclick = () => move('take discard');
$('queue-button').onclick = () => { staged.push([...selected]); selected.clear(); renderHand(); updateActions(); };
$('meld-button').onclick = () => { const groups = [...staged]; if (selected.size) groups.push([...selected]); move('meld ' + groups.map(selectors).join(' | ')); };
$('add-button').onclick = () => move(`add ${selectors([...selected])} to ${targetMeld}`);
$('discard-button').onclick = () => move(`discard ${selectors([...selected])}`);
$('clear-button').onclick = () => { selected.clear(); staged = []; renderHand(); updateActions(); };
$('help-button').onclick = () => $('help-dialog').showModal();
$('score-button').onclick = () => $('score-dialog').showModal();
$('quit-button').onclick = () => $('quit-dialog').showModal();
$('confirm-quit').onclick = () => { $('quit-dialog').close(); move('quit',true); };
$('new-button').onclick = () => { $('game').hidden = true; $('setup').hidden = false; notice('Set your options for the next hand.'); window.scrollTo(0,0); };
document.querySelectorAll('[data-close]').forEach(button => button.onclick = () => $(button.dataset.close).close());
request('/api/state').then(result => { snapshot = result; setDefaults(result.defaults); render(); }).catch(error => notice(`Cannot reach the game server. ${error.message} Keep the Python server running and refresh.`,true));
}
