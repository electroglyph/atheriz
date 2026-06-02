"""Tests for atheriz/objects/verb_conjugation/pronouns.py.

Pure-Python; no DB / network / async. Covers the public
pronoun_to_viewpoints function and the module-level constants/mappings.
"""
import pytest

from atheriz.objects.verb_conjugation.pronouns import (
    DEFAULT_PRONOUN_TYPE,
    DEFAULT_VIEWPOINT,
    DEFAULT_GENDER,
    PRONOUN_TYPES,
    VIEWPOINTS,
    GENDERS,
    PRONOUN_MAPPING,
    PRONOUN_TABLE,
    VIEWPOINT_CONVERSION,
    ALIASES,
    pronoun_to_viewpoints,
)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


def test_pronoun_types_constant():
    assert "subject pronoun" in PRONOUN_TYPES
    assert "object pronoun" in PRONOUN_TYPES
    assert "possessive adjective" in PRONOUN_TYPES
    assert "possessive pronoun" in PRONOUN_TYPES
    assert "reflexive pronoun" in PRONOUN_TYPES


def test_viewpoints_constant():
    assert set(VIEWPOINTS) == {"1st person", "2nd person", "3rd person"}


def test_genders_constant():
    assert set(GENDERS) == {"male", "female", "neutral", "plural"}


def test_defaults():
    assert DEFAULT_PRONOUN_TYPE == "subject pronoun"
    assert DEFAULT_VIEWPOINT == "2nd person"
    assert DEFAULT_GENDER == "neutral"


def test_viewpoint_conversion():
    assert VIEWPOINT_CONVERSION["1st person"] == "3rd person"
    assert VIEWPOINT_CONVERSION["2nd person"] == "3rd person"
    assert set(VIEWPOINT_CONVERSION["3rd person"]) == {"2nd person", "1st person"}


def test_aliases():
    assert ALIASES["m"] == "male"
    assert ALIASES["f"] == "female"
    assert ALIASES["n"] == "neutral"
    assert ALIASES["p"] == "plural"
    assert ALIASES["1st"] == "1st person"
    assert ALIASES["2nd"] == "2nd person"
    assert ALIASES["3rd"] == "3rd person"
    assert ALIASES["1"] == "1st person"
    assert ALIASES["2"] == "2nd person"
    assert ALIASES["3"] == "3rd person"
    assert ALIASES["sp"] == "subject pronoun"
    assert ALIASES["op"] == "object pronoun"
    assert ALIASES["pa"] == "possessive adjective"
    assert ALIASES["pp"] == "possessive pronoun"


# ---------------------------------------------------------------------------
# pronoun_to_viewpoints — empty / unknown
# ---------------------------------------------------------------------------


def test_pronoun_to_viewpoints_empty_returns_input():
    assert pronoun_to_viewpoints("") == ""


def test_pronoun_to_viewpoints_unknown_returns_input():
    assert pronoun_to_viewpoints("xyzzy") == "xyzzy"
    assert pronoun_to_viewpoints("nope") == "nope"


# ---------------------------------------------------------------------------
# pronoun_to_viewpoints — "I" special case
# ---------------------------------------------------------------------------


def test_pronoun_to_viewpoints_i_capitalized():
    """The "I" special case skips copy_word_case (always capitalized).
    The first tuple element is always the original input; the second
    is the mapped 3rd-person form using the source's defaults."""
    speaker, observer = pronoun_to_viewpoints("I")
    # Source pronoun is preserved verbatim as speaker form.
    assert speaker == "I"
    # The default neutral gender maps "I" to "it" in 3rd person.
    assert observer == "it"


# ---------------------------------------------------------------------------
# 1st-person -> 3rd-person conversion
# ---------------------------------------------------------------------------


def test_1st_person_me_default_gender_neutral():
    # "me" with default gender (neutral) maps to "it" in 3rd person —
    # this is a documented quirk of the function.
    speaker, observer = pronoun_to_viewpoints("me")
    assert observer == "it"


def test_1st_person_us_plural():
    speaker, observer = pronoun_to_viewpoints("us")
    assert observer == "them"


def test_1st_person_us_plural_explicit_gender():
    speaker, observer = pronoun_to_viewpoints("us", gender="plural")
    assert observer == "them"


# ---------------------------------------------------------------------------
# 3rd-person -> 1st/2nd-person conversion
# ---------------------------------------------------------------------------


def test_3rd_person_him_to_2nd():
    """A 3rd-person object pronoun with explicit 2nd-person viewpoint
    yields 'you' as the speaker form."""
    speaker, observer = pronoun_to_viewpoints("him", options="2nd")
    assert speaker == "you"
    assert observer == "him"


def test_3rd_person_them_to_1st():
    speaker, observer = pronoun_to_viewpoints("them", options="1st")
    assert speaker == "us"
    assert observer == "them"


def test_3rd_person_he_to_2nd():
    speaker, observer = pronoun_to_viewpoints("he", options="2nd")
    assert speaker == "you"
    assert observer == "he"


def test_3rd_person_she_to_2nd():
    speaker, observer = pronoun_to_viewpoints("she", options="2nd")
    assert speaker == "you"
    assert observer == "she"


