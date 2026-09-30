import copy
import random
import unittest

from buraco.config import Rules
from buraco.engine import Game, RuleError, make_deck, validate_meld


def cards(text, jokers=True):
    available = make_deck(jokers)
    result = []
    for selector in text.split():
        card = next(c for c in available if c.selector.lower() == selector.lower())
        available.remove(card)
        result.append(card)
    return result


def position(hand, *, phase="play", rules=None, prior_scores=(0, 0),
             melds=(), stock=None, mortos=("available", "available"), took=False, other_hands=None):
    """Create a controlled, conserved full-deck scenario for transition tests."""
    game = Game(rules, prior_scores, seed="fixture")
    available = list(game.deck)

    def take(text):
        result = []
        for selector in text.split():
            card = next(c for c in available if c.selector.lower() == selector.lower())
            available.remove(card)
            result.append(card)
        return result

    game.hands = [take(hand), [], [], []]
    for index, text in (other_hands or {}).items():
        game.hands[index] = take(text)
    game.teams[0].melds = [validate_meld(take(text), i + 1) for i, text in enumerate(melds)]
    game.teams[0].opened = bool(melds)
    game.teams[0].took_morto = took
    game.next_meld_id = len(melds) + 1
    game.morto_states = list(mortos)
    specified_stock = take(stock) if stock is not None else None
    game.mortos = []
    for state in mortos:
        game.mortos.append([available.pop() for _ in range(11)] if state == "available" else [])
    game.stock = available[:] if stock is None else specified_stock
    game.discard = [] if stock is None else available[:]
    game.phase = phase
    game.assert_conserved()
    return game


class MeldTests(unittest.TestCase):
    def test_natural_two_preferred_then_reassigned(self):
        meld = validate_meld(cards("2h 3h 4h"))
        self.assertIsNone(meld.wild_id)
        self.assertEqual(meld.status, "Meld")
        extended = validate_meld(cards("2h 3h 4h 6h"))
        self.assertEqual([c.selector for c in extended.cards], ["3h", "4h", "2h", "6h"])
        self.assertIsNotNone(extended.wild_id)
        self.assertEqual(extended.status, "Meld")

    def test_dirty_canastra_can_be_cleaned(self):
        dirty = validate_meld(cards("2h 4h 5h 6h 7h 8h 9h"))
        self.assertEqual(dirty.status, "Dirty canastra")
        clean = validate_meld(cards("2h 3h 4h 5h 6h 7h 8h 9h"))
        self.assertEqual(clean.status, "Clean canastra")

    def test_one_wild_and_one_natural_two(self):
        meld = validate_meld(cards("2h 2h 3h 5h"))
        self.assertIsNotNone(meld.wild_id)
        for text in ("2s 2c 4h", "Jok Jok ah", "2s 2c ah ad"):
            with self.subTest(text=text), self.assertRaises(RuleError):
                validate_meld(cards(text))

    def test_all_aces_plus_one_wild(self):
        meld = validate_meld(cards("as as ah ah ad ad ac ac 2h"))
        self.assertEqual(meld.kind, "ace_set")
        self.assertEqual(meld.status, "Dirty canastra")
        self.assertEqual(validate_meld(cards("as as Jok")).kind, "ace_set")

    def test_ace_high_and_full_ace_to_ace(self):
        self.assertEqual(validate_meld(cards("qh kh ah")).start, 12)
        self.assertEqual(validate_meld(cards("qh 2c ah")).start, 12)
        full = "ah 2h 3h 4h 5h 6h 7h 8h 9h 10h jh qh kh ah"
        meld = validate_meld(cards(full))
        self.assertEqual(meld.start, 1)
        self.assertEqual(meld.bonus(Rules()), 200)
        self.assertEqual(meld.bonus(Rules(allow_a_to_a_clean_canastra=True)), 1000)
        with self.assertRaises(RuleError):
            validate_meld(cards("kh ah 2h 3h"))

    def test_special_bonus_replaces_ordinary(self):
        meld = validate_meld(cards("ah 2h 3h 4h 5h 6h 7h 8h 9h 10h jh qh kh"))
        self.assertEqual(meld.bonus(Rules()), 200)
        self.assertEqual(meld.bonus(Rules(allow_a_to_k_clean_canastra=True)), 500)

    def test_duplicates_mixed_suits_and_wrong_sets(self):
        for text in ("3h 4h 5s", "3h 3h 4h", "kh kh kc", "ah ad", "ah ah 3h"):
            with self.subTest(text=text), self.assertRaises(RuleError):
                validate_meld(cards(text))


