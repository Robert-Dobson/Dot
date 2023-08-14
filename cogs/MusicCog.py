import asyncio
import datetime
import discord
from discord.ext import commands, tasks
import logging
import os
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
    "quiet": True,
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
    "quiet": True,
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
        # Use YoutubeDL to download the song from YouTube
        with YoutubeDL(options) as ydl:
            logging.info(f"Searching YouTube for {query}")
            try:
                info = ydl.extract_info(query, download=should_download)["entries"]

                if not is_playlist:
                    # Only want one song information
                    info = info[0]

                return info
            except Exception as e:
                logging.error(f"Issue downloading {query}: {e}")
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
        query = "https://www.youtube.com/playlist?list={playlist[1]}"
        metadata = self.query_youtube(query, YDL_OPTIONS_PLAYLIST, False, True)
        if metadata is None:
            logging.error("Issue fetching playlist data for sync")
            return

        # Compare local songs to remote songs
        logging.info("Comparing remote playlists to local playlists for sync")

        remote_songs = [[song_info["title"], song_info["id"]] for song_info in metadata]
        local_songs = [
            [song, re.findall(".*\[(.*)\].mp3", song)[-1]]
            for song in os.listdir(f"./playlists/{playlist[0]}")
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
        except Exception as e:
            logging.error(f"Issue removing song from storage: {e}")
            return False

    async def start_music(self, ctx):
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
            await ctx.send("Could not connect to the voice channel")
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

    @commands.command(
        brief="Plays the requested song (usage: /play <song-name>)",
        description="Searches Youtube for the music that best matches "
        "the query and adds it to the queue to play in "
        "your current channel \n Arguments: <song-name>",
    )
    async def play(self, ctx, *song_query):
        query = " ".join(song_query)

        # Get caller's voice channel
        caller_vc = ctx.author.voice.channel if ctx.author.voice else None
        if caller_vc is None:
            await ctx.send("Connect to a voice channel!")
            return

        # TODO: Consider what if dot is paused in different channel
        if self.is_paused:
            await self.resume(ctx)
            return

        if query != " ":
            await ctx.send("Searching for song, this might take a while!")

            # Find song on YouTube in a thread
            coroutine = asyncio.to_thread(
                self.query_youtube, f"ytsearch:{query}", YDL_OPTIONS, True, False
            )
            info = await coroutine

            song = None
            if info is not None:
                logging.info(f"Downloaded (temporarily) {info['title']}")

                # Return song information and path
                song = {
                    "title": info["title"],
                    "path": f"{os.getcwd()}/{info['title']} [{info['id']}].mp3",
                    "delete": True,
                }

            if song is None:
                await ctx.send("Could not find the song. Please try again")
                return

            await ctx.send(f"Song, {song['title']}, added to the queue")
            self.music_queue.append([song, caller_vc])

        if len(self.music_queue) == 0:
            await ctx.send("No music in queue!")
        else:
            if self.is_playing is False:
                await self.start_music(ctx)

    @commands.command(
        brief="Pauses the currently playing song (usage: /pause)",
        description="Pauses the currently playing song",
    )
    async def pause(self, ctx):
        if self.is_playing:
            self.is_playing = False
            self.is_paused = True
            self.connected_vc.pause()
        else:
            await ctx.send("Music already paused!")

    @commands.command(
        brief="Resumes the currently playing song if paused (usage: /resume)",
        description="Resumes the currently playing song if paused",
    )
    async def resume(self, ctx):
        if self.is_paused:
            self.is_playing = True
            self.is_paused = False
            self.connected_vc.resume()
        else:
            await ctx.send("No music is paused!")

    @commands.command(
        brief="Skips the current song (usage: /skip optional:<num-of-songs-to-skip>)",
        description="Skips the currently playing song or the number of songs"
        "specified.\n Arguments: Optional argument <num-of-songs-to-skip>"
        "- Skip given number of songs (corresponds to queue number)",
    )
    async def skip(self, ctx, *args):
        num_to_skip = 1

        if len(args) == 1:
            if args[0].isnumeric():
                num_to_skip = int(args[0])
            else:
                await ctx.send("Enter an integer number to skip n songs")
                return
        elif len(args) > 1:
            await ctx.send("Too many arguments!")
            return

        if not self.is_playing:
            await ctx.send("No song is currently playing")
            return

        if self.is_paused:
            await ctx.send("Dot is currently paused")
            return

        if num_to_skip > 1:
            if len(self.music_queue) < num_to_skip:
                await ctx.send("There's not enough songs in the queue")
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
            os.system("killall -KILL ffmpeg")
        else:
            await ctx.send("Not playing any music!")

    @commands.command(
        brief="Displays next 20 songs in queue (and current song) (usage: /queue)",
        description="Displays next 20 songs in queue (and current song)",
    )
    async def queue(self, ctx):
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
            await ctx.send(queue)
        else:
            await ctx.send("No music in the queue!")

    @commands.command(
        brief="Removes all songs from the queue (usage: /clear)",
        description="Removes all songs from the queue (current song is unaffected)."
        " Also deletes any temporary songs no longer used",
    )
    async def clear(self, ctx):
        self.music_queue = []
        self.skip(ctx)
        self.current_song = None

        # Delete all left over mp3 songs
        for filename in os.listdir("."):
            if filename.endswith(".mp3"):
                if self.delete_song(filename):
                    logging.info(f"Removed {filename} as part of clearing queue")

        await ctx.send("Music queue is cleared!")

    @commands.command(
        alias=["disconnect", "quit"],
        brief="Disconnects bot from voice channel (usage: /leave)",
        description="Disconnects bot from voice channel. Also clears current queue "
        "and deletes any temporary songs in queue from storage",
    )
    async def leave(self, ctx):
        self.music_queue = []
        self.current_song = None

        # Stop music if playing
        if self.is_playing:
            logging.info("Stop music by killing all ffmpeg processes")
            os.system("killall -KILL ffmpeg")

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

    @commands.command(
        brief="Shuffles current queue (usage: /shuffle)",
        description="Shuffles current queue",
    )
    async def shuffle(self, ctx):
        random.shuffle(self.music_queue)
        await ctx.send("Playlist shuffled!")

    @commands.group(
        brief="Group of commands related to playlists",
    )
    async def playlist(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid playlist command. Use p (for play) or list")

    @playlist.command(
        brief="Adds songs from playlist to queue (usage /playlist p  <playlist-name>)",
        description="Adds all songs in given local playlist to queue \n"
        "Arugments: <playlist-name> - name of the local playlist to play",
    )
    async def p(self, ctx, *args):
        query = " ".join(args)

        # Get users voice channel
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if voice_channel is None:
            await ctx.send("Connect to a voice channel!")
            return

        if query == " ":
            await ctx.send("Must provide a playlist name!")
            return

        if query not in os.listdir("./playlists"):
            await ctx.send(f"{query} is not a playlist!")
            return

        # add songs to list
        for song in os.listdir(f"./playlists/{query}"):
            song = {
                "title": song[:-4],
                "path": f"./playlists/{query}/{song}",
                "delete": False,
            }
            self.music_queue.append([song, voice_channel])

        # Shuffle queue
        random.shuffle(self.music_queue)

        # Start playing songs
        await ctx.send(f"Playlist {query} has been added to the queue!")
        logging.info(f"Added playlist {query} to the queue")
        await self.start_music(ctx)

    @playlist.command(
        brief="Lists all avaliable local playlists (usage /playlist list)",
        description="Lists all avaliable local playlists",
    )
    async def list(self, ctx):
        # List all avaliable local playlists
        list = ""
        for i, playlist in enumerate(os.listdir("./playlists")):
            list += f"{i}: {playlist} \n"

        if list == "":
            await ctx.send("No playlists found!")
        else:
            await ctx.send(list)

    @playlist.command(
        brief="Synchronises given playlist (usage: /playlist sync <playlist-name>)",
        description="Synchronises given playlist with remote YouTube playlist."
        "Downloads songs that aren't avaliable locally and deletes songs"
        " not avaliable remotely \n"
        "Arugments: <playlist-name> - name of the local playlist to play",
    )
    async def sync(self, ctx):
        if not self.is_syncing:
            logging.info("Commenced on demand sync of playlists")
            await ctx.send("Syncing playlists (this may take a while)")

            coroutine = asyncio.to_thread(self.playlist_sync)
            await coroutine

            await ctx.send("Playlist sync complete")
        else:
            await ctx.send("Already syncing!")
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
        if self.connected_vc is None or before is None:
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
                    await self.leave(self.connected_vc)
                    return

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("Cog loaded")
        await self.check_playlists.start()


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
