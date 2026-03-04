"""Feedback dashboard — view, mark, reply to user feedback.
Run: python3 feedback_web.py
Access: http://server:8901/?key=<ADMIN_KEY>
"""
import os
import time
import json
from string import Template
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import db

ADMIN_KEY = os.getenv("FEEDBACK_ADMIN_KEY", "edgex-feedback-2026")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
PORT = int(os.getenv("FEEDBACK_PORT", "8901"))


def send_tg_message(chat_id: int, text: str):
    if not BOT_TOKEN:
        return False
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"Failed to send TG message: {e}")
        return False


HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>edgeX Agent — Admin</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #0d1117; color: #c9d1d9; }
  h1 { color: #58a6ff; }
  .nav { display: flex; gap: 10px; margin: 10px 0; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
  .nav a { padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: 600; }
  .nav a.active { background: #1f6feb; color: white; }
  .nav a:not(.active) { background: #21262d; color: #8b949e; }
  .tabs { display: flex; gap: 10px; margin: 20px 0; flex-wrap: wrap; }
  .tab { padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; }
  .tab.active { background: #238636; color: white; }
  .tab:not(.active) { background: #21262d; color: #8b949e; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 12px 0; }
  .card .meta { color: #8b949e; font-size: 13px; margin-bottom: 8px; }
  .card .msg { font-size: 15px; line-height: 1.5; white-space: pre-wrap; }
  .card .reply-box { margin-top: 12px; }
  .card textarea { width: 100%; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 8px; font-size: 14px; resize: vertical; }
  .btn { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; margin-right: 6px; }
  .btn-resolve { background: #238636; color: white; }
  .btn-reply { background: #1f6feb; color: white; }
  .btn-wip { background: #d29922; color: white; }
  .status-new { color: #f85149; }
  .status-wip { color: #d29922; }
  .status-resolved { color: #3fb950; }
  .admin-reply { background: #1c2128; padding: 8px; border-radius: 4px; margin-top: 8px; border-left: 3px solid #1f6feb; }
  .empty { text-align: center; color: #8b949e; padding: 40px; }
  .count { background: #30363d; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 4px; }
  .chat-bubble { padding: 10px 14px; border-radius: 12px; margin: 6px 0; max-width: 80%; line-height: 1.5; }
  .chat-user { background: #1f6feb; color: white; margin-left: auto; text-align: right; }
  .chat-bot { background: #21262d; color: #c9d1d9; }
  .chat-time { font-size: 11px; color: #8b949e; margin-top: 2px; }
  .chat-container { display: flex; flex-direction: column; }
  .user-row { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid #21262d; cursor: pointer; text-decoration: none; color: #c9d1d9; }
  .user-row:hover { background: #161b22; }
  .user-row .name { font-weight: 600; color: #58a6ff; }
  .user-row .stats { color: #8b949e; font-size: 13px; }
</style>
</head>
<body>
<h1>edgeX Agent — Admin</h1>
<div class="nav">
  <a class="$nav_feedback" href="?key=$key&page=feedback">Feedback</a>
  <a class="$nav_users" href="?key=$key&page=users">Users & Conversations</a>
</div>
$content
</body>
</html>""")

FEEDBACK_TABS = Template("""
<div class="tabs">
  <a class="tab $active_all" href="?key=$key&page=feedback&filter=all">All <span class="count">$count_all</span></a>
  <a class="tab $active_new" href="?key=$key&page=feedback&filter=new">New <span class="count">$count_new</span></a>
  <a class="tab $active_wip" href="?key=$key&page=feedback&filter=wip">In Progress <span class="count">$count_wip</span></a>
  <a class="tab $active_resolved" href="?key=$key&page=feedback&filter=resolved">Resolved <span class="count">$count_resolved</span></a>
</div>
$cards
""")

CARD_TEMPLATE = Template("""<div class="card">
  <div class="meta">
    <strong>#$fid</strong> &middot;
    <span class="status-$status">$status</span> &middot;
    $user_display &middot;
    $time_display
  </div>
  <div class="msg">$message</div>
  $admin_reply_html
  <div class="reply-box">
    <form method="POST" action="?key=$key">
      <input type="hidden" name="id" value="$fid">
      <textarea name="reply" rows="2" placeholder="Reply to user (sent via Telegram)...">$existing_reply</textarea>
      <div style="margin-top:8px;">
        <button class="btn btn-reply" name="action" value="reply">Reply &amp; Send</button>
        <button class="btn btn-wip" name="action" value="wip">Mark In Progress</button>
        <button class="btn btn-resolve" name="action" value="resolve">Mark Resolved</button>
      </div>
    </form>
  </div>
</div>""")


def format_time(ts):
    if not ts:
        return "?"
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class FeedbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        key = params.get("key", [""])[0]
        if key != ADMIN_KEY:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden. Add ?key=YOUR_ADMIN_KEY")
            return

        db.init_db()
        page = params.get("page", ["feedback"])[0]

        if page == "users":
            content = self._render_users_page(params, key)
            nav_feedback, nav_users = "", "active"
        else:
            content = self._render_feedback_page(params, key)
            nav_feedback, nav_users = "active", ""

        html = HTML_TEMPLATE.substitute(
            key=key, content=content,
            nav_feedback=nav_feedback, nav_users=nav_users,
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _render_feedback_page(self, params, key):
        filter_status = params.get("filter", ["all"])[0]
        all_fb = db.get_all_feedback()
        count_new = sum(1 for f in all_fb if f["status"] == "new")
        count_wip = sum(1 for f in all_fb if f["status"] == "wip")
        count_resolved = sum(1 for f in all_fb if f["status"] == "resolved")

        if filter_status == "new":
            items = [f for f in all_fb if f["status"] == "new"]
        elif filter_status == "wip":
            items = [f for f in all_fb if f["status"] == "wip"]
        elif filter_status == "resolved":
            items = [f for f in all_fb if f["status"] == "resolved"]
        else:
            items = all_fb

        if not items:
            cards_html = '<div class="empty">No feedback yet.</div>'
        else:
            cards = []
            for f in items:
                user_display = f"@{f['tg_username']}" if f.get("tg_username") else f.get("tg_first_name", "User")
                user_display += f" (ID: {f['tg_user_id']})"
                admin_reply_html = ""
                if f.get("admin_reply"):
                    admin_reply_html = f'<div class="admin-reply">Admin: {f["admin_reply"]}</div>'
                cards.append(CARD_TEMPLATE.substitute(
                    fid=f["id"], status=f["status"], key=key,
                    user_display=user_display, time_display=format_time(f["created_at"]),
                    message=f["message"].replace("<", "&lt;").replace(">", "&gt;"),
                    admin_reply_html=admin_reply_html,
                    existing_reply=f.get("admin_reply", "") or "",
                ))
            cards_html = "\n".join(cards)

        return FEEDBACK_TABS.substitute(
            key=key, cards=cards_html,
            count_all=len(all_fb), count_new=count_new, count_wip=count_wip, count_resolved=count_resolved,
            active_all="active" if filter_status == "all" else "",
            active_new="active" if filter_status == "new" else "",
            active_wip="active" if filter_status == "wip" else "",
            active_resolved="active" if filter_status == "resolved" else "",
        )

    def _render_users_page(self, params, key):
        user_id = params.get("uid", [""])[0]

        if user_id:
            return self._render_user_conversations(int(user_id), key)

        # List all users with conversation history
        conn = db.get_conn()
        users = conn.execute("""
            SELECT c.tg_user_id, COUNT(*) as msg_count,
                   MIN(c.created_at) as first_msg, MAX(c.created_at) as last_msg,
                   u.personality, u.ai_base_url, u.ai_model
            FROM conversations c
            LEFT JOIN users u ON c.tg_user_id = u.tg_user_id
            GROUP BY c.tg_user_id
            ORDER BY last_msg DESC
        """).fetchall()
        conn.close()

        if not users:
            return '<div class="empty">No user conversations yet.</div>'

        rows = []
        for u in users:
            uid = u["tg_user_id"]
            stats = db.get_memory_stats(uid)
            prefs = db.get_user_preferences(uid)
            persona = u["personality"] or "default"
            pref_info = ""
            if prefs:
                parts = []
                if prefs.get("trading_style"):
                    parts.append(prefs["trading_style"])
                if prefs.get("favorite_assets"):
                    parts.append(f"Favs: {', '.join(prefs['favorite_assets'][:5])}")
                if parts:
                    pref_info = f' | {" | ".join(parts)}'

            rows.append(
                f'<a class="user-row" href="?key={key}&page=users&uid={uid}">'
                f'<div><div class="name">User {uid}</div>'
                f'<div class="stats">{u["msg_count"]} messages | '
                f'{stats["summaries"]} summaries | '
                f'Persona: {persona}{pref_info}</div>'
                f'<div class="stats">First: {format_time(u["first_msg"])} | '
                f'Last: {format_time(u["last_msg"])}</div>'
                f'</div></a>'
            )
        return '<div style="border:1px solid #30363d;border-radius:8px;overflow:hidden;">' + "\n".join(rows) + '</div>'

    def _render_user_conversations(self, user_id, key):
        stats = db.get_memory_stats(user_id)
        prefs = db.get_user_preferences(user_id)
        conversations = db.get_recent_conversations(user_id, limit=200)

        header = (
            f'<div style="margin:16px 0;">'
            f'<a href="?key={key}&page=users" style="color:#58a6ff;text-decoration:none;">&larr; Back to Users</a>'
            f'<h2 style="color:#c9d1d9;margin:8px 0;">User {user_id}</h2>'
            f'<div style="color:#8b949e;font-size:13px;">'
            f'Messages: {stats["conversations"]} | Summaries: {stats["summaries"]}'
        )

        if prefs:
            pref_parts = []
            if prefs.get("trading_style"):
                pref_parts.append(f'Style: {prefs["trading_style"]}')
            if prefs.get("favorite_assets"):
                pref_parts.append(f'Favs: {", ".join(prefs["favorite_assets"])}')
            if prefs.get("risk_tolerance"):
                pref_parts.append(f'Risk: {prefs["risk_tolerance"]}')
            if prefs.get("language"):
                pref_parts.append(f'Lang: {prefs["language"]}')
            if pref_parts:
                header += f'<br>Preferences: {" | ".join(pref_parts)}'
            if prefs.get("notes"):
                for note in prefs["notes"][-5:]:
                    header += f'<br>Note: {_esc(note)}'

        header += '</div></div>'

        # Summaries
        summaries = db.get_memory_summaries(user_id, limit=20)
        summ_html = ""
        if summaries:
            summ_html = '<details style="margin:12px 0;"><summary style="cursor:pointer;color:#58a6ff;">Memory Summaries ({} total)</summary>'.format(len(summaries))
            for s in summaries:
                summ_html += (
                    f'<div class="card" style="margin:6px 0;padding:10px;">'
                    f'<div class="meta">{format_time(s["created_at"])} | {s["turn_count"]} turns | Keywords: {_esc(s["keywords"])}</div>'
                    f'<div class="msg" style="font-size:13px;">{_esc(s["summary"])}</div>'
                    f'</div>'
                )
            summ_html += '</details>'

        # Conversation bubbles
        if not conversations:
            chat_html = '<div class="empty">No conversations.</div>'
        else:
            bubbles = []
            for msg in conversations:
                role = msg["role"]
                content = _esc(msg["content"][:1000])
                ts = format_time(msg["created_at"])
                if role == "user":
                    bubbles.append(
                        f'<div style="display:flex;justify-content:flex-end;">'
                        f'<div class="chat-bubble chat-user">{content}<div class="chat-time">{ts}</div></div></div>'
                    )
                else:
                    bubbles.append(
                        f'<div style="display:flex;justify-content:flex-start;">'
                        f'<div class="chat-bubble chat-bot">{content}<div class="chat-time">{ts}</div></div></div>'
                    )
            chat_html = '<div class="chat-container">' + "\n".join(bubbles) + '</div>'

        return header + summ_html + chat_html

    def do_POST(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        key = params.get("key", [""])[0]
        if key != ADMIN_KEY:
            self.send_response(403)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        form = parse_qs(body)
        fb_id = int(form.get("id", ["0"])[0])
        action = form.get("action", [""])[0]
        reply_text = form.get("reply", [""])[0]

        db.init_db()
        fb = db.get_feedback_by_id(fb_id)
        if not fb:
            self.send_response(404)
            self.end_headers()
            return

        if action == "reply" and reply_text.strip():
            db.update_feedback(fb_id, "resolved", reply_text.strip())
            msg = (
                f"\U0001f4ac **Feedback Update**\n\n"
                f"Your feedback: _{fb['message'][:100]}_\n\n"
                f"Reply: {reply_text.strip()}\n\n"
                f"Thanks for helping us improve!"
            )
            send_tg_message(fb["tg_user_id"], msg)
        elif action == "wip":
            db.update_feedback(fb_id, "wip", reply_text.strip() if reply_text.strip() else None)
        elif action == "resolve":
            db.update_feedback(fb_id, "resolved", reply_text.strip() if reply_text.strip() else None)
            if reply_text.strip():
                msg = (
                    f"\U0001f4ac **Feedback Update**\n\n"
                    f"Your feedback: _{fb['message'][:100]}_\n\n"
                    f"Reply: {reply_text.strip()}\n\n"
                    f"Thanks for helping us improve!"
                )
                send_tg_message(fb["tg_user_id"], msg)

        self.send_response(302)
        self.send_header("Location", f"?key={key}&filter=all")
        self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    db.init_db()
    if not BOT_TOKEN:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
        except Exception:
            pass
    print(f"Feedback dashboard on http://0.0.0.0:{PORT}/?key={ADMIN_KEY}")
    HTTPServer(("0.0.0.0", PORT), FeedbackHandler).serve_forever()
