import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import os
import re
import random


# TODO: Parallel for getting youtube music
# TODO: Understand why we can't replace the play mp3 code in first play with just call to function
# TODO: Do we need self.is_paused bit in play command
# TODO: Remove specific songs
# TODO: Current song playing command?

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
        }
        self.pid = 0
        
        self.vc = None
    
    async def search_youtube(self, item):
            # Use youtube downloader to download the youtube song
            with YoutubeDL(self.YDL_OPTIONS) as ydl:
                try:
                     info = ydl.extract_info("ytsearch:%s" % item, download=True)['entries'][0]
                except Exception as e:
                     print(e) # Debugging purposes
                     return False
            return {'title': info['title'], 'path': f"{info['title']} [{info['id']}].mp3"} 
    
    def end_song(self, path, remove):
        # Remove file to clear up space if not in queue anymore
        match = re.search(".*\[(.*)\].*", path)
        if match and remove:
            song_id = match.group(1)
                
            if len([song[0] for song in self.music_queue if song[0]['id'] == song_id]) == 0:
                try:
                    os.remove(path)
                except Exception as e:
                    print(e) # Debugging purposes
            
        self.play_next(remove)
        

    def play_next(self, remove):
        if len(self.music_queue) > 0:
            self.is_playing = True
            music = self.music_queue.pop(0)
            path = music[0]['path']
            
            self.vc.play(discord.FFmpegPCMAudio(path, executable="ffmpeg.exe", options="-vn"), after = lambda e : self.end_song(path, remove))
        else:
            self.is_playing = False
            

    async def start_music(self, ctx, remove=True):
        if len(self.music_queue) > 0:
            self.is_playing = True
            target_vc = self.music_queue[0][1]
            music = self.music_queue.pop(0)
            path = music[0]['path']

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
            self.vc.play(discord.FFmpegPCMAudio(path, executable="ffmpeg.exe", options="-vn"), after = lambda e : self.end_song(path, remove))
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
            os.system("taskkill /F /im ffmpeg.exe")
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
            os.system("taskkill /F /im ffmpeg.exe")
        
        self.is_playing = False
        self.is_paused = False
        
        await self.vc.disconnect()

        # Delete all left over mp3 songs
        for filename in os.listdir('.'):
            if filename.endswith('.mp3'):
                os.remove(filename)

    @commands.command()
    async def suffle(self, ctx):
        random.shuffle(self.music_queue)
    
    
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
                        song = {'title': song[:-4], 'path': f"./playlists/{query}/{song}"}
                        self.music_queue.append([song, voice_channel])
                    
                    # Start playing songs
                    await self.start_music(ctx, False)
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

async def setup(bot):
    await bot.add_cog(MusicCog(bot))