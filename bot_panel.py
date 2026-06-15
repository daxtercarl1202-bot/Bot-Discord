import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import requests
import os
import json
import time
from dotenv import load_dotenv

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "bot_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

config = load_config()
TOKEN = config.get("token") or os.getenv("DISCORD_TOKEN")
OWNER_ID = config.get("owner_id") or 0

if not TOKEN or not OWNER_ID:
    root = tk.Tk()
    root.title("Setup Bot Panel")
    root.geometry("400x250")
    root.configure(bg="#1e1e1e")
    tk.Label(root, text="Bot Panel - First Time Setup", font=("Arial", 14, "bold"), fg="#1e90ff", bg="#1e1e1e").pack(pady=(20,10))
    tk.Label(root, text="Discord Bot Token:", fg="#fff", bg="#1e1e1e").pack()
    token_entry = tk.Entry(root, width=40, bg="#2d2d2d", fg="#fff", insertbackground="white")
    token_entry.pack(pady=5)
    if TOKEN:
        token_entry.insert(0, TOKEN)
    tk.Label(root, text="Owner Discord ID:", fg="#fff", bg="#1e1e1e").pack()
    owner_entry = tk.Entry(root, width=40, bg="#2d2d2d", fg="#fff", insertbackground="white")
    owner_entry.pack(pady=5)
    if OWNER_ID:
        owner_entry.insert(0, str(OWNER_ID))
    def save_and_continue():
        t = token_entry.get().strip()
        o = owner_entry.get().strip()
        if t and o:
            save_config({"token": t, "owner_id": int(o)})
            root.destroy()
        else:
            messagebox.showwarning("Error", "Please fill all fields!")
    tk.Button(root, text="Save & Continue", bg="#238636", fg="#fff", font=("Arial", 10, "bold"), bd=0, padx=20, pady=8, command=save_and_continue).pack(pady=20)
    root.mainloop()
    config = load_config()
    TOKEN = config.get("token")
    OWNER_ID = config.get("owner_id", 0)

HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
API = "https://discord.com/api/v10"

class BotPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Bot DarkN2ss (I'mDaxx) Control Panel")
        self.root.geometry("780x720")
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, False)

        self.guilds = []
        self.channels = []
        self.selected_guild_id = None
        self.selected_channel_id = None

        self.setup_ui()
        self.log("Panel ready.")
        threading.Thread(target=self.fetch_guilds, daemon=True).start()

    def log(self, msg):
        self.console.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.console.see(tk.END)

    def setup_ui(self):
        title = tk.Label(self.root, text="Bot DarkN2ss (I'mDaxx) Control Panel", font=("Arial", 20, "bold"), fg="#1e90ff", bg="#1e1e1e")
        title.pack(pady=(10, 2))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tab_channel = tk.Frame(self.notebook, bg="#1e1e1e")
        self.tab_dm = tk.Frame(self.notebook, bg="#1e1e1e")
        self.notebook.add(self.tab_channel, text=" Send to Channel ")
        self.notebook.add(self.tab_dm, text=" Send to User (DM) ")

        self.setup_channel_tab()
        self.setup_dm_tab()

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        console_frame = tk.LabelFrame(self.root, text="Console", fg="#fff", bg="#1e1e1e", font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
        console_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10), ipady=3)

        self.console = tk.Text(console_frame, bg="#121212", fg="#4af626", font=("Consolas", 9), bd=0, wrap=tk.WORD, height=7)
        self.console.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scroll = tk.Scrollbar(console_frame, command=self.console.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.console.config(yscrollcommand=scroll.set)

    # ========== CHANNEL TAB ==========
    def setup_channel_tab(self):
        left = tk.Frame(self.tab_channel, bg="#1e1e1e", width=300)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 5), pady=10)

        g_frame = tk.LabelFrame(left, text="Server", fg="#fff", bg="#1e1e1e", font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
        g_frame.pack(fill=tk.X, pady=(0, 10))
        self.guild_combo = ttk.Combobox(g_frame, state="readonly", width=28)
        self.guild_combo.pack(padx=8, pady=8, fill=tk.X)
        self.guild_combo.bind("<<ComboboxSelected>>", self.on_guild_select)

        c_frame = tk.LabelFrame(left, text="Channel", fg="#fff", bg="#1e1e1e", font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
        c_frame.pack(fill=tk.X, pady=(0, 10))
        self.channel_combo = ttk.Combobox(c_frame, state="readonly", width=28)
        self.channel_combo.pack(padx=8, pady=8, fill=tk.X)
        self.channel_combo.bind("<<ComboboxSelected>>", self.on_channel_select)

        self.status_label = tk.Label(left, text="Status: Selecting server...", fg="#ffcc00", bg="#1e1e1e", font=("Arial", 9))
        self.status_label.pack(anchor="w", pady=(5, 0))

        right = tk.Frame(self.tab_channel, bg="#1e1e1e")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 10), pady=10)

        msg_frame = tk.LabelFrame(right, text="Write Message", fg="#fff", bg="#1e1e1e", font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
        msg_frame.pack(fill=tk.BOTH, expand=True)

        self.message_text = tk.Text(msg_frame, bg="#121212", fg="#fff", font=("Arial", 10), bd=0, wrap=tk.WORD, height=8, insertbackground="white")
        self.message_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        btn_frame = tk.Frame(msg_frame, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.send_btn = tk.Button(btn_frame, text="Send Message", bg="#0056b3", fg="#fff", font=("Arial", 10, "bold"), bd=0, padx=15, pady=6, command=self.send_message)
        self.send_btn.pack(side=tk.RIGHT)

        self.refresh_btn = tk.Button(btn_frame, text="Refresh", bg="#2d2d2d", fg="#fff", bd=0, padx=10, pady=6, command=self.refresh)
        self.refresh_btn.pack(side=tk.RIGHT, padx=(0, 8))

    # ========== DM TAB ==========
    def setup_dm_tab(self):
        main = tk.Frame(self.tab_dm, bg="#1e1e1e")
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        id_frame = tk.LabelFrame(main, text="User ID", fg="#fff", bg="#1e1e1e", font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
        id_frame.pack(fill=tk.X, pady=(0, 5), ipady=3)

        row = tk.Frame(id_frame, bg="#1e1e1e")
        row.pack(fill=tk.X, padx=8, pady=5)

        self.dm_user_id = tk.Entry(row, bg="#2d2d2d", fg="#fff", font=("Arial", 10), bd=1, relief=tk.SOLID, insertbackground="white")
        self.dm_user_id.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.dm_user_id.insert(0, "Enter target User ID...")
        self.dm_user_id.bind("<FocusIn>", lambda e: self.dm_user_id.delete(0, tk.END) if self.dm_user_id.get() == "Enter target User ID..." else None)
        self.dm_user_id.bind("<FocusOut>", self.on_dm_user_id_entered)

        self.dm_auto_timer = None
        self.dm_auto_running = False

        # Send area (always visible first)
        send_frame = tk.LabelFrame(main, text="Send Message", fg="#fff", bg="#1e1e1e", font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
        send_frame.pack(fill=tk.X, pady=(0, 5))

        self.dm_message = tk.Text(send_frame, bg="#121212", fg="#fff", font=("Arial", 10), bd=0, wrap=tk.WORD, height=4, insertbackground="white")
        self.dm_message.pack(fill=tk.X, padx=8, pady=(8, 4))

        btn_row = tk.Frame(send_frame, bg="#1e1e1e")
        btn_row.pack(fill=tk.X, padx=8, pady=(0, 8))

        self.dm_send_btn = tk.Button(btn_row, text="Send DM", bg="#9b59b6", fg="#fff", font=("Arial", 10, "bold"), bd=0, padx=15, pady=6, command=self.send_dm)
        self.dm_send_btn.pack(side=tk.RIGHT)

        # Chat display area
        chat_frame = tk.LabelFrame(main, text="Chat History", fg="#fff", bg="#1e1e1e", font=("Arial", 10, "bold"), bd=1, relief=tk.SOLID)
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

        self.chat_display = tk.Text(chat_frame, bg="#121212", fg="#fff", font=("Consolas", 9), bd=0, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        chat_scroll = tk.Scrollbar(chat_frame, command=self.chat_display.yview)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_display.config(yscrollcommand=chat_scroll.set)

    # ========== CHANNEL LOGIC ==========
    def fetch_guilds(self):
        try:
            r = requests.get(f"{API}/users/@me/guilds", headers=HEADERS)
            if r.status_code == 200:
                self.guilds = r.json()
                names = [f"{g['name']} ({g['id']})" for g in self.guilds]
                self.guild_combo["values"] = names
                if names:
                    self.guild_combo.set(names[0])
                    self.selected_guild_id = self.guilds[0]["id"]
                    self.log(f"Loaded {len(self.guilds)} servers")
                    threading.Thread(target=self.fetch_channels, daemon=True).start()
            else:
                self.log(f"Failed to fetch guilds: {r.status_code}")
                self.status_label.config(text="Status: Token invalid?", fg="#f27963")
        except Exception as e:
            self.log(f"Error: {e}")

    def fetch_channels(self):
        if not self.selected_guild_id:
            return
        try:
            r = requests.get(f"{API}/guilds/{self.selected_guild_id}/channels", headers=HEADERS)
            if r.status_code == 200:
                all_ch = r.json()
                self.channels = [c for c in all_ch if c["type"] in (0, 2)]
                names = [f"{'[TEXT]' if c['type']==0 else '[VC]'} {c['name']} ({c['id']})" for c in self.channels]
                self.channel_combo["values"] = names
                if names:
                    self.channel_combo.set(names[0])
                    self.selected_channel_id = self.channels[0]["id"]
                self.log(f"Loaded {len(self.channels)} channels")
                self.status_label.config(text="Status: Ready to send", fg="#4bc0a1")
            else:
                self.log(f"Failed to fetch channels: {r.status_code}")
        except Exception as e:
            self.log(f"Error: {e}")

    def on_guild_select(self, event):
        idx = self.guild_combo.current()
        if idx >= 0:
            self.selected_guild_id = self.guilds[idx]["id"]
            self.status_label.config(text="Status: Loading channels...", fg="#ffcc00")
            threading.Thread(target=self.fetch_channels, daemon=True).start()

    def on_channel_select(self, event):
        idx = self.channel_combo.current()
        if idx >= 0:
            self.selected_channel_id = self.channels[idx]["id"]

    def send_message(self):
        if not self.selected_channel_id:
            messagebox.showwarning("Error", "Select a channel first!")
            return
        msg = self.message_text.get("1.0", tk.END).strip()
        if not msg:
            messagebox.showwarning("Error", "Empty message!")
            return
        self.send_btn.config(state=tk.DISABLED, text="Sending...")
        threading.Thread(target=self._do_send, args=(msg,), daemon=True).start()

    def _do_send(self, msg):
        try:
            r = requests.post(f"{API}/channels/{self.selected_channel_id}/messages", headers=HEADERS, json={"content": msg})
            if r.status_code == 200:
                self.log(f"Message sent to <#{self.selected_channel_id}>")
                self.root.after(0, lambda: self.message_text.delete("1.0", tk.END))
            else:
                err = r.json().get("message", r.status_code)
                self.log(f"Failed to send: {err}")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send: {err}"))
        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self.root.after(0, lambda: self.send_btn.config(state=tk.NORMAL, text="Send Message"))

    # ========== DM LOGIC ==========
    def on_dm_user_id_entered(self, event=None):
        uid = self.dm_user_id.get().strip()
        if uid and uid != "Enter target User ID...":
            self.stop_dm_auto_refresh()
            self.start_dm_auto_refresh(uid)

    def on_tab_change(self, event=None):
        tab = self.notebook.index(self.notebook.select())
        if tab == 1:  # DM tab
            uid = self.dm_user_id.get().strip()
            if uid and uid != "Enter target User ID...":
                self.start_dm_auto_refresh(uid)
        else:
            self.stop_dm_auto_refresh()

    def start_dm_auto_refresh(self, uid):
        self.stop_dm_auto_refresh()
        self.dm_auto_running = True
        self._do_read_dm(uid)
        self._dm_auto_loop(uid)

    def stop_dm_auto_refresh(self):
        self.dm_auto_running = False
        if self.dm_auto_timer:
            self.root.after_cancel(self.dm_auto_timer)
            self.dm_auto_timer = None

    def _dm_auto_loop(self, uid):
        if not self.dm_auto_running:
            return
        self._do_read_dm(uid)
        self.dm_auto_timer = self.root.after(8000, lambda: self._dm_auto_loop(uid))

    def _do_read_dm(self, uid):
        try:
            r = requests.post(f"{API}/users/{uid}/channels", headers=HEADERS, json={"recipient_id": uid})
            if r.status_code != 200:
                return
            dm_id = r.json()["id"]
            r2 = requests.get(f"{API}/channels/{dm_id}/messages?limit=30", headers=HEADERS)
            if r2.status_code != 200:
                return
            msgs = r2.json()
            msgs.reverse()
            lines = []
            for m in msgs:
                author = m["author"]["username"]
                content = m.get("content", "")
                ts = m["timestamp"][:19].replace("T", " ")
                lines.append(f"[{ts}] {author}: {content}")
            text = "\n".join(lines) if lines else "(empty chat)"
            self.root.after(0, lambda: self._update_chat(text))
        except:
            pass

    def _update_chat(self, text):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.insert("1.0", text)
        self.chat_display.config(state=tk.DISABLED)

    def send_dm(self):
        uid = self.dm_user_id.get().strip()
        if not uid or uid == "Enter target User ID...":
            messagebox.showwarning("Error", "Enter a User ID first!")
            return
        msg = self.dm_message.get("1.0", tk.END).strip()
        if not msg:
            messagebox.showwarning("Error", "No message to send!")
            return
        self.dm_send_btn.config(state=tk.DISABLED, text="Sending...")
        threading.Thread(target=self._do_send_dm, args=(uid, msg), daemon=True).start()

    def _do_send_dm(self, uid, msg):
        try:
            # 1. Create DM channel
            r = requests.post(f"{API}/users/{uid}/channels", headers=HEADERS, json={"recipient_id": uid})
            if r.status_code != 200:
                err = r.json().get("message", r.status_code)
                self.log(f"Failed to create DM: {err}")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to create DM: {err}"))
                return
            dm_channel_id = r.json()["id"]

            # 2. Send message
            r2 = requests.post(f"{API}/channels/{dm_channel_id}/messages", headers=HEADERS, json={"content": msg})
            if r2.status_code == 200:
                self.log(f"DM sent to user {uid}")
                self.root.after(0, lambda: self.dm_message.delete("1.0", tk.END))
            else:
                err = r2.json().get("message", r2.status_code)
                self.log(f"Failed to send DM: {err}")
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send DM: {err}"))
        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self.root.after(0, lambda: self.dm_send_btn.config(state=tk.NORMAL, text="Send DM"))

    def refresh(self):
        self.log("Refreshing...")
        threading.Thread(target=self.fetch_guilds, daemon=True).start()

if __name__ == "__main__":
    if not TOKEN:
        tk.messagebox.showerror("Error", "Token not found. Please restart to set it up.")
        exit()
    root = tk.Tk()
    app = BotPanel(root)
    root.mainloop()
