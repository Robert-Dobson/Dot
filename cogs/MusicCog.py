import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
import psutil
import random
from yt_dlp import YoutubeDL

YDL_OPTIONS = {
    "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
    "noplaylist": "True",
    "prefer_free_formats": False,
    "extract_flat": False,
    "logger": logging,
    "cookiefile": "cookies.txt",
    "remote_components": ["ejs:github"],
}


class MusicCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        self.music_queue = []
        self.is_playing = False
        self.is_paused = False

        self.current_song = None
        self.connected_vc = None

    def cog_unload(self):
        """Clean up resources when cog is unloaded"""
        logging.info("Unloading MusicCog - cleaning up resources")

        # Stop any playing music
        if self.connected_vc and self.is_playing:
            self.kill_process()

        # Clear the queue
        self.music_queue.clear()

        # Reset state
        self.is_playing = False
        self.is_paused = False
        self.current_song = None

    def download_song(self, query):
        """Extract song stream URL instead of downloading"""
        with YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                # Check if input is a URL or search query
                if query.startswith(("http://", "https://", "www.")):
                    logging.info(f"Extracting info from URL: {query}")
                    result = ydl.extract_info(query, download=False)
                else:
                    logging.info(f"Searching YouTube for: {query}")
                    result = ydl.extract_info(f"ytsearch:{query}", download=False)

                info = ydl.sanitize_info(result)

                if "entries" in info and info["entries"]:
                    info = info["entries"][0]

                return {
                    "title": info["title"],
                    "url": info["url"],
                    "id": info["id"],
                }
            except Exception as e:
                logging.exception(f"Issue extracting stream URL for {query}: {e}")
                return None

    def kill_process(self, proc_name="ffmpeg"):
        for proc in psutil.process_iter():
            if proc.name() == proc_name:
                proc.kill()

    async def start_music(self, interaction):
        if len(self.music_queue) == 0:
            self.is_playing = False
            return

        target_vc = self.music_queue[0]["voice_channel"]

        # Check if voice dependencies are available
        try:
            import nacl
        except ImportError:
            await interaction.channel.send(
                "❌ Voice dependencies missing. Please install: `pip install discord.py[voice] PyNaCl`"
            )
            logging.error("PyNaCl not installed - voice connections will fail")
            return

        # If not connected to any voice channel
        if self.connected_vc is None or not self.connected_vc.is_connected():
            try:
                await interaction.channel.send("🔄 Connecting to voice channel...")
                self.connected_vc = await target_vc.connect(timeout=60.0)
                # Give Discord more time to establish the connection properly
                await asyncio.sleep(2)
                logging.info(f"Successfully connected to voice channel: {target_vc.name}")
            except discord.errors.ConnectionClosed as e:
                logging.error(f"Voice connection closed during handshake: {e}")
                await interaction.channel.send(
                    "❌ Voice connection failed. This might be due to:\n• Missing voice dependencies\n• Server network restrictions\n• Discord voice server issues"
                )
                return
            except asyncio.TimeoutError:
                logging.error("Voice connection timed out")
                await interaction.channel.send("❌ Voice connection timed out. Please try again.")
                return
            except Exception as e:
                logging.error(f"Failed to connect to voice channel: {e}")
                await interaction.channel.send(f"❌ Could not connect to voice channel: {str(e)}")
                return

        # If in wrong voice channel
        if self.connected_vc.channel != target_vc:
            try:
                await self.connected_vc.move_to(target_vc)
                await asyncio.sleep(1)  # Give time for move to complete
            except Exception as e:
                logging.error(f"Failed to move to voice channel: {e}")
                await interaction.channel.send("Could not move to the voice channel.")
                return

        # If bot failed to connect to caller's voice channel
        if self.connected_vc is None:
            await interaction.channel.send("Could not connect to the voice channel")
            logging.error("Dot couldn't connect to a voice channel")
            return

        # Play Music
        self.play_next()

    def play_next(self):
        if len(self.music_queue) == 0:
            self.is_playing = False
            return

        # Get next song from queue
        self.is_playing = True
        queue_item = self.music_queue.pop(0)

        # Play next song
        try:
            self.current_song = queue_item["title"]
            logging.info(f"Playing {self.current_song} in {queue_item['voice_channel'].name}")
            ffmpeg_options = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin",
                "options": "-vn -b:a 128k -bufsize 512k -af dynaudnorm=f=200:g=15",
            }
            self.connected_vc.play(
                discord.FFmpegPCMAudio(queue_item["url"], executable="ffmpeg", **ffmpeg_options),
                after=lambda _: self.end_song(),
            )
        except Exception as e:
            logging.exception(f"Failed to play {self.current_song}: {e}")
            self.play_next()

    def end_song(self):
        self.current_song = None
        self.play_next()

    async def leave_channel(self):
        self.music_queue = []
        self.current_song = None

        # Stop music if playing
        if self.is_playing:
            logging.info("Stop music by killing all ffmpeg processes")
            self.kill_process()

        self.is_playing = False
        self.is_paused = False

        # Properly disconnect from voice channel
        if self.connected_vc and self.connected_vc.is_connected():
            try:
                await self.connected_vc.disconnect()
                logging.info("Disconnected from voice channel")
            except Exception as e:
                logging.error(f"Error disconnecting from voice: {e}")
            finally:
                self.connected_vc = None

    @app_commands.command(description="Plays requested song from YouTube")
    async def play(self, interaction, song_query: str):
        # Get caller's voice channel
        caller_vc = interaction.user.voice.channel if interaction.user.voice else None
        if caller_vc is None:
            await interaction.response.send_message("Connect to a voice channel!")
            return

        # TODO: Consider what if dot is paused in different channel
        if self.is_paused:
            await self.resume(interaction)
            return

        await interaction.response.send_message("Searching for song, this might take a while!")

        # Find song on YouTube in a thread
        coroutine = asyncio.to_thread(self.download_song, song_query)
        song = await coroutine

        if song is None:
            await interaction.followup.send("Could not find the song. Please try again")
            return

        await interaction.followup.send(f"Song, {song['title']}, added to the queue")
        self.music_queue.append({"title": song["title"], "url": song["url"], "voice_channel": caller_vc})

        if not self.is_playing:
            await self.start_music(interaction)

    @app_commands.command(description="Pauses the currently playing song")
    async def pause(self, interaction):
        if self.is_playing and self.connected_vc:
            self.is_playing = False
            self.is_paused = True
            self.connected_vc.pause()
            await interaction.response.send_message("Music paused")
        else:
            await interaction.response.send_message("No music is currently playing!")

    @app_commands.command(description="Resumes the currently playing song if paused")
    async def resume(self, interaction):
        if self.is_paused and self.connected_vc:
            self.is_playing = True
            self.is_paused = False
            self.connected_vc.resume()
            await interaction.response.send_message("Music resumed")
        else:
            await interaction.response.send_message("No music is paused!")

    @app_commands.command(description="Skips specified number of songs songs")
    async def skip(self, interaction, num_to_skip: int = 1):
        response = interaction.response

        if not self.is_playing:
            await response.send_message("No song is currently playing")
            return

        if self.is_paused:
            await response.send_message("Dot is currently paused")
            return

        if num_to_skip < 1:
            await response.send_message("Must skip 1 or more songs")
            return

        if len(self.music_queue) < num_to_skip:
            await response.send_message("There's not enough songs in the queue")
            return

        # If skipping more than 1 song, remove n-1 songs from queue first
        if num_to_skip > 1:
            if len(self.music_queue) < num_to_skip:
                await response.send_message("There's not enough songs in the queue")
                return

            del self.music_queue[: num_to_skip - 1]

        # Skip currently playing song
        if self.connected_vc is not None and self.is_playing is True:
            logging.info("Skipping song by killing ffmpeg process")
            self.kill_process()
        else:
            await response.send_message("Not playing any music!")
            return

        await response.send_message(f"Skipped {num_to_skip} songs")

    @app_commands.command(description="Displays next 20 songs in queue (and current song)")
    async def queue(self, interaction):
        queue_text = ""

        # Show currently playing song
        if self.current_song:
            status = "⏸️ Paused" if self.is_paused else "🎵 Now Playing"
            queue_text += f"{status}: **{self.current_song}**\n\n"

        # Show upcoming songs
        if self.music_queue:
            queue_text += f"📝 **Queue ({len(self.music_queue)} song(s)):**\n"
            for i, song in enumerate(self.music_queue[:20], 1):
                queue_text += f"`{i:2d}.` {song['title']}\n"

            if len(self.music_queue) > 20:
                queue_text += f"... and {len(self.music_queue) - 20} more songs"
        else:
            if not self.current_song:
                queue_text = "📝 **Queue is empty!**\nUse `/play <song>` to add some music."
            else:
                queue_text += "📝 **No songs in queue**\nCurrent song will finish, then playback will stop."

        await interaction.response.send_message(queue_text)

    @app_commands.command(description="Removes all songs from the queue (current song is unaffected)")
    async def clear(self, interaction):
        self.music_queue = []
        self.kill_process()  # Skip any songs if playing
        self.current_song = None

        await interaction.response.send_message("Music queue is cleared!")

    @app_commands.command(description="Disconnects bot from voice channel")
    async def leave(self, interaction):
        await self.leave_channel()
        await interaction.response.send_message("Bot is now disconnected")

    @app_commands.command(description="Shuffles current queue")
    async def shuffle(self, interaction):
        random.shuffle(self.music_queue)
        await interaction.response.send_message("Playlist shuffled!")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Automatic leaving of voice chat if alone

        # If bot is the one moving channel do nothing
        if member.id == self.bot.user.id:
            return

        # If bot isn't connected or nobody left a channel
        if self.connected_vc is None or before.channel is None:
            return

        bot_channel = self.connected_vc.channel.guild.id
        left_channel = before.channel.guild.id

        # If bot isn't connected to the channel that had activity
        if bot_channel != left_channel:
            return

        # Leave if alone for more than 5s before finally leaving
        if len(self.connected_vc.channel.members) <= 1:
            time = 0
            while True:
                await asyncio.sleep(1)
                time += 1

                if len(self.connected_vc.channel.members) >= 2:
                    break

                if time >= 5 and self.connected_vc.is_connected():
                    logging.info("Left voice channel automatically")
                    await self.leave_channel()
                    return


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
