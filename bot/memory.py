"""Per-user memory system inspired by OpenClaw's 5-tier architecture.

Simplified for TG bot: 3 tiers
  T0 — Working memory: last N messages (raw conversation history)
  T1 — Short-term: session summaries (AI-compressed conversation chunks)
  T2 — Long-term: user preferences + key facts extracted over time

Storage: SQLite via db.py (conversations, memory_summaries, user_preferences)
Search: keyword-based (LIKE queries) — no embeddings needed for our scale
"""
import logging
import time
import json
import re
from typing import Optional

import db

logger = logging.getLogger(__name__)

# ── Configuration ──
WORKING_MEMORY_SIZE = 16          # last N messages kept in prompt
SUMMARY_THRESHOLD = 10            # summarize after this many un-summarized turns
MAX_CONVERSATIONS_STORED = 500    # max raw messages per user before cleanup
CONTEXT_WINDOW_TOKENS = 2000     # approx chars budget for memory context in prompt
PREFERENCE_EXTRACT_INTERVAL = 30  # re-extract preferences every N messages


class UserMemory:
    """Manages memory for a single user."""

    def __init__(self, tg_user_id: int):
        self.user_id = tg_user_id

    def record(self, role: str, content: str, metadata: dict = None):
        """Record a conversation turn (user or assistant message)."""
        if not content or not content.strip():
            return
        # Truncate extremely long messages
        content = content[:3000]
        db.save_conversation(self.user_id, role, content, metadata)
        # Periodic cleanup
        count = db.get_conversation_count(self.user_id)
        if count > MAX_CONVERSATIONS_STORED:
            db.delete_old_conversations(self.user_id, keep_recent=MAX_CONVERSATIONS_STORED)

    def get_working_memory(self, limit: int = None) -> list:
        """Get recent conversation turns for prompt injection (T0)."""
        n = limit or WORKING_MEMORY_SIZE
        return db.get_recent_conversations(self.user_id, limit=n)

    def get_context_for_prompt(self, user_message: str = "") -> str:
        """Build memory context string to inject into AI system prompt.

        Combines:
        1. User preferences (T2 — long-term facts)
        2. Relevant memory summaries (T1 — compressed history)
        3. Recent conversation history (T0 — working memory)
        """
        parts = []
        budget = CONTEXT_WINDOW_TOKENS

        # T2: User preferences (always included, small)
        prefs = db.get_user_preferences(self.user_id)
        if prefs:
            pref_lines = []
            if prefs.get("trading_style"):
                pref_lines.append(f"Trading style: {prefs['trading_style']}")
            if prefs.get("favorite_assets"):
                pref_lines.append(f"Favorite assets: {', '.join(prefs['favorite_assets'])}")
            if prefs.get("risk_tolerance"):
                pref_lines.append(f"Risk tolerance: {prefs['risk_tolerance']}")
            if prefs.get("language"):
                pref_lines.append(f"Preferred language: {prefs['language']}")
            if prefs.get("notes"):
                for note in prefs["notes"][-5:]:
                    pref_lines.append(f"Note: {note}")
            if pref_lines:
                pref_text = "\n".join(pref_lines)
                parts.append(f"## User Profile\n{pref_text}")
                budget -= len(pref_text)

        # T1: Search memory summaries for relevant context
        if user_message:
            keywords = _extract_keywords(user_message)
            relevant_summaries = []
            for kw in keywords[:3]:
                hits = db.search_memory_summaries(self.user_id, kw, limit=2)
                for h in hits:
                    if h not in relevant_summaries:
                        relevant_summaries.append(h)

            if relevant_summaries:
                summ_lines = []
                for s in relevant_summaries[:3]:
                    text = s["summary"][:300]
                    summ_lines.append(f"- {text}")
                summ_text = "\n".join(summ_lines)
                if len(summ_text) < budget:
                    parts.append(f"## Relevant Past Context\n{summ_text}")
                    budget -= len(summ_text)

        # T0: Recent conversation history
        recent = self.get_working_memory()
        if recent:
            history_lines = []
            for msg in recent:
                role_label = "User" if msg["role"] == "user" else "Agent"
                text = msg["content"][:200]
                history_lines.append(f"{role_label}: {text}")
            history_text = "\n".join(history_lines)
            # Trim to budget
            if len(history_text) > budget:
                history_text = history_text[-budget:]
                # Clean up partial first line
                nl = history_text.find("\n")
                if nl > 0:
                    history_text = history_text[nl + 1:]
            parts.append(f"## Recent Conversation\n{history_text}")

        if not parts:
            return ""
        return "\n\n".join(parts)

    def get_conversation_messages(self, limit: int = None) -> list:
        """Get recent messages formatted for API multi-turn conversation.

        Returns list of {"role": "user"|"assistant", "content": "..."} dicts.
        """
        recent = self.get_working_memory(limit)
        messages = []
        for msg in recent:
            role = msg["role"]
            if role not in ("user", "assistant"):
                continue
            messages.append({"role": role, "content": msg["content"][:1500]})
        return messages

    def needs_summarization(self) -> bool:
        """Check if there are enough un-summarized turns to warrant compression."""
        summaries = db.get_memory_summaries(self.user_id, limit=1)
        if not summaries:
            count = db.get_conversation_count(self.user_id)
            return count >= SUMMARY_THRESHOLD
        latest_summary = summaries[-1]
        since = latest_summary.get("period_end", 0)
        unsummarized = db.get_conversations_since(self.user_id, since)
        return len(unsummarized) >= SUMMARY_THRESHOLD

    def get_unsummarized_turns(self) -> list:
        """Get conversation turns that haven't been summarized yet."""
        summaries = db.get_memory_summaries(self.user_id, limit=1)
        if summaries:
            since = summaries[-1].get("period_end", 0)
        else:
            since = 0
        return db.get_conversations_since(self.user_id, since)

    def save_summary(self, summary: str, keywords: str, turns: list):
        """Save a compressed memory summary."""
        if not turns:
            return
        period_start = turns[0]["created_at"]
        period_end = turns[-1]["created_at"]
        db.save_memory_summary(
            self.user_id, summary, keywords,
            turn_count=len(turns),
            period_start=period_start,
            period_end=period_end,
        )

    def update_preferences(self, prefs_update: dict):
        """Merge new preferences into existing ones."""
        current = db.get_user_preferences(self.user_id)
        for key, value in prefs_update.items():
            if key == "favorite_assets" and isinstance(value, list):
                existing = set(current.get("favorite_assets", []))
                existing.update(value)
                current["favorite_assets"] = sorted(existing)[:20]
            elif key == "notes" and isinstance(value, list):
                existing = current.get("notes", [])
                existing.extend(value)
                current["notes"] = existing[-20:]  # keep last 20 notes
            else:
                current[key] = value
        db.save_user_preferences(self.user_id, current)

    def get_stats(self) -> dict:
        """Get memory statistics for this user."""
        stats = db.get_memory_stats(self.user_id)
        prefs = db.get_user_preferences(self.user_id)
        stats["has_preferences"] = bool(prefs)
        stats["preference_keys"] = list(prefs.keys()) if prefs else []
        return stats

    def clear(self):
        """Clear all memory for this user."""
        db.clear_user_memory(self.user_id)


