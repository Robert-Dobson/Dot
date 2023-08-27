# Dot
Dot is my personal Discord bot written in Python that allows users to play music in a Discord server. It utilizes the Discord API and ffmpeg to play music files on a given voice channel. Note this project should only be used to play songs you legally own.

## Features
- Plays high-quality MP3 files in a voice channel
- Allows you to make a music queue and automatically plays through each song in the queue
- Can search and stream YouTube videos
- Allows you to play pre-built playlists in your local file system
- And more to come...

## Commands
- `/play <query>` - Searches Youtube for the music that best matches the query and adds it to the queue to play in your current voice channel
- `/pause` - Pauses the currently playing music
- `/resume` - Resumes the currently playing music
- `/skip` - Skips the current song
- `/queue` - Lists the next 20 songs in the queue
- `/clear` - Clears the queue
- `/leave` - Disconnects the discrod bot and clears the queue
- `/shuffle` - Shuffles the queue
- `/playlist p <query>` - Adds all songs in the given playlist
- `/playlist list` - Lists all avaliable playlists

## Dependencies
Python libraries can be installed using the `requirements.txt` provided in this repo:
```bash
python -m pip install -r requirements.txt
```

You must also install `FFmpeg` (Multimedia framework to stream music) - https://ffmpeg.org/about.html. Make sure this is in your PATH.

