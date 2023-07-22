import discord
from discord.ext import commands, tasks
from yt_dlp import YoutubeDL
import os
import random
import datetime
import threading
import re
import asyncio
import logging

sync_playlist_time = datetime.time(hour=2, minute=0, tzinfo=datetime.timezone.utc) # 2am GMT or 3am BST

class MusicCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()

        self.bot = bot
        self.is_playing = False
        self.is_paused = False

        self.music_queue = []
        self.YDL_OPTIONS = {
            'format':'bestaudio/best',
            'noplaylist': 'True', 
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            "quiet": True
        }

        self.YDL_OPTIONS_PLAYLIST = {
            'format':'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            "quiet": True
        }

        self.pid = 0
        self.vc = None
        self.is_syncing = False

        # Start schedule for syncing playlists at night
        self.check_playlists.start()
    
    def cog_unload(self):
        self.check_playlists.cancel()
    
    def search_youtube(self, item):
            # Use youtube downloader to download the youtube song
            with YoutubeDL(self.YDL_OPTIONS) as ydl:
                logging.info(f"Searching YouTube for {item}")
                try:
                     info = ydl.extract_info("ytsearch:%s" % item, download=True)['entries'][0]
                except Exception as e:
                     logging.error(f"Issue downloading {item} through play function: {e}")
                     return False
            logging.info(f"Downloaded (temporarily) {info['title']}")
            return {'title': info['title'], 'path': f"{os.getcwd()}/{info['title']} [{info['id']}].mp3", 'delete': True} 
    
    def end_song(self, path, remove):
        # Remove file to clear up space if not in queue anymore
        # TODO: Bug here?
        if remove:
            for song in self.music_queue:
                if song['path'] == path:
                    try:
                        logging.info(f"Removed {path} through normal play functionality")
                        os.remove(path)
                    except Exception as e:
                        logging.error(f"Issue removing temporary song from storage: {e}")
            
        self.play_next()
        

    def play_next(self):
        if len(self.music_queue) > 0:
            self.is_playing = True
            music = self.music_queue.pop(0)
            path = music[0]['path']
            remove = music[0]['delete']
            
            if not os.path.isfile(path):
                logging.error(f"Tried to play a song that doesn't exist: {music[0]['path']}")
            else:
                logging.info(f"Playing {music[0]['title']}")
                self.vc.play(discord.FFmpegPCMAudio(path, executable="ffmpeg", options="-vn"), after = lambda e : self.end_song(path, remove))
        else:
            self.is_playing = False
    
    def playlist_sync(self):
        logging.info("Started local playlist sync")
        self.is_syncing = True

        # Get playlists and ids
        playlists = [elem.split(":") for elem in os.getenv("playlists").split("/")]

        for playlist in playlists:
            # Skip empty playlists
            if playlist == [""]:
                continue
                
            if playlist[0] in os.listdir('./playlists'):
                # Get songs in youtube playlist
                with YoutubeDL(self.YDL_OPTIONS_PLAYLIST) as ydl:
                    try:
                        logging.info(f"Gathering {playlist} playlist data for sync")
                        remote_songs = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist[1]}", download=False)['entries']
                    except Exception as e:
                        logging.error("Issue fetching playlist data for sync")
                        
                # Compare local songs to remote songs and update local songs to match
                logging.info("Comparing remote playlists to local playlists for sync")
                remote_songs = [[song_info['title'], song_info['id']] for song_info in remote_songs]
                local_songs = [[song, re.findall(".*\[(.*)\].mp3", song)[-1]] for song in os.listdir(f"./playlists/{playlist[0]}")]
                
                missing_songs = [song for song in remote_songs if song[1] not in [sublist[1] for sublist in local_songs]]
                remove_songs = [song for song in local_songs if song[1] not in [sublist[1] for sublist in remote_songs]]
                logging.info(f"{playlist[0]} has {len(missing_songs)} missing songs")
                logging.info(f"{playlist[0]} has {len(remove_songs)} songs to remove")

                # Download any missing songs
                if (len(missing_songs) > 0):
                    logging.info(f"Found missing songs in {playlist[0]} playlist, downloading now")
                    download_options = dict(self.YDL_OPTIONS)
                    download_options['outtmpl'] = f"{os.getcwd()}/playlists/{playlist[0]}/%(title)s [%(id)s].%(ext)s"

                    for song in missing_songs:
                        logging.info(f"Downloading song {song[0]} for playlist:{playlist[0]}")
                        with YoutubeDL(download_options) as ydl:
                            try:
                                songs = ydl.extract_info(f"https://www.youtube.com/watch?v={song[1]}", download=True)
                            except Exception as e:
                                logging.error(f"Issue downloading song id: {song[0]} for playlist {playlist[0]}: {e}")

                # Delete any remove_songs
                if (len(remove_songs) > 0):
                    logging.info(f"Found songs not in remote playlist in {playlist[0]}, removing now")
                    for remove_song in remove_songs:
                        try:
                            logging.info(f"Removing {remove_song[0]} from {playlist[0]}")
                            os.remove(f"./playlists/{playlist[0]}/{remove_song[0]}")
                        except Exception as e:
                            logging.error(f"Issue removing {remove_song[0]} from local playlist {playlist[0]}: {e}")
            else:
                # Create folder and download all songs
                os.mkdir(f"./playlists/{playlist[0]}")
                download_options = dict(self.YDL_OPTIONS_PLAYLIST)
                download_options['outtmpl'] = f"./playlists/{playlist[0]}/%(title)s [%(id)s].%(ext)s"
                logging.info(f"{playlist[0]} playlist doesn't exist, downloading now")

                with YoutubeDL(download_options) as ydl:
                    try:
                        songs = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist[1]}", download=True)
                    except Exception as e:
                        logging.error(f"Issue downloading new playlist from scratch: {e}")   
            
            logging.info("Playlist sync complete")
            self.is_syncing = False

    async def start_music(self, ctx):
        if len(self.music_queue) > 0:
            self.is_playing = True
            target_vc = self.music_queue[0][1]
            music = self.music_queue.pop(0)
            path = music[0]['path']
            remove = music[0]['delete']

            # If not connected to any voice channel
            if self.vc == None or not self.vc.is_connected():
                self.vc = await target_vc.connect()
                
                # If we failed to connect to our channel
                if self.vc == None:
                    await ctx.send("Could not connect to the voice channel")
                    log.error("Dot couldn't connect to a voice channel")
                    return
            else:
                # Move to our channel
                if self.vc != target_vc:
                    await self.vc.move_to(target_vc)
            
            # Play Music
            logging.info(f"Playing {music[0]['title']}")
            self.vc.play(discord.FFmpegPCMAudio(path, executable="ffmpeg", options="-vn"), after = lambda e : self.end_song(path, remove))
        else:
            self.is_playing = False

    @commands.command()
    async def play(self, ctx, *args):
        # Get users search query
        query = " ".join(args)

        # Get users voice channel
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if voice_channel is None:
            await ctx.send("Connect to a voice channel!")
        elif self.is_paused:
            self.vc.resume()
        else:
            if query != " ":
                await ctx.send("Searching for song, this might take a while!")
                # Find song and play it
                song = self.search_youtube(query)
                if song == False:
                    await ctx.send("Could not find the song. Please try again")
                else:
                    await ctx.send(f"Song, {song['title']}, added to the queue")
                    self.music_queue.append([song, voice_channel])

                    if self.is_playing == False:
                        await self.start_music(ctx)
            else:
                if len(self.music_queue) == 0:
                    await ctx.send("No music in queue!")
                else:
                    if self.is_playing == False:
                        await self.start_music(ctx)


    @commands.command()
    async def pause(self, ctx):
        if self.is_playing:
            self.is_playing = False
            self.is_paused = True
            self.vc.pause()
        else:
            await ctx.send("Music already paused!")

    @commands.command()
    async def resume(self, ctx):
        if self.is_paused:
            self.is_playing = True
            self.is_paused = False
            self.vc.resume()
        else:
            await ctx.send("No music is paused!")

    @commands.command()
    async def skip(self, ctx):
        #TODO: Potential Bug
        if self.vc != None and self.is_playing == True:
            logging.info("Skipping song by killing ffmpeg process")
            os.system("killall -KILL ffmpeg")
        else:
            await ctx.send("Not playing any music!")

    @commands.command()
    async def queue(self, ctx):
        queue = ""
        
        i = 0
        while i <= 20 and i < len(self.music_queue):
            queue += f"{i}: {self.music_queue[i][0]['title']} \n"
            i += 1
        
        if i == 21:
            queue += "..."

        if queue != "":
            await ctx.send(queue)
        else:
            await ctx.send("No music in the queue!")

    @commands.command()
    async def clear(self, ctx):

        self.music_queue = []
        self.skip(ctx)

        # Delete all left over mp3 songs
        for filename in os.listdir('.'):
            if filename.endswith('.mp3'):
                logging.info(f"Removing {filename} as part of clearing queue")
                os.remove(filename)

        await ctx.send("Music queue is cleared!")

    @commands.command(alias=["disconnect", "quit"])
    async def leave(self, *args):
        self.music_queue = []
        
        # Stop music if playing
        if self.is_playing:  
            logging.info("Stop music by killing all ffmpeg processes")
            os.system("killall -KILL ffmpeg")
        
        self.is_playing = False
        self.is_paused = False
        
        await self.vc.disconnect()

        # Delete all left over mp3 songs
        for filename in os.listdir('.'):
            if filename.endswith('.mp3'):
                logging.info(f"Removing {filename} as part of the bot leaving")
                os.remove(filename)

    @commands.command(alias=["suffle"])
    async def shuffle(self, ctx):
        random.shuffle(self.music_queue)
        await ctx.send("Playlist shuffled!")
    
    
    @commands.group()
    async def playlist(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid playlist command. Use p (for play) or list")

    @playlist.command()
    async def p(self, ctx, *args):
        query = " ".join(args)

        # Get users voice channel
        voice_channel = ctx.author.voice.channel if ctx.author.voice else None
        if voice_channel is None:
            await ctx.send("Connect to a voice channel!")
        else:
            if query != " ":
                if query in os.listdir('./playlists'):
                    # add songs to list
                    for song in os.listdir(f"./playlists/{query}"):
                        song = {'title': song[:-4], 'path': f"./playlists/{query}/{song}", 'delete': False}
                        self.music_queue.append([song, voice_channel])
                    
                    # Shuffle queue
                    random.shuffle(self.music_queue)

                    # Start playing songs
                    await ctx.send(f"Playlist {query} has been added to the queue!")
                    logging.info(f"Added playlist {query} to the queue")
                    await self.start_music(ctx)
                else:
                    await ctx.send(f"{query} is not a playlist!")

    @playlist.command()
    async def list(self, ctx):
        list = ""
        for i, playlist in enumerate(os.listdir('./playlists')):
            list += f"{i}: {playlist} \n"
        
        if list == "":
            await ctx.send("No playlists found!")
        else:
            await ctx.send(list)

    @playlist.command()
    async def sync(self, ctx):
        if (not self.is_syncing):
            logging.info("Commenced on demand sync of playlists")
            await ctx.send("Syncing playlists (this may take a while)")
            thread = threading.Thread(target=self.playlist_sync, daemon=True)
            thread.start()
        else:
            await ctx.send("Already syncing!")
            logging.warning("Tried syncing when already syncing")

    @tasks.loop(time=sync_playlist_time)
    async def check_playlists(self):
        logging.info("Commenced scheduled sync of playlists")
        if (not self.is_syncing):
            thread = threading.Thread(target=self.playlist_sync, daemon=True)
            thread.start()
        else:
            logging.warning("Tried syncing when already syncing")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Automatic leaving of voice chat if alone
        if member.id == self.bot.user.id:
            return

        # User has left channel
        if before.channel != None:
            voice = discord.utils.get(self.bot.voice_clients, channel__guild__id = before.channel.guild.id)

            if voice == None or voice.channel.id != before.channel.id:
                return
            
            if len(voice.channel.members) <= 1:
                time = 0
                while True:
                    await asyncio.sleep(1)
                    time += 1

                    if len(voice.channel.members) >= 2 or not voice.is_connected():
                        break
                    
                    if time >= 5:
                        logging.info("Left voice channel automatically")
                        await self.leave(voice)
                        return

async def setup(bot):
    await bot.add_cog(MusicCog(bot))