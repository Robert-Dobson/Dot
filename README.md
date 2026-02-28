# Dot
Dot is my personal Discord bot written in Python. Its primary purpose is to allow users to play music in a Discord server, but it also supports fixing embeds for various social media links. It utilizes the Discord API, ffmpeg and yt_dlp to stream songs.

## Features
- Allows you to search and stream YouTube songs in a voice channel 
- Allows you to make a music queue and automatically plays through each song in the queue
- Updates the channel status to show the song currently playing
- Automatically fixes embeds for social media links (Reddit, Instagram, Twitter/X, TikTok) by replacing them with embed-friendly versions
  - This will reply to any message using the social media link with the embed-friendly version and then remove the embed from the original message
  - Spoiler tags should also automatically persist

## Commands
Music:
- `/play <song_query>` - Plays requested song from YouTube
- `/pause` - Pauses the currently playing song
- `/resume` - Resumes the currently playing song if paused
- `/skip [num_to_skip]` - Skips specified number of songs (default: 1)
- `/queue` - Displays next 20 songs in queue (and current song)
- `/clear` - Removes all songs from the queue (current song is unaffected)
- `/leave` - Disconnects bot from voice channel
- `/shuffle` - Shuffles current queue

Other:
- `/test` - Replies with test message
- `/random <num>` - Generates a random number from 1 to n
- `/sync_slash_commands` (prefix command) - Syncs slash commands to the guild. This must be done during initial set-up and whenever the slash commands are updated

## Dependencies
Python libraries can be installed using the `requirements.txt` provided in this repo:
```bash
python -m pip install -r requirements.txt
```

You must also install `FFmpeg` (Multimedia framework to stream music) - https://ffmpeg.org/about.html. Make sure this is in your PATH.

And finally you must install a supported JavaScript runtime: https://github.com/yt-dlp/yt-dlp/wiki/EJS

