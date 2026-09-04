"""Tests for atheriz/objects/verb_conjugation/conjugate.py.

Pure-Python; no DB / network / async. Covers every public function.
"""
import pytest

from atheriz.objects.verb_conjugation import conjugate as c
from atheriz.objects.verb_conjugation.conjugate import verb_is_present, verb_is_past


# ---------------------------------------------------------------------------
# verb_infinitive
# ---------------------------------------------------------------------------


def test_verb_infinitive_irregular_be():
    assert c.verb_infinitive("was") == "be"
    assert c.verb_infinitive("were") == "be"
    assert c.verb_infinitive("is") == "be"
    assert c.verb_infinitive("are") == "be"
    assert c.verb_infinitive("been") == "be"
    assert c.verb_infinitive("being") == "be"


def test_verb_infinitive_regular_inflected():
    assert c.verb_infinitive("running") == "run"
    assert c.verb_infinitive("walked") == "walk"
    assert c.verb_infinitive("eaten") == "eat"


def test_verb_infinitive_already_infinitive():
    assert c.verb_infinitive("be") == "be"
    assert c.verb_infinitive("run") == "run"


def test_verb_infinitive_unknown_returns_original():
    assert c.verb_infinitive("xyzzy") == "xyzzy"
    assert c.verb_infinitive("") == ""


# ---------------------------------------------------------------------------
# verb_conjugate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verb,tense,expected",
    [
        ("be", "infinitive", "be"),
        ("be", "1st singular present", "am"),
        ("be", "2nd singular present", "are"),
        ("be", "3rd singular present", "is"),
        ("be", "present plural", "are"),
        ("be", "present participle", "being"),
        ("be", "1st singular past", "was"),
        ("be", "2nd singular past", "were"),
        ("be", "3rd singular past", "was"),
        ("be", "past plural", "were"),
        ("be", "past", "were"),
        ("be", "past participle", "been"),
        ("have", "3rd singular present", "has"),
        ("have", "past", "had"),
        ("go", "past participle", "gone"),
        ("run", "past participle", "run"),
        ("give", "present participle", "giving"),
        ("swim", "past participle", "swum"),
    ],
)
def test_verb_conjugate(verb, tense, expected):
    assert c.verb_conjugate(verb, tense) == expected


def test_verb_conjugate_short_aliases():
    """Short alias keys must produce the same result as long forms."""
    assert c.verb_conjugate("be", "inf") == c.verb_conjugate("be", "infinitive")
    assert c.verb_conjugate("be", "3sgpres") == c.verb_conjugate("be", "3rd singular present")
    assert c.verb_conjugate("be", "ppart") == c.verb_conjugate("be", "past participle")
    assert c.verb_conjugate("be", "prog") == c.verb_conjugate("be", "present participle")
    assert c.verb_conjugate("be", "1sgpres") == c.verb_conjugate("be", "1st singular present")


def test_verb_conjugate_negate_supported():
    assert c.verb_conjugate("be", "3rd singular present", negate=True) == "isn't"
    assert c.verb_conjugate("be", "1st singular present", negate=True) == "am not"
    assert c.verb_conjugate("have", "3rd singular present", negate=True) == "hasn't"
    assert c.verb_conjugate("do", "infinitive", negate=True) == "don't"
    assert c.verb_conjugate("can", "infinitive", negate=True) == "can't"


def test_verb_conjugate_unknown_returns_original():
    """verb_conjugate first lemmatizes the input. Unknown verbs have no lemma,
    so the original verb is returned unchanged (as the docstring documents)."""
    assert c.verb_conjugate("xyzzy", "infinitive") == "xyzzy"
    assert c.verb_conjugate("flibbertigibbet", "past") == "flibbertigibbet"


def test_verb_conjugate_accepts_inflected_input():
    """Input may be inflected — verb_infinitive() is called internally."""
    assert c.verb_conjugate("was", "infinitive") == "be"
    assert c.verb_conjugate("running", "past participle") == c.verb_conjugate("run", "past participle")


# ---------------------------------------------------------------------------
# verb_present / verb_past
# ---------------------------------------------------------------------------


def test_verb_present_all_persons():
    assert c.verb_present("be", "1") == "am"
    assert c.verb_present("be", "2") == "are"
    assert c.verb_present("be", "3") == "is"
    assert c.verb_present("be", "*") == "are"


def test_verb_present_with_ordinal_suffix():
    """The person string is stripped of 's', 't', 'n', 'd', etc."""
    assert c.verb_present("be", "1st") == "am"
    assert c.verb_present("be", "3rd") == "is"
    assert c.verb_present("be", "2nd") == "are"


def test_verb_present_plural_alias():
    """'pl' is replaced with '*' (plural) before lookup."""
    assert c.verb_present("be", "pl") == "are"


def test_verb_present_falls_back_to_infinitive():
    """Unknown person falls back to the infinitive."""
    assert c.verb_present("be", "5") == "be"
    assert c.verb_present("walk", "") == "walk"


