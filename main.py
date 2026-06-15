import discord
from discord import app_commands
import os, sys, subprocess
import io
import json
import asyncio
import aiohttp
from dotenv import load_dotenv
import wavelink
from openai import AsyncOpenAI

# Pastiin PyNaCl keinstall
try:
    import nacl
except ImportError:
    print("PyNaCl belum keinstall, install otomatis...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyNaCl>=1.5.0"])
    import nacl
    print("PyNaCl berhasil diinstall")


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

import web
web.start()

OWNER_ID = 1286240448775720962

groq_client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

system_prompt = "Kamu adalah asisten AI yang ramah dan membantu. Jawab dengan bahasa Indonesia."

help_message = "haiiikkkk ada yang bisa ak bantuu?? kalau butuh ikuti ini ya!, contoh: @Bot kegunaan AI apa?\nJika ingin melihat status ping bot silahkan ketik /ping\nJika ingin menghubungi admin bot silahkan ketik /ownerbot:)"

FFMPEG_PATH = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
if not os.path.exists(FFMPEG_PATH):
    FFMPEG_PATH = "ffmpeg"

# Lavalink nodes config (fallback jika node utama mati)
LAVALINK_NODES = [
    {"uri": "http://lavalinkv4.serenetia.com:80", "password": "https://dsc.gg/ajidevserver", "identifier": "serenetia"},
    {"uri": "http://lavalinkv4.alndriw.online:443", "password": "alndriw", "identifier": "alndriw"},
    {"uri": "http://lava-v4.techbyte.host:443", "password": "techbyte", "identifier": "techbyte"},
]

# Music queue per guild
queues = {}
leave_timers = {}
track_nums = {}
loop_modes = {}
last_tracks = {}
last_queries = {}
music_channels = {}
voice_clients = {}  # untuk fallback non-lavalink

def next_track_num(guild_id):
    n = track_nums.get(guild_id, 0) + 1
    track_nums[guild_id] = n
    return n

async def start_leave_timer(guild_id, channel):
    if guild_id in leave_timers:
        leave_timers[guild_id].cancel()
    async def _timer():
        await asyncio.sleep(300)
        vc = next((g.voice_client for g in client.guilds if g.id == guild_id), None)
        if vc and not vc.playing:
            await channel.send("yahh ga ada music diplay selama 5 menit, aku izin keluar dulu")
            await vc.disconnect()
        leave_timers.pop(guild_id, None)
    leave_timers[guild_id] = asyncio.create_task(_timer())

def cancel_leave_timer(guild_id):
    if guild_id in leave_timers:
        leave_timers[guild_id].cancel()
        leave_timers.pop(guild_id, None)

async def connect_lavalink():
    for cfg in LAVALINK_NODES:
        try:
            node = wavelink.Node(
                uri=cfg["uri"],
                password=cfg["password"],
                identifier=cfg["identifier"],
                inactive_player_timeout=None
            )
            await wavelink.Pool.connect(nodes=[node], client=client)
            print(f"Lavalink connected: {cfg['identifier']} ({cfg['uri']})")
            return True
        except Exception as e:
            print(f"Lavalink {cfg['identifier']} gagal: {e}")
    return False

def is_lavalink_connected():
    nodes = wavelink.Pool.nodes
    return bool(nodes and any(n.status.name == 'CONNECTED' for n in nodes.values()))

async def ensure_lavalink():
    if not is_lavalink_connected():
        print("Lavalink disconnect, coba reconnect...")
        return await connect_lavalink()
    return True

async def ytdl_search(query):
    import yt_dlp
    ydl_opts = {
        "quiet": True, "no_warnings": True,
        "format": "bestaudio/best",
        "extract_flat": False,
    }
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch:{query}", download=False))
    if info and info.get("entries"):
        e = info["entries"][0]
        return {
            "title": e.get("title", query),
            "url": e.get("url") or e.get("webpage_url", ""),
            "duration": e.get("duration", 0),
            "uploader": e.get("uploader", "Unknown"),
            "id": e.get("id", ""),
        }
    return None

