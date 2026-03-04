"""Tests for per-user memory system.

Covers:
- Conversation recording + retrieval
- Memory context building
- Keyword extraction
- Summarization trigger logic
- User preferences
- Memory isolation between users
- Memory clearing
- Memory stats
"""
import os
import sys
import time
import json
import sqlite3

# Ensure we import from the bot directory
sys.path.insert(0, os.path.dirname(__file__))

# Use a test database
TEST_DB = os.path.join(os.path.dirname(__file__), "test_memory.db")

import db
db.DB_PATH = TEST_DB

import memory as mem

passed = 0
failed = 0
total = 0


def check(name, condition, detail=""):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  \u2705 {name}")
    else:
        failed += 1
        print(f"  \u274c {name}: {detail}")


def setup():
    """Initialize test database."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    db.init_db()
    mem._memory_cache.clear()


def teardown():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


# ── Test 1: Conversation Recording ──

def test_conversation_recording():
    print("\n\U0001f4dd Test 1: Conversation Recording")
    setup()

    user_id = 1001
    m = mem.get_user_memory(user_id)

    m.record("user", "What's BTC price?")
    m.record("assistant", "BTC is at $95,000, up 2.3% today.")
    m.record("user", "Should I long it?")
    m.record("assistant", "Based on the upward momentum, a small long position could work.")

    recent = m.get_working_memory()
    check("Records 4 messages", len(recent) == 4, f"got {len(recent)}")
    check("First message is user", recent[0]["role"] == "user")
    check("Content preserved", "BTC" in recent[0]["content"])
    check("Chronological order", recent[0]["created_at"] <= recent[-1]["created_at"])


# ── Test 2: Memory Isolation ──

def test_memory_isolation():
    print("\n\U0001f512 Test 2: Memory Isolation Between Users")
    setup()

    user_a = mem.get_user_memory(2001)
    user_b = mem.get_user_memory(2002)

    user_a.record("user", "I love trading SOL")
    user_a.record("assistant", "SOL is a great choice!")

    user_b.record("user", "ETH is my favorite")
    user_b.record("assistant", "ETH has strong fundamentals.")

    mem_a = user_a.get_working_memory()
    mem_b = user_b.get_working_memory()

    check("User A has 2 messages", len(mem_a) == 2, f"got {len(mem_a)}")
    check("User B has 2 messages", len(mem_b) == 2, f"got {len(mem_b)}")
    check("User A sees SOL", any("SOL" in m["content"] for m in mem_a))
    check("User A doesn't see ETH", not any("ETH" in m["content"] for m in mem_a))
    check("User B sees ETH", any("ETH" in m["content"] for m in mem_b))
    check("User B doesn't see SOL", not any("SOL" in m["content"] for m in mem_b))


# ── Test 3: Context Building ──

def test_context_building():
    print("\n\U0001f9e0 Test 3: Memory Context Building")
    setup()

    user_id = 3001
    m = mem.get_user_memory(user_id)

    m.record("user", "I prefer small positions, max 50 USD")
    m.record("assistant", "Got it, I'll keep positions under $50.")
    m.record("user", "BTC looks bullish to me")
    m.record("assistant", "Yes, BTC is showing strong momentum. Consider a small long.")

    context = m.get_context_for_prompt("What about SOL?")

    check("Context is non-empty", len(context) > 0, f"got empty string")
    check("Contains recent conversation header", "Recent Conversation" in context)
    check("Contains BTC from history", "BTC" in context)


# ── Test 4: User Preferences ──

def test_user_preferences():
    print("\n\u2699\ufe0f Test 4: User Preferences")
    setup()

    user_id = 4001
    m = mem.get_user_memory(user_id)

    m.update_preferences({
        "trading_style": "conservative scalper",
        "favorite_assets": ["BTC", "ETH"],
        "risk_tolerance": "low",
    })

    prefs = db.get_user_preferences(user_id)
    check("Trading style saved", prefs.get("trading_style") == "conservative scalper")
    check("Favorite assets saved", prefs.get("favorite_assets") == ["BTC", "ETH"])
    check("Risk tolerance saved", prefs.get("risk_tolerance") == "low")

    # Merge new favorites
    m.update_preferences({
        "favorite_assets": ["SOL", "DOGE"],
        "notes": ["User prefers morning trading sessions"],
    })

    prefs = db.get_user_preferences(user_id)
    check("Assets merged", "SOL" in prefs.get("favorite_assets", []))
    check("Old assets kept", "BTC" in prefs.get("favorite_assets", []))
    check("Notes added", len(prefs.get("notes", [])) == 1)

    # Check preferences appear in context
    m.record("user", "test message")
    context = m.get_context_for_prompt("test")
    check("Preferences in context", "conservative scalper" in context, f"context: {context[:200]}")


# ── Test 5: Keyword Extraction ──

def test_keyword_extraction():
    print("\n\U0001f50d Test 5: Keyword Extraction")
    setup()

    kw1 = mem._extract_keywords("What's the BTC price right now?")
    check("Extracts BTC", "btc" in kw1, f"got {kw1}")
    check("Filters stop words", "the" not in kw1 and "what" not in kw1)

    kw2 = mem._extract_keywords("SOL和ETH哪个好")
    check("Extracts SOL from Chinese", "sol" in kw2, f"got {kw2}")
    check("Extracts ETH from Chinese", "eth" in kw2, f"got {kw2}")

    kw3 = mem._extract_keywords("I want to short NVDA with 3x leverage")
    check("Extracts NVDA", "nvda" in kw3, f"got {kw3}")
    check("Asset keywords first", kw3.index("nvda") == 0 if "nvda" in kw3 else False)


# ── Test 6: Summarization Trigger ──

def test_summarization_trigger():
    print("\n\U0001f4ca Test 6: Summarization Trigger")
    setup()

    user_id = 6001
    m = mem.get_user_memory(user_id)

    # Not enough turns yet (4 pairs = 8 turns, below threshold of 10)
    for i in range(4):
        m.record("user", f"Message {i}")
        m.record("assistant", f"Response {i}")

    check("No summarization needed (8 turns)", not m.needs_summarization())

    # Add more turns to exceed threshold (6 pairs = 12 turns total)
    for i in range(4, 6):
        m.record("user", f"Message {i}")
        m.record("assistant", f"Response {i}")

    check("Summarization needed (12 turns)", m.needs_summarization())

    # Get unsummarized turns
    turns = m.get_unsummarized_turns()
    check("All 12 turns unsummarized", len(turns) == 12, f"got {len(turns)}")


# ── Test 7: Memory Summary Storage ──

def test_memory_summary():
    print("\n\U0001f4be Test 7: Memory Summary Storage")
    setup()

    user_id = 7001
    m = mem.get_user_memory(user_id)

    for i in range(5):
        m.record("user", f"User says {i}")
        m.record("assistant", f"Agent replies {i}")

    turns = m.get_unsummarized_turns()
    m.save_summary(
        summary="User discussed BTC trading, prefers conservative approach.",
        keywords="btc,trading,conservative",
        turns=turns,
    )

    summaries = db.get_memory_summaries(user_id)
    check("Summary saved", len(summaries) == 1, f"got {len(summaries)}")
    check("Summary content", "BTC" in summaries[0]["summary"])
    check("Keywords saved", "btc" in summaries[0]["keywords"])

    # After saving summary, needs_summarization should be false
    check("No re-summarization needed", not m.needs_summarization())

    # Search summaries
    hits = db.search_memory_summaries(user_id, "BTC")
    check("Search finds summary", len(hits) > 0)

    hits2 = db.search_memory_summaries(user_id, "PEPE")
    check("Search misses irrelevant", len(hits2) == 0)


# ── Test 8: Conversation Search ──

def test_conversation_search():
    print("\n\U0001f50e Test 8: Conversation Search")
    setup()

    user_id = 8001
    m = mem.get_user_memory(user_id)

    m.record("user", "I want to buy DOGE")
    m.record("assistant", "DOGE is at $0.18, a volatile pick!")
    m.record("user", "What about SILVER?")
    m.record("assistant", "SILVER is stable at $28.50.")

    doge_hits = db.search_conversations(user_id, "DOGE")
    check("Finds DOGE messages", len(doge_hits) >= 1)

    silver_hits = db.search_conversations(user_id, "SILVER")
    check("Finds SILVER messages", len(silver_hits) >= 1)

    empty_hits = db.search_conversations(user_id, "PEPE")
    check("No hits for PEPE", len(empty_hits) == 0)


# ── Test 9: Memory Clearing ──

def test_memory_clearing():
    print("\n\U0001f5d1 Test 9: Memory Clearing")
    setup()

    user_id = 9001
    m = mem.get_user_memory(user_id)

    m.record("user", "Some message")
    m.record("assistant", "Some reply")
    m.update_preferences({"trading_style": "aggressive"})

    stats_before = m.get_stats()
    check("Has data before clear", stats_before["conversations"] == 2)

    m.clear()

    stats_after = m.get_stats()
    check("Conversations cleared", stats_after["conversations"] == 0)
    check("Summaries cleared", stats_after["summaries"] == 0)
    check("Preferences cleared", not stats_after["has_preferences"])


# ── Test 10: Multi-turn Messages ──

def test_multiturn_messages():
    print("\n\U0001f501 Test 10: Multi-turn Message Format")
    setup()

    user_id = 10001
    m = mem.get_user_memory(user_id)

    m.record("user", "What's BTC doing?")
    m.record("assistant", "BTC is at $95K, looking strong.")
    m.record("user", "Should I buy?")
    m.record("assistant", "A small position could work. Consider 0.001 BTC.")

    messages = m.get_conversation_messages()
    check("Returns 4 messages", len(messages) == 4, f"got {len(messages)}")
    check("Alternating roles", messages[0]["role"] == "user" and messages[1]["role"] == "assistant")
    check("API format (role + content)", all("role" in m and "content" in m for m in messages))


# ── Test 11: Memory Stats ──

def test_memory_stats():
    print("\n\U0001f4ca Test 11: Memory Stats")
    setup()

    user_id = 11001
    m = mem.get_user_memory(user_id)

    stats = m.get_stats()
    check("Empty stats initially", stats["conversations"] == 0)

    m.record("user", "Hello")
    m.record("assistant", "Hi!")
    m.update_preferences({"language": "Chinese"})

    stats = m.get_stats()
    check("Counts conversations", stats["conversations"] == 2)
    check("Has preferences", stats["has_preferences"])
    check("Oldest timestamp exists", stats["oldest_ts"] is not None)


# ── Test 12: Context With Preferences and Summaries ──

def test_full_context():
    print("\n\U0001f3af Test 12: Full Context Integration")
    setup()

    user_id = 12001
    m = mem.get_user_memory(user_id)

    # Set preferences
    m.update_preferences({
        "trading_style": "swing trader",
        "favorite_assets": ["BTC", "SOL"],
        "risk_tolerance": "medium",
    })

    # Add some conversation
    m.record("user", "SOL looks like it's about to break out")
    m.record("assistant", "Yes, SOL is showing bullish divergence on the 4h chart.")

    # Add a summary
    m.save_summary(
        summary="User is a swing trader focused on BTC and SOL. Prefers medium risk.",
        keywords="swing,btc,sol,medium risk",
        turns=[{"created_at": time.time() - 100}, {"created_at": time.time()}],
    )

    # Build context for a SOL-related query
    context = m.get_context_for_prompt("Should I open a SOL position?")

    check("Has user profile section", "User Profile" in context)
    check("Shows trading style", "swing trader" in context)
    check("Shows favorite assets", "BTC" in context)
    check("Has relevant past context", "Relevant Past Context" in context or "Recent Conversation" in context)
    check("Has recent conversation", "Recent Conversation" in context)


# ── Test 13: Summarization Prompt Building ──

def test_summarization_prompt():
    print("\n\U0001f4dd Test 13: Summarization Prompt")
    setup()

    turns = [
        {"role": "user", "content": "I love BTC and want to trade it daily"},
        {"role": "assistant", "content": "Great! BTC is perfect for daily trading."},
        {"role": "user", "content": "What about risk? I'm conservative."},
        {"role": "assistant", "content": "For conservative trading, use small sizes and tight stops."},
    ]

    prompt = mem.build_summarization_prompt(turns)
    check("Prompt contains conversation", "BTC" in prompt)
    check("Prompt asks for JSON", "JSON" in prompt)
    check("Prompt asks for preferences", "preferences" in prompt)
    check("Prompt asks for summary", "summary" in prompt)


# ── Test 14: Old Conversation Cleanup ──

def test_cleanup():
    print("\n\U0001f9f9 Test 14: Old Conversation Cleanup")
    setup()

    user_id = 14001
    m = mem.get_user_memory(user_id)

    # Record many messages
    for i in range(50):
        m.record("user", f"Message {i}")

    count_before = db.get_conversation_count(user_id)
    check("50 messages stored", count_before == 50, f"got {count_before}")

    # Force cleanup with low keep limit
    db.delete_old_conversations(user_id, keep_recent=10)
    count_after = db.get_conversation_count(user_id)
    check("Cleaned to 10", count_after == 10, f"got {count_after}")

    # Verify newest are kept
    recent = m.get_working_memory(limit=10)
    check("Newest kept", "Message 49" in recent[-1]["content"], f"got: {recent[-1]['content']}")


# ── Test 15: Memory Singleton Cache ──

def test_singleton_cache():
    print("\n\U0001f504 Test 15: Singleton Memory Cache")
    setup()

    m1 = mem.get_user_memory(15001)
    m2 = mem.get_user_memory(15001)
    m3 = mem.get_user_memory(15002)

    check("Same user returns same instance", m1 is m2)
    check("Different user returns different instance", m1 is not m3)


# ── Run all tests ──

if __name__ == "__main__":
    print("=" * 50)
    print("\U0001f9e0 Memory System Test Suite")
    print("=" * 50)

    try:
        test_conversation_recording()
        test_memory_isolation()
        test_context_building()
        test_user_preferences()
        test_keyword_extraction()
        test_summarization_trigger()
        test_memory_summary()
        test_conversation_search()
        test_memory_clearing()
        test_multiturn_messages()
        test_memory_stats()
        test_full_context()
        test_summarization_prompt()
        test_cleanup()
        test_singleton_cache()
    finally:
        teardown()

    print(f"\n{'=' * 50}")
    print(f"\U0001f3c1 Results: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 50}")

    sys.exit(0 if failed == 0 else 1)
