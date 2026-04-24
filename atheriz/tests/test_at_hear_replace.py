import pytest
from atheriz.objects.base_obj import Object
import atheriz.settings as settings
from unittest.mock import MagicMock

def test_at_hear_replace_logic(global_test_env):
    # Setup listener and emitter
    listener = Object.create(None, "Listener", is_pc=True)
    emitter = Object.create(None, "Emitter", is_pc=False)
    
    # Mock location to be the same
    loc = Object.create(None, "Room")
    listener.location = loc
    emitter.location = loc
    
    test_msg = "one two three four five six seven eight nine ten" # 10 words
    
    # Test cases: (loudness, expected_replace_pct)
    # Loudness 5: < 10, so 75% replacement
    listener.msg = MagicMock()
    listener.at_hear(emitter, "Someone says,", f" \"{test_msg}\"", 5, is_say=True)
    received_text = listener.msg.call_args[0][0]
    assert "nearly inaudible" in received_text
    assert "..." in received_text
    # with 75% replacement on 10 words, very likely to have many ...
    assert received_text.count("...") >= 1

def test_at_hear_thresholds(global_test_env):
    listener = Object.create(None, "Listener", is_pc=True)
    emitter = Object.create(None, "Emitter", is_pc=False)
    loc = Object.create(None, "Room")
    listener.location = loc
    emitter.location = loc
    
    test_msg = "word " * 50 # 50 words to make random replacement more predictable
    
    # High loudness (55): No replacement
    listener.msg = MagicMock()
    listener.at_hear(emitter, "Someone says,", f" \"{test_msg.strip()}\"", 55, is_say=True)
    received_text = listener.msg.call_args[0][0]
    assert "..." not in received_text
    assert test_msg.strip() in received_text

    # Low loudness (0.5): High replacement (90%)
    listener.msg = MagicMock()
    listener.at_hear(emitter, "Someone says,", f" \"{test_msg.strip()}\"", 0.5, is_say=True)
    received_text = listener.msg.call_args[0][0]
    assert "..." in received_text
    assert received_text.count("...") > 30 # Should be around 45

def test_at_hear_is_say_false(global_test_env):
    listener = Object.create(None, "Listener", is_pc=True)
    emitter = Object.create(None, "Emitter", is_pc=False)
    loc = Object.create(None, "Room")
    listener.location = loc
    emitter.location = loc
    
    listener.msg = MagicMock()
    # is_say = False: No replacement even if loudness is low
    listener.at_hear(emitter, "A crash", " (very loud message)", 5, is_say=False)
    received_text = listener.msg.call_args[0][0]
    assert "nearly inaudible" in received_text
    assert "(very loud message)" in received_text
    assert "..." not in received_text