async def play_lagu(message, query):
    try:
        result = None
        using_lavalink = is_lavalink_connected()

        if using_lavalink:
            try:
                result = await asyncio.wait_for(
                    wavelink.Playable.search(query, source=wavelink.TrackSource.YouTube),
                    timeout=10
                )
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"Search error 1: {e}")
            if not result:
                try:
                    result = await asyncio.wait_for(
                        wavelink.Pool.fetch_tracks(f"ytsearch:{query}"),
                        timeout=10
                    )
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    print(f"Search error 2: {e}")

        if not result:
            yt_info = await ytdl_search(query)
            if not yt_info:
                await message.reply("lagu nya gaa ktemuuu maaf.")
                return
            try:
                if using_lavalink:
                    result = [wavelink.Playable(
                        id=yt_info["id"], title=yt_info["title"],
                        author=yt_info["uploader"],
                        uri=yt_info["url"],
                        length=yt_info["duration"] * 1000,
                        source="youtube"
                    )]
                else:
                    result = yt_info
            except:
                result = yt_info

        track = result[0] if not isinstance(result, (dict, wavelink.Playlist)) else (result.tracks[0] if isinstance(result, wavelink.Playlist) else result)

        gid = message.guild.id
        vc = message.guild.voice_client

        if not vc:
            if using_lavalink:
                try:
                    vc = await message.author.voice.channel.connect(cls=wavelink.Player)
                except Exception as e:
                    await message.reply(f"Gagal connect pake Lavalink: {str(e)[:100]}. Coba pake fallback...")
                    using_lavalink = False
            if not using_lavalink:
                try:
                    vc = await message.author.voice.channel.connect()
                    voice_clients[gid] = vc
                except Exception as e:
                    await message.reply(f"Gagal connect ke voice: {str(e)[:100]}")
                    return
        else:
            if vc.channel != message.author.voice.channel:
                await vc.move_to(message.author.voice.channel)

        queue = get_queue(gid)

        if isinstance(track, dict):
            if vc.playing:
                queue.append(track)
                music_channels[gid] = message.channel
                await message.reply(f"kutambahin ke antrian yakk:3: **{track['title']}**")
            else:
                await play_ytdl(vc, track, gid, message.channel)
                last_queries[gid] = query
                await message.reply(f"Memutar: **{track['title']}** (fallback)")
            return

        if vc.playing:
            queue.append(track)
            music_channels[gid] = message.channel
            await message.reply(f"kutambahin ke antrian yakk:3: **{track.title}**")
        else:
            await vc.play(track)
            last_tracks[gid] = track
            last_queries[gid] = query
            music_channels[gid] = message.channel
            cancel_leave_timer(gid)
            track_nums[gid] = 1
            await message.reply(f"Memutar: **{track.title}**")

    except Exception as e:
        await message.reply(f"Error: {type(e).__name__}: {str(e)[:200]}")

async def play_ytdl(vc, info, guild_id, channel):
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True, "no_warnings": True,
            "format": "bestaudio/best",
        }
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            data = await loop.run_in_executor(None, lambda: ydl.extract_info(info["url"], download=False))
        audio_url = data.get("url") or data.get("webpage_url", "")
        if not audio_url:
            await channel.send("Gagal dapetin audio URL")
            return

        after_func = lambda e: asyncio.run_coroutine_threadsafe(on_ytdl_end(guild_id, channel), client.loop)
        vc.play(discord.FFmpegPCMAudio(
            audio_url, executable=FFMPEG_PATH,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn"
        ), after=after_func)
        last_tracks[guild_id] = info
        cancel_leave_timer(guild_id)
        track_nums[guild_id] = 1
    except Exception as e:
        await channel.send(f"Gagal play yt-dlp: {str(e)[:150]}")

async def on_ytdl_end(guild_id, channel):
    q = get_queue(guild_id)
    vc = next((g.voice_client for g in client.guilds if g.id == guild_id), None)
    if not vc:
        return
    if loop_modes.get(guild_id) and last_tracks.get(guild_id):
        qry = last_queries.get(guild_id, "")
        if not qry:
            t = last_tracks[guild_id]
            qry = t.title if hasattr(t, 'title') else t.get("title", "")
        yt = await ytdl_search(qry)
        if yt:
            last_tracks[guild_id] = yt
            if isinstance(vc, wavelink.Player):
                try:
                    nt = wavelink.Playable(
                        id=yt["id"], title=yt["title"],
                        author=yt["uploader"], uri=yt["url"],
                        length=yt["duration"] * 1000, source="youtube"
                    )
                    await vc.play(nt)
                except:
                    await play_ytdl(vc, yt, guild_id, channel)
            else:
                await play_ytdl(vc, yt, guild_id, channel)
        return
    if q:
        n = q.pop(0)
        last_tracks[guild_id] = n
        num = track_nums.get(guild_id, 0) + 1
        track_nums[guild_id] = num
        cancel_leave_timer(guild_id)
        await play_ytdl(vc, n, guild_id, channel)
        labels = {2: "dua", 3: "tiga", 4: "empat", 5: "lima"}
        if num in labels:
            await channel.send(f"kita lanjut ke lagu ke {labels[num]} yaa:>")
    else:
        await start_leave_timer(guild_id, channel)

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

