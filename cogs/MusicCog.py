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
    "format": "bestaudio/best",
    "noplaylist": "True",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
    "logger": logging,
    "cookiefile": "cookies.txt",
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
        
        # Clear the queue and clean up files
        for song in self.music_queue:
            if song["delete"]:
                self.delete_song(song["path"])
        
        self.music_queue.clear()
        
        # Clean up any remaining temporary files
        self._cleanup_temp_files()
        
        # Reset state
        self.is_playing = False
        self.is_paused = False
        self.current_song = None

    def _cleanup_temp_files(self):
        """Clean up all temporary MP3 files"""
        try:
            for filename in os.listdir("."):
                if filename.endswith(".mp3") and filename.startswith("["):
                    if self.delete_song(filename):
                        logging.info(f"Cleaned up temporary file: {filename}")
        except Exception as e:
            logging.exception(f"Error during temp file cleanup: {e}")

    def download_song(self, query):
        """Simple method to download a single song"""
        song_path_format = f"{os.getcwd()}/[%(id)s].%(ext)s"
        options = dict(YDL_OPTIONS)
        options["outtmpl"] = song_path_format
        
        with YoutubeDL(options) as ydl:
            logging.info(f"Searching YouTube for {query}")
            try:
                result = ydl.extract_info(query, download=True)
                info = ydl.sanitize_info(result)
                
                if "entries" in info and info["entries"]:
                    info = info["entries"][0]
                    
                return {
                    "title": info["title"],
                    "path": f"[{info['id']}].mp3",
                    "id": info["id"],
                    "delete": True,
                }
            except Exception as e:
                logging.exception(f"Issue downloading {query}: {e}")
                return None

    def kill_process(self, proc_name="ffmpeg"):
        for proc in psutil.process_iter():
            if proc.name() == proc_name:
                proc.kill()

    def delete_song(self, path):
        """Delete a song file safely"""
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
        except Exception as e:
            logging.exception(f"Failed to delete {path}: {e}")
        return False

    async def start_music(self, interaction):
        if len(self.music_queue) == 0:
            self.is_playing = False
            return

        target_vc = self.music_queue[0]["voice_channel"]

        # If not connected to any voice channel
        if self.connected_vc is None or not self.connected_vc.is_connected():
            self.connected_vc = await target_vc.connect()

        # If in wrong voice channel
        if self.connected_vc != target_vc:
            await self.connected_vc.move_to(target_vc)

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
        path = queue_item["path"]
        remove = queue_item["delete"]
        
        if not os.path.isfile(path):
            logging.error(f"Tried to play a song that doesn't exist: {path}")
            # Try next song instead of stopping
            self.play_next()
            return

        # Play next song
        try:
            logging.info(f"Playing {queue_item['title']}")
            self.current_song = queue_item["title"]
            self.connected_vc.play(
                discord.FFmpegPCMAudio(path, executable="ffmpeg", options="-vn"),
                after=lambda e: self.end_song(path, remove),
            )
        except Exception as e:
            logging.exception(f"Failed to play {queue_item['title']}: {e}")
            # Clean up file if it exists and try next song
            if remove:
                self.delete_song(path)
            self.play_next()

    def end_song(self, path, remove):
        self.current_song = None

        if remove:
            if self.delete_song(path):
                logging.info(f"Removed temporary song: {path}")

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

        await self.connected_vc.disconnect()

        # Wait for music and bot to fully stop
        await asyncio.sleep(5)

        # Delete all left over mp3 songs
        for filename in os.listdir("."):
            if filename.endswith(".mp3"):
                if self.delete_song(filename):
                    logging.info(f"Removed {filename} as part of bot leaving")

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

        await interaction.response.send_message(
            "Searching for song, this might take a while!"
        )

        # Find song on YouTube in a thread
        coroutine = asyncio.to_thread(self.download_song, song_query)
        song = await coroutine

        if song is None:
            await interaction.followup.send(
                "Could not find the song. Please try again"
            )
            return

        await interaction.followup.send(
            f"Song, {song['title']}, added to the queue"
        )
        self.music_queue.append({
            "title": song["title"],
            "path": song["path"],
            "delete": song["delete"],
            "voice_channel": caller_vc
        })

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

        if num_to_skip > 1:
            if len(self.music_queue) < num_to_skip:
                await response.send_message("There's not enough songs in the queue")
                return

            # Remove n-1 songs from queue
            for i in range(num_to_skip - 1):
                # Remember to delete any temporary songs
                if self.music_queue[i]["delete"]:
                    path = self.music_queue[i]["path"]
                    if self.delete_song(path):
                        logging.info(f"Removed {path} through skipping functionality")

                # Remove song from queue
                self.music_queue.pop(0)

        # Skip currently playing song
        if self.connected_vc is not None and self.is_playing is True:
            logging.info("Skipping song by killing ffmpeg process")
            self.kill_process()
        else:
            await response.send_message("Not playing any music!")
            return

        await response.send_message(f"Skipped {num_to_skip} songs")

    @app_commands.command(
        description="Displays next 20 songs in queue (and current song)"
    )
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

    @app_commands.command(
        description="Removes all songs from the queue (current song is unaffected)"
    )
    async def clear(self, interaction):
        self.music_queue = []
        self.kill_process()  # Skip any songs if playing
        self.current_song = None

        # Delete all left over mp3 songs
        for filename in os.listdir("."):
            if filename.endswith(".mp3"):
                if self.delete_song(filename):
                    logging.info(f"Removed {filename} as part of clearing queue")

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
