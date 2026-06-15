import threading, requests, os, json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.template_folder = os.path.join(os.path.dirname(__file__), "templates")

TOKEN = os.getenv("DISCORD_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
HEADERS = {}
API = "https://discord.com/api/v10"

def update_headers():
    global HEADERS
    if TOKEN:
        HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
update_headers()

def get_bot_name():
    try:
        r = requests.get(f"{API}/users/@me", headers=HEADERS, timeout=5)
        if r.status_code == 200:
            return r.json().get("username", "Bot Panel")
    except: pass
    return "Bot Panel"

@app.route("/")
def index():
    return render_template("index.html", bot_name=get_bot_name())

@app.route("/api/guilds")
def api_guilds():
    if not HEADERS: return jsonify({"error":"Not configured"}),400
    try:
        r = requests.get(f"{API}/users/@me/guilds", headers=HEADERS, timeout=10)
        return jsonify([{"id":g["id"],"name":g["name"]} for g in r.json()]) if r.status_code==200 else (jsonify({"error":r.text}), r.status_code)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/channels/<guild_id>")
def api_channels(guild_id):
    if not HEADERS: return jsonify({"error":"Not configured"}),400
    try:
        r = requests.get(f"{API}/guilds/{guild_id}/channels", headers=HEADERS, timeout=10)
        if r.status_code==200:
            channels = [{"id":c["id"],"name":c["name"],"type":"text" if c["type"]==0 else "voice"} for c in r.json() if c["type"] in (0,2)]
            return jsonify(channels)
        return jsonify({"error":r.text}),r.status_code
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/send", methods=["POST"])
def api_send():
    if not HEADERS: return jsonify({"error":"Not configured"}),400
    data = request.json
    if not data.get("channel_id") or not data.get("content","").strip():
        return jsonify({"error":"Missing fields"}),400
    try:
        r = requests.post(f"{API}/channels/{data['channel_id']}/messages", headers=HEADERS, json={"content":data["content"]}, timeout=10)
        return (jsonify({"ok":True}) if r.status_code==200 else jsonify({"error":r.json().get("message",r.status_code)}), r.status_code)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dm/send", methods=["POST"])
def api_dm_send():
    if not HEADERS: return jsonify({"error":"Not configured"}),400
    data = request.json
    if not data.get("user_id") or not data.get("content","").strip():
        return jsonify({"error":"Missing fields"}),400
    try:
        r = requests.post(f"{API}/users/{data['user_id']}/channels", headers=HEADERS, json={"recipient_id":data["user_id"]}, timeout=10)
        if r.status_code!=200: return jsonify({"error":r.json().get("message",r.status_code)}),r.status_code
        r2 = requests.post(f"{API}/channels/{r.json()['id']}/messages", headers=HEADERS, json={"content":data["content"]}, timeout=10)
        return (jsonify({"ok":True}) if r2.status_code==200 else jsonify({"error":r2.json().get("message",r2.status_code)}), r2.status_code)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/dm/chat/<user_id>")
def api_dm_chat(user_id):
    if not HEADERS: return jsonify({"error":"Not configured"}),400
    try:
        r = requests.post(f"{API}/users/{user_id}/channels", headers=HEADERS, json={"recipient_id":user_id}, timeout=10)
        if r.status_code!=200: return jsonify({"error":"Invalid user"}),400
        r2 = requests.get(f"{API}/channels/{r.json()['id']}/messages?limit=30", headers=HEADERS, timeout=10)
        if r2.status_code==200:
            msgs = r2.json(); msgs.reverse()
            return jsonify([{"author":m["author"]["username"],"content":m.get("content",""),"timestamp":m["timestamp"][:19].replace("T"," ")} for m in msgs])
        return jsonify({"error":r2.text}),r2.status_code
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/status")
def api_status():
    if not HEADERS: return jsonify({"ok":False,"message":"Not configured"})
    try:
        r = requests.get(f"{API}/users/@me", headers=HEADERS, timeout=5)
        if r.status_code==200:
            bot = r.json()
            r2 = requests.get(f"{API}/users/@me/guilds", headers=HEADERS, timeout=5)
            return jsonify({"ok":True,"bot":bot["username"],"guilds":len(r2.json()) if r2.status_code==200 else 0})
        return jsonify({"ok":False,"message":f"Token invalid ({r.status_code})"})
    except Exception as e: return jsonify({"ok":False,"message":str(e)})

def run():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start():
    t = threading.Thread(target=run, daemon=True)
    t.start()
    print(f"[Web Panel] Running on port {os.getenv('PORT', 5000)}")