def build_summarization_prompt(turns: list) -> str:
    """Build a prompt for the AI to summarize a conversation chunk."""
    lines = []
    for t in turns:
        role = "User" if t["role"] == "user" else "Agent"
        lines.append(f"{role}: {t['content'][:300]}")
    conversation = "\n".join(lines)

    return (
        "Summarize this conversation between a user and their AI trading agent. "
        "Extract:\n"
        "1. Key facts about the user (trading preferences, risk tolerance, favorite assets)\n"
        "2. Important decisions or trades discussed\n"
        "3. Any user preferences or requests to remember\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"summary": "2-3 sentence summary", "keywords": "comma,separated,keywords", '
        '"preferences": {"trading_style": "...", "favorite_assets": [...], "risk_tolerance": "...", "notes": [...]}}\n\n'
        f"Conversation:\n{conversation}"
    )


def build_preference_extraction_prompt(turns: list) -> str:
    """Build a prompt to extract user preferences from recent conversations."""
    lines = []
    for t in turns[-30:]:
        role = "User" if t["role"] == "user" else "Agent"
        lines.append(f"{role}: {t['content'][:200]}")
    conversation = "\n".join(lines)

    return (
        "Analyze this conversation and extract any user preferences or facts to remember. "
        "Look for: favorite assets, trading style, risk tolerance, language preference, "
        "specific instructions, goals, or personal facts.\n\n"
        "Respond with ONLY a JSON object (empty {} if nothing to extract):\n"
        '{"trading_style": "...", "favorite_assets": [...], "risk_tolerance": "...", '
        '"language": "...", "notes": ["fact1", "fact2"]}\n\n'
        f"Conversation:\n{conversation}"
    )


def _extract_keywords(text: str) -> list:
    """Extract search keywords from a user message."""
    # Remove common stop words and short tokens
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "each",
        "every", "both", "few", "more", "most", "other", "some", "such", "no",
        "not", "only", "own", "same", "so", "than", "too", "very", "just",
        "don", "now", "this", "that", "what", "which", "who", "whom",
        "i", "me", "my", "we", "our", "you", "your", "he", "him", "she", "her",
        "it", "its", "they", "them", "their",
        # Chinese stop words
        "的", "是", "在", "了", "不", "和", "有", "我", "你", "他", "她", "它",
        "们", "这", "那", "什么", "怎么", "吗", "呢", "吧", "啊", "嗯",
        "一", "个", "也", "都", "就", "还", "很", "但", "可以", "现在",
        "想", "看", "看看", "帮", "帮我",
    }
    # Tokenize: split on whitespace and CJK boundaries
    tokens = re.findall(r'[A-Za-z]+|[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+', text)
    keywords = []
    for t in tokens:
        t_lower = t.lower()
        if t_lower not in stop_words and len(t) >= 2:
            keywords.append(t_lower)
    # Prioritize: known asset names, longer tokens
    try:
        from config import CONTRACTS
        known_assets = set(CONTRACTS.keys())
    except ImportError:
        known_assets = {
            "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "PEPE", "SUI", "AVAX", "LINK",
            "ADA", "DOT", "NEAR", "UNI", "ARB", "OP", "APT", "TIA", "WIF", "TON",
            "TRUMP", "AAPL", "TSLA", "NVDA", "AAVE", "CRV", "ONDO", "JUP", "PENGU",
            "KAITO", "XAUT", "SILVER", "CRCL", "AMZN", "GOOG", "META",
        }
    asset_keywords = []
    other_keywords = []
    for kw in keywords:
        if kw.upper() in known_assets:
            asset_keywords.append(kw)
        else:
            other_keywords.append(kw)
    return asset_keywords + other_keywords


# ── Singleton memory manager cache ──
_memory_cache = {}


def get_user_memory(tg_user_id: int) -> UserMemory:
    """Get or create a UserMemory instance for a user."""
    if tg_user_id not in _memory_cache:
        _memory_cache[tg_user_id] = UserMemory(tg_user_id)
    return _memory_cache[tg_user_id]
