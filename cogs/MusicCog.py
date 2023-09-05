import asyncio
import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
import os
import psutil
import random
import re
from yt_dlp import YoutubeDL

SYNC_PLAYLIST_TIME = datetime.time(hour=2, minute=0, tzinfo=datetime.timezone.utc)

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
}
YDL_OPTIONS_PLAYLIST = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
    "logger": logging,
    "no-abort-on-error": True,
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

        # Start schedule for syncing playlists at night
        self.check_playlists.start()
        self.is_syncing = False

    def cog_unload(self):
        self.check_playlists.cancel()

    def query_youtube(self, query, options, should_download, is_playlist):
        # Speed up playlist extraction when its not being downloaded
        if is_playlist and not should_download:
            options = dict(options)
            options['flat-playlist'] = True


        # Use YoutubeDL to download the song from YouTube
        with YoutubeDL(options) as ydl:
            logging.info(f"Searching YouTube for {query}")

            try:
                info = ydl.extract_info(query, download=should_download)["entries"]

                if not is_playlist:
                    # Only want one song information
                    info = info[0]

                return info
            except:
                logging.exception(f"Issue downloading {query}")
                return None

    def playlist_sync(self):
        logging.info("Started local playlist sync")
        self.is_syncing = True

        # Get YT playlist information from `.env`
        playlists = [elem.split(":") for elem in os.getenv("playlists").split("/")]

        for playlist in playlists:
            if playlist == [""]:
                continue

            if playlist[0] in os.listdir("./playlists"):
                self.sync_existing_playlist(playlist)
            else:
                self.download_new_playlist(playlist)

        logging.info("Playlist sync complete")
        self.is_syncing = False

    def sync_existing_playlist(self, playlist):
        # Get metadata of playlist songs from YT
        query = f"https://www.youtube.com/playlist?list={playlist[1]}"
        metadata = self.query_youtube(query, YDL_OPTIONS_PLAYLIST, False, True)
        if metadata is None:
            logging.error("Issue fetching playlist data for sync")
            return

        # Compare local songs to remote songs
        logging.info("Comparing remote playlists to local playlists for sync")

        remote_songs = [[song_info["title"], song_info["id"]] for song_info in metadata]
        local_songs = [
            [song, re.findall(".*\[(.*)\].mp3", song)[0]]
            for song in os.listdir(f"./playlists/{playlist[0]}")
            if song.endswith(".mp3")
        ]

        # Songs not in local but are in remote
        missing_songs = [
            song
            for song in remote_songs
            if song[1] not in [sublist[1] for sublist in local_songs]
        ]

        # Songs that are in local but not in remote
        remove_songs = [
            song
            for song in local_songs
            if song[1] not in [sublist[1] for sublist in remote_songs]
        ]

        logging.info(f"{playlist[0]} has {len(missing_songs)} missing songs")
        logging.info(f"{playlist[0]} has {len(remove_songs)} songs to remove")

        # Download any missing songs
        if len(missing_songs) > 0:
            self.download_missing_songs_in_playlist(missing_songs, playlist[0])

        # Delete any local songs not present on Youtube
        if len(remove_songs) > 0:
            logging.info(f"Deleting songs not in remote playlist {playlist[0]}")

            for remove_song in remove_songs:
                if self.delete_song(f"./playlists/{playlist[0]}/{remove_song[0]}"):
                    logging.info(f"Removed {remove_song[0]} from {playlist[0]}")

    def download_new_playlist(self, playlist):
        logging.info(f"{playlist[0]} playlist doesn't exist, downloading now")

        os.mkdir(f"./playlists/{playlist[0]}")

        # Download all playlist songs from YouTube
        download_options = dict(YDL_OPTIONS_PLAYLIST)
        song_path_format = f"./playlists/{playlist[0]}/%(title)s [%(id)s].%(ext)s"
        download_options["outtmpl"] = song_path_format

        query = f"https://www.youtube.com/playlist?list={playlist[1]}"
        songs = self.query_youtube(query, download_options, True, True)

        if songs is None:
            logging.error(f"Issue downloading new playlist {playlist[0]} from scratch")

    def download_missing_songs_in_playlist(self, missing_songs, playlist):
        logging.info(f"Downloading missing songs from {playlist} playlist")

        song_path_format = (
            f"{os.getcwd()}/playlists/{playlist}/%(title)s [%(id)s].%(ext)s"
        )
        download_options = dict(YDL_OPTIONS)
        download_options["outtmpl"] = song_path_format

        for song in missing_songs:
            # Download missing song from youtube
            logging.info(f"Downloading song {song[0]} for playlist:{playlist}")
            query = f"https://www.youtube.com/watch?v={song[1]}"
            songs = self.query_youtube(query, download_options, True, True)
            if songs is None:
                logging.error(
                    f"Issue downloading song id: {song[0]} for playlist {playlist}"
                )

    def delete_song(self, song_path):
        try:
            os.remove(song_path)
            return True
        except:
            logging.exception("Issue removing song from storage")
            return False

    def kill_process(self, proc_name="ffmpeg"):
        for proc in psutil.process_iter():
            if proc.name() == proc_name:
                proc.kill()

    async def start_music(self, interaction):
        if len(self.music_queue) == 0:
            self.is_playing = False
            return

        target_vc = self.music_queue[0][1]

        # If not connected to any voice channel
        if self.connected_vc is None or not self.connected_vc.is_connected():
            self.connected_vc = await target_vc.connect()

        # If in wrong voice channel
        if self.connected_vc != target_vc:
            await self.connected_vc.move_to(target_vc)

        # If bot failed to connect to caller's voice channel
        if self.connected_vc is None:
            await interaction.channel.send(
                "Could not connect to the voice channel"
            )
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
        music = self.music_queue.pop(0)
        path = music[0]["path"]
        remove = music[0]["delete"]

        if not os.path.isfile(path):
            logging.error(f"Tried to play a song that doesn't exist: {path}")
            return

        # Play next song
        logging.info(f"Playing {music[0]['title']}")
        self.current_song = music[0]["title"]
        self.connected_vc.play(
            discord.FFmpegPCMAudio(path, executable="ffmpeg", options="-vn"),
            after=lambda e: self.end_song(path, remove),
        )

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

        if song_query != " ":
            await interaction.response.send_message("Searching for song, this might take a while!")

            # Find song on YouTube in a thread
            coroutine = asyncio.to_thread(
                self.query_youtube, f"ytsearch:{song_query}", YDL_OPTIONS, True, False
            )
            info = await coroutine

            song = None
            if info is not None:
                logging.info(f"Downloaded (temporarily) {info['title']}")

                # Return song information and path
                song = {
                    "title": info["title"],
                    "path": f"{info['title']} [{info['id']}].mp3",
                    "delete": True,
                }

            if song is None:
                await interaction.followup.send("Could not find the song. Please try again")
                return

            await interaction.followup.send(f"Song, {song['title']}, added to the queue")
            self.music_queue.append([song, caller_vc])

        if len(self.music_queue) == 0:
            await interaction.response.send_message("No music in queue!")
        else:
            if self.is_playing is False:
                await self.start_music(interaction)

    @app_commands.command(description="Pauses the currently playing song")
    async def pause(self, interaction):
        if self.is_playing:
            self.is_playing = False
            self.is_paused = True
            self.connected_vc.pause()
        else:
            await interaction.response.send_message("Music already paused!")

    @app_commands.command(description="Resumes the currently playing song if paused")
    async def resume(self, interaction):
        if self.is_paused:
            self.is_playing = True
            self.is_paused = False
            self.connected_vc.resume()
        else:
            await interaction.response.send_message("No music is paused!")

    @app_commands.command(description="Skips specified number of songs songs")
    async def skip(self, interaction, num_to_skip: int):
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
                if self.music_queue[i][0]["delete"]:
                    path = self.music_queue[i][0]["path"]
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
        queue = ""

        # Create queue list
        if self.current_song is not None:
            queue += f"Currently playing: {self.current_song}\n"

        i = 0
        while i <= 20 and i < len(self.music_queue):
            queue += f"{i+1}: {self.music_queue[i][0]['title']}\n"
            i += 1

        if i == 21:
            queue += "..."

        if queue != "":
            await interaction.response.send_message(queue)
        else:
            await interaction.response.send_message("No music in the queue!")

    @app_commands.command(
        description="Removes all songs from the queue (current song is unaffected)"
    )
    async def clear(self, interaction):
        self.music_queue = []
        self.kill_process() # Skip any songs if playing
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

    @app_commands.command(description="Adds all songs in given local playlist to queue")
    async def playlist_play(self, interaction, playlist_name: str):
        response = interaction.response

        # Get users voice channel
        voice = interaction.user.voice
        voice_channel = voice.channel if voice else None
        if voice_channel is None:
            await response.send_message("Connect to a voice channel!")
            return

        if playlist_name == " ":
            await response.send_message("Must provide a playlist name!")
            return

        if playlist_name not in os.listdir("./playlists"):
            await response.send_message(f"{playlist_name} is not a playlist!")
            return

        # add songs to list
        for song in os.listdir(f"./playlists/{playlist_name}"):
            song = {
                "title": song[:-4],
                "path": f"./playlists/{playlist_name}/{song}",
                "delete": False,
            }
            self.music_queue.append([song, voice_channel])

        # Shuffle queue
        random.shuffle(self.music_queue)

        # Start playing songs
        await response.send_message(
            f"Playlist {playlist_name} has been added to the queue!"
        )
        logging.info(f"Added playlist {playlist_name} to the queue")
        await self.start_music(interaction)

    @app_commands.command(description="Lists all avaliable local playlists")
    async def playlist_list(self, interaction):
        # List all avaliable local playlists
        list = ""
        for i, playlist in enumerate(os.listdir("./playlists")):
            list += f"{i}: {playlist} \n"

        if list == "":
            await interaction.response.send_message("No playlists found!")
        else:
            await interaction.response.send_message(list)

    @app_commands.command(
        description="Synchronises given playlist with remote YouTube playlist."
    )
    async def sync_playlists(self, interaction):
        response = interaction.response
        if not self.is_syncing:
            logging.info("Commenced on demand sync of playlists")
            await response.send_message("Syncing playlists (this may take a while)")

            coroutine = asyncio.to_thread(self.playlist_sync)
            await coroutine

            await interaction.followup.send("Playlist sync complete")
        else:
            await response.send_message("Already syncing!")
            logging.warning("Tried syncing when already syncing")

    @tasks.loop(time=SYNC_PLAYLIST_TIME)
    async def check_playlists(self):
        logging.info("Commenced scheduled sync of playlists")

        if not self.is_syncing:
            coroutine = asyncio.to_thread(self.playlist_sync)
            await coroutine
        else:
            logging.warning("Tried syncing when already syncing")

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

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("Cog loaded")
        await self.check_playlists.start()


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