class GameTests(unittest.TestCase):
    def unchanged_after(self, game, command):
        before = copy.deepcopy(game.__dict__)
        rng_state = game.rng.getstate()
        with self.assertRaises(RuleError):
            game.execute(command)
        before.pop("rng")
        after = dict(game.__dict__)
        after.pop("rng")
        self.assertEqual(before, after)
        self.assertEqual(rng_state, game.rng.getstate())

    def test_seed_deal_sizes_and_conservation(self):
        game = Game(seed="repeat")
        self.assertEqual(game.view(), Game(seed="repeat").view())
        self.assertEqual([len(h) for h in game.hands], [11] * 4)
        self.assertEqual([len(m) for m in game.mortos], [11, 11])
        self.assertEqual(len(game.stock), 37)
        self.assertEqual(len(Game(Rules(use_jokers=True)).stock), 41)
        game.assert_conserved()

    def test_draw_required_and_once_only(self):
        game = position("3h 4h 5h 6h", phase="draw")
        for command in ("meld 3h 4h 5h", "add 6h to 1", "discard 6h"):
            self.unchanged_after(game, command)
        game.execute("DRAW STOCK")
        self.unchanged_after(game, "draw stock")
        self.unchanged_after(game, "take discard")

    def test_entire_discard_no_immediate_meld_requirement(self):
        game = position("3h 4h", phase="draw", stock="as")
        expected = len(game.discard) + 2
        game.execute("take discard")
        self.assertEqual(len(game.hands[0]), expected)
        self.assertFalse(game.discard)
        game.execute("discard 3h")
        self.assertEqual(game.active, 1)

    def test_empty_discard_is_rejected(self):
        game = position("3h 4h", phase="draw")
        self.unchanged_after(game, "take discard")

    def test_multiple_melds_atomic_and_duplicate_selection(self):
        game = position("3h 4h 5h as as ad 9h")
        self.unchanged_after(game, "meld 3h 4h 5h | as ad 9h")
        self.unchanged_after(game, "meld 3h 4h 5h | 3h 4h 5h")
        game.execute("meld 3H 4H 5h | AS as ad")
        self.assertEqual(len(game.team.melds), 2)
        self.assertEqual([c.selector for c in game.hands[0]], ["9h"])

    def test_vulnerable_opening_combined_and_fixed(self):
        game = position("3h 4h 5h as ah ad 8s 9s 10s kh", prior_scores=(1500, 0))
        self.unchanged_after(game, "meld as ah ad")
        game.execute("meld as ah ad | 8s 9s 10s")
        self.assertTrue(game.team.opened)
        game.execute("meld 3h 4h 5h")
        self.assertTrue(game.vulnerable(0))
        self.assertFalse(position("as", prior_scores=(1499, 0)).vulnerable(0))

    def test_add_multiple_and_rearrange(self):
        game = position("6h 7h 9s", melds=("2h 3h 4h",))
        game.execute("add 6h 7h to 1")
        self.assertEqual(len(game.team.melds[0].cards), 5)
        self.assertIsNotNone(game.team.melds[0].wild_id)
        self.unchanged_after(game, "add 9s to 1")
        self.unchanged_after(game, "add 9s to 999")

    def test_cannot_add_to_opponents_meld(self):
        game = position("6h 9s", melds=("3h 4h 5h",))
        game.teams[1].melds = game.teams[0].melds
        game.teams[0].melds = []
        self.unchanged_after(game, "add 6h to 1")

    def test_direct_morto_continues_same_turn(self):
        game = position("3h 4h 5h")
        game.execute("meld 3h 4h 5h")
        self.assertEqual(len(game.hands[0]), 11)
        self.assertEqual(game.active, 0)
        self.assertEqual(game.phase, "play")
        self.assertTrue(game.team.took_morto)
        self.assertEqual(game.morto_states[0], "taken by Team 1")
        game.execute("discard " + game.hands[0][0].selector)
        self.assertEqual(game.active, 1)

    def test_indirect_morto_ends_turn(self):
        game = position("3h")
        game.execute("discard 3h")
        self.assertEqual(len(game.hands[0]), 11)
        self.assertEqual(game.active, 1)
        self.assertEqual(game.phase, "draw")

    def test_cannot_empty_without_clean_canastra(self):
        game = position("3h 4h 5h", took=True)
        self.unchanged_after(game, "meld 3h 4h 5h")
        game = position("2h", took=True)
        self.unchanged_after(game, "discard 2h")

    def test_final_meld_itself_qualifies_for_go_out(self):
        game = position("2h 3h 4h 5h 6h 7h 8h", took=True)
        game.execute("meld 2h 3h 4h 5h 6h 7h 8h")
        self.assertTrue(game.ended)
        self.assertEqual(game.scores()[0]["table_cards"], 45)
        self.assertEqual(game.scores()[0]["canastra_bonuses"], 200)
        self.assertEqual(game.scores()[0]["going_out"], 100)
        self.assertEqual(game.scores()[0]["total"], 345)

    def test_add_can_clean_and_go_out(self):
        game = position("3h", melds=("2h 4h 5h 6h 7h 8h 9h",), took=True)
        game.execute("add 3h to 1")
        self.assertTrue(game.ended)
        self.assertEqual(game.team.melds[0].status, "Clean canastra")

    def test_go_out_without_morto_when_none_available(self):
        game = position("2s", melds=("2h 3h 4h 5h 6h 7h 8h",), mortos=("moved to stock", "taken by Team 2"))
        game.execute("discard 2s")
        self.assertTrue(game.ended)
        self.assertEqual(game.scores()[0]["morto_penalty"], -100)
        self.assertEqual(game.scores()[0]["going_out"], 100)

    def test_joker_final_discard_and_clean_requirement_option(self):
        game = position("Jok", rules=Rules(use_jokers=True, require_clean_canastra_to_go_out=False), took=True)
        game.execute("discard jOk")
        self.assertTrue(game.ended)

    def test_last_draw_claims_morto_before_replenishment(self):
        game = position("3h 4h", phase="draw", stock="5h", mortos=("taken by Team 2", "available"))
        game.execute("draw stock")
        self.assertEqual(game.morto_states[1], "available")
        game.execute("meld 3h 4h 5h")
        self.assertTrue(game.team.took_morto)
        self.assertFalse(game.ended)
        game.execute("discard " + game.hands[0][0].selector)
        self.assertTrue(game.ended)
        self.assertIn("Stock exhausted", game.end_reason)

    def test_last_draw_can_take_morto_by_discard(self):
        game = position("", phase="draw", stock="3h", mortos=("taken by Team 2", "available"))
        game.execute("draw stock")
        game.execute("discard 3h")
        self.assertEqual(len(game.hands[0]), 11)
        self.assertTrue(game.ended)
        self.assertEqual(game.scores()[0]["morto_penalty"], 0)
        self.assertLess(game.scores()[0]["hand_penalty"], 0)

    def test_remaining_morto_replenishes_even_after_first_taken(self):
        game = position("9s", phase="draw", stock="3h", mortos=("taken by Team 2", "available"))
        game.execute("draw stock")
        game.execute("discard 3h")
        self.assertEqual(len(game.stock), 11)
        self.assertEqual(game.morto_states[1], "moved to stock")
        self.assertFalse(game.ended)

    def test_first_available_replenishes_and_second_stays(self):
        game = position("9s", phase="draw", stock="3h")
        game.execute("draw stock")
        game.execute("discard 3h")
        self.assertEqual(game.morto_states, ["moved to stock", "available"])

    def test_last_stock_turn_ends_despite_nonempty_discard(self):
        game = position("9s", phase="draw", stock="3h", mortos=("moved to stock", "taken by Team 2"))
        game.execute("draw stock")
        self.assertFalse(game.ended)
        game.execute("discard 3h")
        self.assertTrue(game.ended)
        self.assertTrue(game.discard)
        self.assertEqual(game.went_out, None)
        self.unchanged_after(game, "take discard")

    def test_twelve_no_progress_turns_and_reset_on_stock_draw(self):
        game = Game(seed=1)
        for index in range(12):
            selector = game.discard[0].selector
            game.execute("take discard")
            game.execute("discard " + selector)
            self.assertEqual(game.no_progress, index + 1)
            self.assertEqual(game.ended, index == 11)
        self.assertIn("12 consecutive", game.end_reason)
        game = Game(seed=1)
        selector = game.discard[0].selector
        game.execute("take discard")
        game.execute("discard " + selector)
        game.execute("draw stock")
        game.execute("discard " + game.hands[game.active][0].selector)
        self.assertEqual(game.no_progress, 0)

    def test_progress_on_meld_and_morto_resets_counter(self):
        for hand in ("3h 4h 5h 9s", "3h 4h 5h"):
            game = position(hand)
            game.no_progress = 11
            game.execute("meld 3h 4h 5h")
            game.execute("discard " + game.hands[0][0].selector)
            self.assertEqual(game.no_progress, 0)
            self.assertFalse(game.ended)

    def test_quit_scoring_without_go_out_and_tie(self):
        game = position("3h", other_hands={1: "3s"})
        game.execute("quit")
        self.assertEqual(game.view()["winner"], "Draw")
        self.assertEqual(game.scores()[0]["total"], -105)
        self.assertEqual(game.scores()[0]["going_out"], 0)

    def test_show_help_do_not_mutate(self):
        game = Game()
        before = game.view()
        game.execute("show")
        game.execute("help")
        self.assertEqual(game.view(), before)

    def test_only_active_hand_exposed(self):
        game = Game()
        view = game.view()
        self.assertNotIn("hands", view)
        self.assertNotIn("stock", view)
        self.assertTrue(all(set(p) == {"player", "team", "count"} for p in view["players"]))
        self.assertTrue(all(score["hand_penalty"] == 0 for score in view["scores"]))
        self.assertTrue(all(score["total"] == 0 for score in view["scores"]))
        game.execute("quit")
        self.assertTrue(all(score["hand_penalty"] < 0 for score in game.view()["scores"]))

    def test_long_play_sequences_conserve_cards(self):
        for seed in range(8):
            game = Game(seed=seed)
            chooser = random.Random(seed)
            turns = 0
            while not game.ended and turns < 200:
                game.execute("take discard" if game.discard and chooser.random() < .3 else "draw stock")
                game.execute("discard " + chooser.choice(game.hands[game.active]).selector)
                game.assert_conserved()
                turns += 1
            self.assertTrue(game.ended)


if __name__ == "__main__":
    unittest.main()
