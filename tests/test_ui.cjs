const test = require('node:test');
const assert = require('node:assert/strict');
const {newlyAddedCards} = require('../buraco/static/app.js');

const hand = (ids, options = {}) => ({active: 1, turn: 1, ended: false,
  hand: ids.map(id => ({id})), ...options});

test('stock draw marks only the new physical copy', () => {
  assert.deepEqual([...newlyAddedCards(hand([1, 2]), hand([1, 2, 54]))], [54]);
});
test('discard pickup marks every new card', () => {
  assert.deepEqual([...newlyAddedCards(hand([1]), hand([1, 2, 3, 4]))], [2, 3, 4]);
});
test('playing cards retains highlights on remaining new cards', () => {
  assert.deepEqual([...newlyAddedCards(hand([1, 2, 3]), hand([1, 3]), new Set([2, 3]))], [3]);
});
test('taking a morto by melding marks the replacement hand', () => {
  assert.deepEqual([...newlyAddedCards(hand([1, 2, 3]), hand([4, 5, 6]))], [4, 5, 6]);
});
test('the next player does not get the previous turn highlights', () => {
  assert.equal(newlyAddedCards(hand([1]), hand([2, 3], {active: 2, turn: 2}), new Set([1])).size, 0);
});
test('returning to the same player on a later turn clears highlights', () => {
  assert.equal(newlyAddedCards(hand([1]), hand([1, 2], {turn: 5}), new Set([1])).size, 0);
});
test('initial deals and finished hands have no new-card highlights', () => {
  assert.equal(newlyAddedCards(null, hand([1, 2])).size, 0);
  assert.equal(newlyAddedCards(hand([1]), hand([1, 2], {ended: true}), new Set([1])).size, 0);
});