def test_verb_past_all_persons():
    assert c.verb_past("be", "1") == "was"
    assert c.verb_past("be", "2") == "were"
    assert c.verb_past("be", "3") == "was"
    assert c.verb_past("be", "*") == "were"
    assert c.verb_past("run", "3") == "ran"


def test_verb_past_falls_back_to_infinitive_past():
    assert c.verb_past("walk", "") == "walked"
    assert c.verb_past("run", "") == "ran"


# ---------------------------------------------------------------------------
# verb_present_participle / verb_past_participle
# ---------------------------------------------------------------------------


def test_verb_present_participle():
    assert c.verb_present_participle("give") == "giving"
    assert c.verb_present_participle("be") == "being"
    assert c.verb_present_participle("swim") == "swimming"
    assert c.verb_present_participle("eat") == "eating"


def test_verb_past_participle():
    assert c.verb_past_participle("give") == "given"
    assert c.verb_past_participle("be") == "been"
    assert c.verb_past_participle("swim") == "swum"
    assert c.verb_past_participle("eat") == "eaten"


# ---------------------------------------------------------------------------
# verb_all_tenses
# ---------------------------------------------------------------------------


def test_verb_all_tenses_count():
    tenses = c.verb_all_tenses()
    assert len(tenses) == 12


def test_verb_all_tenses_unique():
    assert len(set(c.verb_all_tenses())) == len(c.verb_all_tenses())


def test_verb_all_tenses_contents():
    """Spot-check the documented tense names."""
    tenses = c.verb_all_tenses()
    assert "infinitive" in tenses
    assert "past" in tenses
    assert "past participle" in tenses
    assert "present participle" in tenses


# ---------------------------------------------------------------------------
# verb_tense
# ---------------------------------------------------------------------------


def test_verb_tense_known():
    # The tense returned is whichever verb_tenses_keys index the data
    # matches first; for many regular verbs this is the "bare past" slot.
    assert c.verb_tense("ran") in ("past", "1st singular past", "3rd singular past")
    assert c.verb_tense("running") == "present participle"
    assert c.verb_tense("am") == "1st singular present"
    assert c.verb_tense("been") == "past participle"
    assert c.verb_tense("is") == "3rd singular present"


def test_verb_tense_unknown_returns_original():
    """An unknown verb has no tense, so None is returned (the caller falls
    back to the verb itself)."""
    assert c.verb_tense("xyzzy") is None


def test_verb_tense_infinitive():
    assert c.verb_tense("be") == "infinitive"
    assert c.verb_tense("walk") == "infinitive"


# ---------------------------------------------------------------------------
# verb_is_tense
# ---------------------------------------------------------------------------


def test_verb_is_tense_true():
    assert c.verb_is_tense("been", "ppart")
    assert c.verb_is_tense("been", "past participle")
    assert c.verb_is_tense("running", "present participle")
    assert c.verb_is_tense("am", "1st singular present")
    assert c.verb_is_tense("is", "3rd singular present")


def test_verb_is_tense_false():
    assert not c.verb_is_tense("been", "infinitive")
    assert not c.verb_is_tense("ran", "past participle")
    assert not c.verb_is_tense("running", "infinitive")


# ---------------------------------------------------------------------------
# verb_is_present / verb_is_past
# ---------------------------------------------------------------------------


def test_verb_is_present():
    assert c.verb_is_present("am", "1")
    assert c.verb_is_present("are", "2")
    assert c.verb_is_present("is", "3")
    assert not c.verb_is_present("am", "3")
    assert not c.verb_is_present("was", "1")


def test_verb_is_present_negated():
    assert c.verb_is_present("isn't", "3", negated=True)
    assert c.verb_is_present("am not", "1", negated=True)
    assert not c.verb_is_present("is", "3", negated=True)


def test_verb_is_past():
    # "was" appears in both 1st and 3rd singular past — both should be true.
    assert c.verb_is_past("was", "1")
    assert c.verb_is_past("was", "3")
    assert c.verb_is_past("were", "2")
    assert c.verb_is_past("am", "1") is False
    assert c.verb_is_past("is", "3") is False
    # "am" is present, not past.
    assert not c.verb_is_past("am", "1")


def test_verb_is_past_negated():
    assert c.verb_is_past("wasn't", "1", negated=True)
    assert c.verb_is_past("weren't", "2", negated=True)
    assert not c.verb_is_past("was", "1", negated=True)


# ---------------------------------------------------------------------------
# verb_is_present_participle / verb_is_past_participle
# ---------------------------------------------------------------------------


def test_verb_is_present_participle():
    assert c.verb_is_present_participle("running")
    assert c.verb_is_present_participle("being")
    assert not c.verb_is_present_participle("ran")
    assert not c.verb_is_present_participle("run")


def test_verb_is_past_participle():
    assert c.verb_is_past_participle("been")
    assert c.verb_is_past_participle("eaten")
    assert not c.verb_is_past_participle("eat")
    assert not c.verb_is_past_participle("eating")


# ---------------------------------------------------------------------------
# verb_actor_stance_components
# ---------------------------------------------------------------------------


