# Dot
Dot is my personal Discord bot written in Python that allows users to play music in a Discord server. It utilizes the Discord API, ffmpeg and yt_dlp to stream songs.

## Features
- Allows you to search and stream YouTube songs in a voice channel 
- Allows you to make a music queue and automatically plays through each song in the queue
- Updates the channel status to show the song currently playing

## Commands
- `/play <query>` - Searches Youtube for the music that best matches the query and adds it to the queue to play in your current voice channel
- `/pause` - Pauses the currently playing music
- `/resume` - Resumes the currently playing music
- `/skip` - Skips the current song
- `/queue` - Lists the next 20 songs in the queue
- `/clear` - Clears the queue
- `/leave` - Disconnects the discrod bot and clears the queue
- `/shuffle` - Shuffles the queue

## Dependencies
Python libraries can be installed using the `requirements.txt` provided in this repo:
```bash
python -m pip install -r requirements.txt
```

You must also install `FFmpeg` (Multimedia framework to stream music) - https://ffmpeg.org/about.html. Make sure this is in your PATH.

And finally you must install a supported JavaScript runtime: https://github.com/yt-dlp/yt-dlp/wiki/EJS