@client.event
async def on_ready():
    try:
        print(f"Bot {client.user} uda online!")
        await client.change_presence(status=discord.Status.do_not_disturb, activity=discord.Game(name="Mini World: CREATA"))

        # Konek ke Lavalink dengan fallback nodes
        try:
            lav = await connect_lavalink()
            if not lav:
                print("Semua Lavalink node gagal, pake yt-dlp fallback.")
        except Exception as e:
            print(f"Lavalink error: {e}")

        # Daftarin commands pake tree.command decorator
        guilds = [discord.Object(id=g.id) for g in client.guilds]

        @tree.command(name="stop", description="stop music", guilds=guilds)
        async def cmd_stop(interaction: discord.Interaction):
            await stop_cmd(interaction)

        @tree.command(name="queue", description="Lihat antrian lagu", guilds=guilds)
        async def cmd_queue(interaction: discord.Interaction):
            await queue_cmd(interaction)

        @tree.command(name="ping", description="Cek status bot", guilds=guilds)
        async def cmd_ping(interaction: discord.Interaction):
            await ping_cmd(interaction)

        @tree.command(name="ownerbot", description="Info pembuat bot", guilds=guilds)
        async def cmd_ownerbot(interaction: discord.Interaction):
            await ownerbot_cmd(interaction)

        @tree.command(name="status", description="Cek status koneksi bot", guilds=guilds)
        async def cmd_status(interaction: discord.Interaction):
            await status_cmd(interaction)

        @tree.command(name="bannplayer", description="Cara banned player Mini World", guilds=guilds)
        async def cmd_bannplayer(interaction: discord.Interaction):
            await bannplayer_cmd(interaction)

        @tree.command(name="say", description="Kirim pesan lewat bot", guilds=guilds)
        async def cmd_say(interaction: discord.Interaction, channel: discord.TextChannel, pesan: str):
            await say_cmd(interaction, channel, pesan)

        @tree.command(name="sayhello", description="Bot bilang Hello", guilds=guilds)
        async def cmd_sayhello(interaction: discord.Interaction):
            await sayhello_cmd(interaction)

        @tree.command(name="reconnect", description="Coba konek ulang Lavalink", guilds=guilds)
        async def cmd_reconnect(interaction: discord.Interaction):
            await reconnect_cmd(interaction)

        @tree.command(name="panel", description="Private panel (owner only)", guilds=guilds)
        async def cmd_panel(interaction: discord.Interaction):
            await panel_cmd(interaction)

        for g in guilds:
            try:
                await tree.sync(guild=g)
            except Exception as e:
                print(f"Gagal sync guild {g.id}: {e}")

        print("Commands registered!")

    except Exception as e:
        print(f"ERROR di on_ready: {e}")
        import traceback
        traceback.print_exc()

    for guild in client.guilds:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                await ch.send("bot siap dipkai!")
                break
        break

@client.event
async def on_wavelink_node_disconnected(payload):
    print(f"Lavalink node disconnected: {payload.node.identifier}")
    asyncio.create_task(connect_lavalink())

@client.event
async def on_wavelink_track_end(payload):
    vc = payload.player
    if vc is None:
        return
    gid = vc.guild.id
    q = get_queue(gid)
    if loop_modes.get(gid) and last_tracks.get(gid):
        ch = music_channels.get(gid)
        qry = last_queries.get(gid, "")
        if not qry:
            t = last_tracks[gid]
            qry = t.title if hasattr(t, 'title') else t.get("title", "")
        try:
            tracks = await wavelink.Playable.search(qry, source=wavelink.TrackSource.YouTube)
            if tracks:
                nt = tracks[0] if not isinstance(tracks, wavelink.Playlist) else tracks.tracks[0]
                last_tracks[gid] = nt
                await vc.play(nt)
                return
        except:
            pass
        yt = await ytdl_search(qry)
        if yt:
            try:
                nt = wavelink.Playable(
                    id=yt["id"], title=yt["title"],
                    author=yt["uploader"], uri=yt["url"],
                    length=yt["duration"] * 1000, source="youtube"
                )
                last_tracks[gid] = nt
                await vc.play(nt)
                if ch:
                    await ch.send(f"Loop: **{yt['title']}** (fallback)")
                return
            except:
                pass
        if ch:
            await ch.send("Gagal loop lagu, lanjut antrian kalo ada...")
    if q:
        n = q.pop(0)
        last_tracks[vc.guild.id] = n
        num = next_track_num(vc.guild.id)
        cancel_leave_timer(vc.guild.id)
        await vc.play(n)
        labels = {2: "dua", 3: "tiga", 4: "empat", 5: "lima"}
        if num in labels:
            ch = music_channels.get(vc.guild.id)
            if ch:
                await ch.send(f"kita lanjut ke lagu ke {labels[num]} yaa:>")
    else:
        ch = music_channels.get(vc.guild.id)
        if ch:
            await start_leave_timer(vc.guild.id, ch)


