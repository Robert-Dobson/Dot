import discord
from discord.ext import commands, tasks
from yt_dlp import YoutubeDL
import os
import random
import datetime
import threading
import re

sync_playlist_time = datetime.time(hour=14, minute=0) # 2am GMT or 3am BST

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

        self.check_playlists.start()
    
    def search_youtube(self, item):
            # Use youtube downloader to download the youtube song
            with YoutubeDL(self.YDL_OPTIONS) as ydl:
                try:
                     info = ydl.extract_info("ytsearch:%s" % item, download=True)['entries'][0]
                except Exception as e:
                     print(e) # Debugging purposes
                     return False
            return {'title': info['title'], 'path': f"{info['title']} [{info['id']}].mp3", 'delete': True} 
    
    def end_song(self, path, remove):
        # Remove file to clear up space if not in queue anymore
        if remove:
            for song in self.music_queue:
                if song == path:
                    try:
                        os.remove(path)
                    except Exception as e:
                        print(e)
            
        self.play_next()
        

    def play_next(self):
        if len(self.music_queue) > 0:
            self.is_playing = True
            music = self.music_queue.pop(0)
            path = music[0]['path']
            remove = music[0]['delete']
            
            print(f"Playing {music[0]['title']}")
            self.vc.play(discord.FFmpegPCMAudio(path, executable="ffmpeg", options="-vn"), after = lambda e : self.end_song(path, remove))
        else:
            self.is_playing = False
    
    def playlist_sync(self):
        print("Started Playlist Sync")

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
                        print("Gathering Playlist Data")
                        remote_songs = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist[1]}", download=False)['entries']
                    except Exception as e:
                        print(e)
                        
                # Compare local songs to remote songs and update local songs to match
                print("Playlist Data Gathered, now comparing to local songs")
                remote_songs = [f"{song_info['title']} [{song_info['id']}].mp3" for song_info in remote_songs]
                local_songs = os.listdir(f"./playlists/{playlist[0]}")

                missing_songs = list(set(remote_songs) - set(local_songs))
                remove_songs = list(set(local_songs) - set(remote_songs))

                # Download any missing songs
                if (len(missing_songs) > 0):
                    print(f"Found missing songs in {playlist[0]}, downloading now")
                    missing_song_ids = [re.findall(".*\[(.*)\].*", path)[-1] for path in missing_songs]
                    download_options = dict(self.YDL_OPTIONS)
                    download_options['outtmpl'] = f"{os.getcwd()}/playlists/{playlist[0]}/%(title)s [%(id)s].%(ext)s"

                    for missing_song_id in missing_song_ids:
                        print(f"Downloading song_id: {missing_song_id}")
                        with YoutubeDL(download_options) as ydl:
                            try:
                                songs = ydl.extract_info(f"https://www.youtube.com/watch?v={missing_song_id}", download=True)
                            except Exception as e:
                                print(e)

                # Delete any remove_songs
                if (len(remove_songs) > 0):
                    for remove_song in remove_songs:
                        os.remove(f"./playlists/{playlist[0]}/{remove_song}")
            else:
                # Create folder and download all songs
                os.mkdir(f"./playlists/{playlist[0]}")
                download_options = dict(self.YDL_OPTIONS_PLAYLIST)
                download_options['outtmpl'] = f"./playlists/{playlist[0]}/%(title)s [%(id)s].%(ext)s"
                print("Playlist doesn't exist, syncing now")

                with YoutubeDL(download_options) as ydl:
                    try:
                        songs = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist[1]}", download=True)
                    except Exception as e:
                        print(e)     

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
                    # Send error message
                    await ctx.send("Could not connect to the voice channel")
                    return
            else:
                # Move to our channel
                if self.vc != target_vc:
                    await self.vc.move_to(target_vc)
            
            # Play Music
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
                # Find song and play it
                song = await self.search_youtube(query)
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
        if self.vc != None and self.is_playing == True:
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
                os.remove(filename)

        await ctx.send("Music queue is cleared!")

    @commands.command(alias=["disconnect", "quit"])
    async def leave(self, ctx):
        self.music_queue = []
        
        # Stop music if playing
        if self.is_playing:  
            os.system("killall -KILL ffmpeg")
        
        self.is_playing = False
        self.is_paused = False
        
        await self.vc.disconnect()

        # Delete all left over mp3 songs
        for filename in os.listdir('.'):
            if filename.endswith('.mp3'):
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
        await ctx.send("Syncing playlists (this may take a while)")
        thread = threading.Thread(target=self.playlist_sync, daemon=True)
        thread.start()

    @tasks.loop(time=sync_playlist_time)
    async def check_playlists(self, ctx):
        thread = threading.Thread(target=self.playlist_sync, daemon=True)
        thread.start()

async def setup(bot):
    await bot.add_cog(MusicCog(bot))