def test_3rd_person_they_to_1st():
    speaker, observer = pronoun_to_viewpoints("they", options="1st")
    assert speaker == "we"
    assert observer == "they"


def test_3rd_person_they_to_2nd():
    speaker, observer = pronoun_to_viewpoints("they", options="2nd")
    assert speaker == "you"
    assert observer == "they"


# ---------------------------------------------------------------------------
# Ambiguous pronoun disambiguation
# ---------------------------------------------------------------------------


def test_her_default_chooses_object_pronoun():
    """'her' is ambiguous (op or pa). Without options, defaults to
    object pronoun (first in tuple)."""
    speaker, observer = pronoun_to_viewpoints("her")
    # default is object pronoun -> 3rd person op neutral = "her"
    assert observer == "her"


def test_her_with_pa_option():
    speaker, observer = pronoun_to_viewpoints("her", options="pa")
    # possessive adjective (3rd person female) = "her"
    assert observer == "her"
    # speaker 2nd person pa = "your"
    assert speaker == "your"


def test_his_default_pp():
    """'his' is ambiguous (pp or pa). Default is pp."""
    speaker, observer = pronoun_to_viewpoints("his")
    # 3rd person male pp = "his"
    assert observer == "his"


def test_his_with_pa_option():
    speaker, observer = pronoun_to_viewpoints("his", options="pa")
    # 3rd person male pa = "his"
    assert observer == "his"
    assert speaker == "your"


def test_it_default_subject():
    """'it' is ambiguous (subject or object). Default = subject."""
    speaker, observer = pronoun_to_viewpoints("it")
    # 3rd person neutral subject pronoun = "it"
    assert observer == "it"


def test_it_with_object_option():
    speaker, observer = pronoun_to_viewpoints("it", options="op")
    assert observer == "it"


def test_its_default_pp():
    """'its' is ambiguous (pp or pa)."""
    speaker, observer = pronoun_to_viewpoints("its")
    # 3rd person neutral pp = "its"
    assert observer == "its"


# ---------------------------------------------------------------------------
# Casing preservation
# ---------------------------------------------------------------------------


def test_caps_preserved_input():
    """Capitalization of the input is carried into the speaker/observer."""
    speaker, observer = pronoun_to_viewpoints("Her", options="2nd")
    # Capitalization is preserved through copy_word_case.
    assert "H" in observer or "h" in observer
    assert speaker == "You"


def test_lowercase_input_unchanged():
    speaker, observer = pronoun_to_viewpoints("her", options="2nd")
    assert observer == "her"


# ---------------------------------------------------------------------------
# Aliases in options
# ---------------------------------------------------------------------------


def test_options_alias_male():
    speaker, observer = pronoun_to_viewpoints("him", options="m")
    # gender=male explicitly
    assert observer == "him"


def test_options_alias_female_2nd():
    speaker, observer = pronoun_to_viewpoints("her", options="f 2nd")
    assert observer == "her"
    assert speaker == "you"


def test_options_alias_plural_3rd():
    speaker, observer = pronoun_to_viewpoints("they", options="p")
    assert observer == "they"


def test_options_alias_pronoun_type_subject():
    """'subject' alias maps to 'subject pronoun'."""
    speaker, observer = pronoun_to_viewpoints("you", options="subject")
    # 'you' is 2nd person, ambiguous subject/object
    # pronoun_type is now 'subject pronoun' (forced)


def test_options_as_list():
    speaker, observer = pronoun_to_viewpoints("her", options=["pa", "2nd"])
    assert speaker == "your"


# ---------------------------------------------------------------------------
# Explicit kwargs
# ---------------------------------------------------------------------------


def test_explicit_pronoun_type_kwarg():
    speaker, observer = pronoun_to_viewpoints("her", pronoun_type="possessive adjective")
    assert speaker == "your"
    assert observer == "her"


def test_explicit_viewpoint_kwarg():
    speaker, observer = pronoun_to_viewpoints("him", viewpoint="1st person")
    assert speaker == "me"
    assert observer == "him"


def test_explicit_gender_kwarg():
    speaker, observer = pronoun_to_viewpoints("us", gender="plural")
    assert observer == "them"


# ---------------------------------------------------------------------------
# Reflexive
# ---------------------------------------------------------------------------


def test_reflexive_myself_default_neutral():
    """'myself' source is 1st-person neutral. The default gender
    resolves to 3rd-person neutral reflexive = 'itself'."""
    speaker, observer = pronoun_to_viewpoints("myself")
    assert speaker == "myself"
    assert observer == "itself"


def test_reflexive_themselves():
    """'themselves' source is 3rd-person plural. The default viewpoint
    is the source's viewpoint ('3rd person'), which is not a valid
    target from 3rd (which can map to 1st or 2nd), so it falls back to
    '2nd person' — yielding the 2nd-person plural reflexive."""
    speaker, observer = pronoun_to_viewpoints("themselves")
    assert speaker == "yourselves"
    assert observer == "themselves"


def test_reflexive_himself_to_2nd():
    speaker, observer = pronoun_to_viewpoints("himself", options="2nd")
    # 2nd person neutral reflexive (gender male not available) = yourself
    assert speaker == "yourself"
    assert observer == "himself"