def test_verb_actor_stance_past_singular():
    """Past singular: ('you_form', 'them_form')."""
    you, them = c.verb_actor_stance_components("ran")
    assert you == "ran"
    assert them == "ran"


def test_verb_actor_stance_past_plural():
    you, them = c.verb_actor_stance_components("ran", plural=True)
    assert you == "ran"
    assert them == "ran"


def test_verb_actor_stance_infinitive_singular():
    """Infinitive with a regular verb: you-form adds nothing weird,
    them-form adds 's' as fallback."""
    you, them = c.verb_actor_stance_components("walk")
    # verb_present with person=2 returns "walk" (no person-specific form)
    # verb_present with person=3 returns "walks" for "walk"
    assert them == "walks"


def test_verb_actor_stance_present_participle():
    """Participles short-circuit to (verb, verb)."""
    you, them = c.verb_actor_stance_components("running")
    assert you == "running"
    assert them == "running"


def test_verb_is_present_are_plural():
    assert verb_is_present("are", "plural") is True
    assert verb_is_present("are", "*") is True
    assert verb_is_present("are", "2") is True
    assert verb_is_present("are", "2nd") is True
    assert verb_is_present("are", "1") is False
    assert verb_is_present("are", "3") is False
    assert verb_is_present("is", "3") is True
    assert verb_is_present("is", "plural") is False
    assert verb_is_present("is", "2") is False
    assert verb_is_present("am", "") is True
    assert verb_is_present("was", "") is False


def test_verb_is_past_was_covers_both_singular():
    assert verb_is_past("was", "1") is True
    assert verb_is_past("was", "3") is True
    assert verb_is_past("was", "2") is False
    assert verb_is_past("was", "*") is False
    assert verb_is_past("were", "2") is True
    assert verb_is_past("were", "*") is True
    assert verb_is_past("were", "1") is False


def test_verb_is_present_past_negated():
    assert verb_is_present("isn't", "3", negated=True) is True
    assert verb_is_present("is", "3", negated=True) is False
    assert verb_is_past("wasn't", "1", negated=True) is True
    assert verb_is_past("was", "1", negated=True) is False


class TestVerbTenseUnknownReturnsNone:
    def test_verb_tense_unknown_returns_none(self):
        assert c.verb_tense("xyzzy") is None


class TestVerbDuplicateInfinitives:
    def test_duplicate_infinitives_resolve_to_correct_forms(self):
        """Last-wins duplicate rows in verbs.txt must not clobber correct forms."""
        assert c.verb_conjugate("matter", "3rd singular present") == "matters"
        assert c.verb_conjugate("leer", "3rd singular present") == "leers"
        assert c.verb_conjugate("leer", "present participle") == "leering"
        assert c.verb_conjugate("leer", "past") == "leered"
        assert c.verb_conjugate("skewer", "3rd singular present") == "skewers"
        assert c.verb_conjugate("draft", "present participle") == "drafting"
        assert c.verb_conjugate("draft", "past") == "drafted"
        assert c.verb_conjugate("lure", "3rd singular present") == "lures"

    def test_merged_and_renamed_verbs_conjugate_correctly(self):
        """Merged rows keep all tenses; misfiled rows live under their own headword."""
        assert c.verb_conjugate("feed", "3rd singular present") == "feeds"
        assert c.verb_conjugate("feed", "past") == "fed"
        assert c.verb_conjugate("drag", "3rd singular present") == "drags"
        assert c.verb_conjugate("drag", "present participle") == "dragging"
        assert c.verb_conjugate("drag", "past") == "dragged"
        assert c.verb_conjugate("lay", "past") == "laid"
        assert c.verb_conjugate("low", "3rd singular present") == "lows"
        assert c.verb_conjugate("rebind", "past") == "rebound"
        assert c.verb_conjugate("wrap", "present participle") == "wrapping"
        assert c.verb_conjugate("halt", "3rd singular present") == "halts"
        assert c.verb_conjugate("skew", "3rd singular present") == "skews"
        assert c.verb_conjugate("buff", "past") == "buffed"
        assert c.verb_conjugate("numb", "past") == "numbed"
        assert c.verb_conjugate("filigree", "past") == "filigreed"
        assert c.verb_conjugate("founder", "3rd singular present") == "founders"
        assert c.verb_conjugate("summons", "present participle") == "summoning"
        assert c.verb_conjugate("rebound", "past") == "rebounded"
        assert c.verb_conjugate("bound", "3rd singular present") == "bounds"

    def test_verbs_txt_has_no_duplicate_infinitives(self):
        """File-wide guard: every headword appears exactly once (last-wins
        clobbering corrupted matter/leer/skewer/draft/lure)."""
        import os
        from collections import Counter

        path = os.path.join(os.path.dirname(c.__file__), "verbs.txt")
        with open(path, encoding="utf-8") as fil:
            heads = [line.split(",")[0].strip() for line in fil if line.strip()]
        dupes = sorted(k for k, n in Counter(heads).items() if n > 1)
        assert dupes == [], f"duplicate infinitives in verbs.txt: {dupes}"