async def stop_cmd(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        queues[interaction.guild_id] = []
        cancel_leave_timer(interaction.guild_id)
        voice_clients.pop(interaction.guild_id, None)
        await vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("music nya distop yaaahh.")
    else:
        await interaction.response.send_message("maaf bgt nihh bot km ga ada di voice channel")

async def queue_cmd(interaction: discord.Interaction):
    queue = get_queue(interaction.guild_id)
    if queue:
        lines = []
        for i, t in enumerate(queue):
            title = t.title if hasattr(t, 'title') else t.get('title', 'Unknown')
            lines.append(f"{i+1}. {title}")
        await interaction.response.send_message("**Antrian:**\n" + "\n".join(lines))
    else:
        await interaction.response.send_message("antria ny kosong ko tenang ajaaa:3.")

async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {round(client.latency * 1000)}ms")

async def ownerbot_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Pembuat AI BOT: zecvxc_ (I'mDaxxx)\nDisposori oleh: Khairan, Luki.")

async def sayhello_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Hello")

async def status_cmd(interaction: discord.Interaction):
    lines = []
    if is_lavalink_connected():
        for nid, n in wavelink.Pool.nodes.items():
            lines.append(f"Lavalink **{nid}**: {n.status.name} ({n.uri})")
    else:
        lines.append("Lavalink: **Tidak konek** (pake yt-dlp fallback)")
    lines.append(f"Bot ping: {round(client.latency * 1000)}ms")
    await interaction.response.send_message("**Status Bot:**\n" + "\n".join(lines))

async def reconnect_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("Mencoba konek ulang ke Lavalink...")
    ok = await connect_lavalink()
    if ok:
        await interaction.edit_original_response(content="Lavalink berhasil konek!")
    else:
        await interaction.edit_original_response(content="Semua node gagal. Bot akan pake yt-dlp fallback buat musik.")

async def say_cmd(interaction: discord.Interaction, channel: discord.TextChannel, pesan: str):
    await channel.send(pesan)
    await interaction.response.send_message(f"Pesan terkirim ke {channel.mention}", ephemeral=True)

async def bannplayer_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        "**CARA TERBARU MEMBANNED PLAYER Mini World: CREATA 2026**\n"
        "- Melakukan spam item maupun give item secara ilegal ke target dan siapkan teman yang bisa diajak kerjasama untuk merecord player tersebut agar bisa dilaporkan kepada Admin Mini World: CREATA secara illegal.\n"
        "Resiko: Akun kamu bisa saja terkena banned permanent jika ketahuan melakukan Banned secara fitnah dan tidak sah.\n"
        "- Menggunakan Cheat Copy Skin Target didalam map\n"
        "Fungsi cheat tersebut: Cheat tersebut melakukan Copy paste nama dan juga menjadikan diri kita sebagai target tersebut. Dan juga agar diri kita sendiri agar terlihat seolah olah bahwa diri kita ialah orang itu (target) \n"
        "Resiko penggunaan fitur ini: Bisa terkena banned juga jika ketahuan dari Sistem Log-in akun. Karna setiap orang menggunakan Cheat Engine akan tersimpan di server sana."
    )

class SendModal(discord.ui.Modal, title="Kirim Pesan"):
    channel = discord.ui.TextInput(label="ID Channel", placeholder="Masukkan ID channel tujuan")
    pesan = discord.ui.TextInput(label="Pesan", style=discord.TextStyle.paragraph, placeholder="Tulis pesan...")

    async def on_submit(self, interaction: discord.Interaction):
        ch = interaction.guild.get_channel(int(self.channel.value))
        if ch:
            await ch.send(self.pesan.value)
            await interaction.response.send_message(f"Pesan terkirim ke {ch.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("Channel gak ditemukan!", ephemeral=True)

class PrivatePanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Kirim Pesan", style=discord.ButtonStyle.primary, emoji="\u2709\ufe0f")
    async def btn_kirim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SendModal())

async def panel_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("Panel ini cuma buat owner bot.", ephemeral=True)
        return
    embed = discord.Embed(
        title="Private Panel",
        description="Pilih alat yang mau dipake.",
        color=discord.Color.dark_embed()
    )
    await interaction.response.send_message(embed=embed, view=PrivatePanel())

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild is None:
        if client.user in message.mentions:
            try:
                async with message.channel.typing():
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()}
                    ]
                    resp = await groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=messages,
                        max_tokens=1024,
                        temperature=0.7
                    )
                    jawaban = resp.choices[0].message.content
                    if len(jawaban) > 1900:
                        for i in range(0, len(jawaban), 1900):
                            await message.channel.send(jawaban[i:i+1900])
                    else:
                        await message.channel.send(jawaban)
            except Exception as e:
                await message.channel.send(f"Error: {str(e)}")
        return

    content = message.content.lower()
    if content in ("s!s", "s!skip"):
        vc = message.guild.voice_client
        if vc and vc.playing:
            await vc.stop()
            await message.reply("yahh maaaf lagunya diskip:<.")
        else:
            await message.reply("yahh ga ada lagu yang diputarrr.")
        return

    if content in ("s!cancel", "s!c"):
        gid = message.guild.id
        loop_modes[gid] = not loop_modes.get(gid, False)
        status = "di loop" if loop_modes[gid] else "ga di loop"
        await message.reply(f"Lagu {status} yakk!")
        return

    prefix = None
    if message.content.lower().startswith("khairan!p"):
        prefix = "khairan!p"
    elif message.content.lower().startswith("s!p"):
        prefix = "s!p"
    if prefix:
        query = message.content[len(prefix):].strip()
        if not query:
            await message.reply(f"Contoh: {prefix} lofi")
            return

        if not message.author.voice:
            await message.reply("maaf km bkn divoice gabisa putar laguu..")
            return

        await play_lagu(message, query)
        return

    if client.user in message.mentions:
        teks = message.content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()

        if not teks:
            await message.reply(help_message)
            return

        if teks.lower().startswith("gambar"):
            prompt = teks[6:].strip()
            if not prompt:
                await message.reply("Contoh: @Bot gambar orang tidur")
                return
            try:
                async with message.channel.typing():
                    async with aiohttp.ClientSession() as session:
                        # Submit to Stable Horde
                        submit = await session.post(
                            "https://stablehorde.net/api/v2/generate/async",
                            json={
                                "prompt": prompt,
                                "models": ["AlbedoBase XL"],
                                "params": {
                                    "width": 512,
                                    "height": 512,
                                    "steps": 20,
                                    "cfg_scale": 7.5,
                                    "sampler_name": "k_euler"
                                }
                            },
                            headers={"apikey": "0000000000", "Content-Type": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=30)
                        )
                        if submit.status != 202:
                            txt = await submit.text()
                            await message.reply(f"Gagal submit: {submit.status}")
                            return
                        data = await submit.json()
                        req_id = data.get("id")
                        if not req_id:
                            await message.reply("Gagal: no ID")
                            return

                        # Poll for result
                        for i in range(120):
                            await asyncio.sleep(5)
                            chk = await session.get(
                                f"https://stablehorde.net/api/v2/generate/status/{req_id}",
                                timeout=aiohttp.ClientTimeout(total=30)
                            )
                            if chk.status != 200:
                                continue
                            st = await chk.json()
                            if st.get("done"):
                                imgs = st.get("generations", [])
                                if imgs:
                                    img_url = imgs[0].get("img")
                                    if img_url:
                                        async with session.get(img_url) as img_resp:
                                            img_bytes = await img_resp.read()
                                            file = discord.File(io.BytesIO(img_bytes), filename="gambar.png")
                                            await message.reply(f"Prompt: {prompt}", file=file)
                                            return
                                await message.reply("Gagal: gambar kosong")
                                return
                            qpos = st.get("queue_position", 0)
                            if qpos > 0 and (i % 6 == 0):
                                await message.reply(f"Antrian: posisi {qpos}...")
                        await message.reply("Waktu habis (10 menit)")
            except Exception as e:
                await message.reply(f"Error: {str(e)}")
            return

        try:
            async with message.channel.typing():
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": teks}
                ]

                resp = await groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.7
                )

                jawaban = resp.choices[0].message.content

                if len(jawaban) > 1900:
                    for i in range(0, len(jawaban), 1900):
                        await message.reply(jawaban[i:i+1900])
                else:
                    await message.reply(jawaban)

        except Exception as e:
            await message.reply(f"Error: {str(e)}")

client.run(DISCORD_TOKEN)
