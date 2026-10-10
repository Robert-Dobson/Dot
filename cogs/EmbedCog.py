import re

import requests

import discord
from discord.ext import commands
import logging
import datetime

logger = logging.getLogger(__name__)


class EmbedCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        # https://github.com/Kyrela/FixTweetBot/blob/main/README.md#awesome-fixers
        self.link_providers = [
            LinkProvider(
                name="Reddit",
                original_domain="reddit.com",
                replacement_domains=["vxreddit.com", "rxddit.com", "redditez.com"],
            ),
            LinkProvider(
                name="Instagram",
                original_domain="instagram.com",
                replacement_domains=["oginstagram.com", "uuinstagram.com", "zzinstagram.com", "kkinstagram.com"],
            ),
            LinkProvider(
                name="Twitter", original_domain="twitter.com", replacement_domains=["fxtwitter.com", "vxtwitter.com"]
            ),
            LinkProvider(name="x", original_domain="x.com", replacement_domains=["fixupx.com", "fixvx.com"]),
            LinkProvider(
                name="Spotify", original_domain="spotify.com", replacement_domains=["fixspotify.com", "fixspotify.com"]
            ),
        ]

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Process incoming messages and replace links with alternative versions.
        """
        if message.author == self.bot.user:
            return

        # Get all replaced links from the message contents, configured by the link providers
        replaced_links = []
        for provider in self.link_providers:
            replaced_links.extend(provider.replace_all_links(message.content))

        if not replaced_links:
            return

        # Delete embeds on the original message
        try:
            await message.edit(suppress=True)
        except discord.Forbidden:
            logger.warning(
                f"Failed to suppress embeds for message {message.id} in channel {message.channel.id} due to insufficient permissions."
            )

        links = "\n".join(replaced_links)
        content = f"{links}\n-# If I got this wrong, react with ❌ within 5 minutes to delete this message."
        logger.info(f"Replying to message {message.id} in channel {message.channel.id} with replaced links.")
        await message.reply(content=content)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, reactionEvent):
        """
        Delete the bot's message if a user reacts with ❌ within 5 minutes of the message being sent.
        """
        if reactionEvent.emoji.name != "❌":
            return

        channel = self.bot.get_channel(reactionEvent.channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(reactionEvent.message_id)

            if message.created_at < (discord.utils.utcnow() - datetime.timedelta(minutes=5)):
                logger.info(
                    f"Reaction ❌ on message {reactionEvent.message_id} in channel {reactionEvent.channel_id} ignored due to time limit."
                )
                return

            if message.author == self.bot.user:
                logger.info(
                    f"Deleting message {reactionEvent.message_id} in channel {reactionEvent.channel_id} due to ❌ reaction."
                )
                await message.delete()
        except discord.Forbidden:
            logger.warning(
                f"Failed to delete message {reactionEvent.message_id} in channel {reactionEvent.channel_id} due to insufficient permissions.",
            )


class LinkProvider:
    def __init__(self, name, original_domain, replacement_domains):
        self.name = name
        self.original_domain = original_domain
        self.replacement_domain = replacement_domains
        self.regex = rf"(https?://(?:[\w-]+\.)?{re.escape(original_domain)}[^\s|]+)"

    def replace_all_links(self, text):
        """
        Finds all links in the text that contain the original domain and replaces each one with the first valid replacement. Returns a list of replaced links.
        """
        if self.original_domain not in text:
            return []

        matches = re.findall(self.regex, text)
        results = []
        for match in matches:
            if (replaced_link := self.replace_link(match)) is not None:
                if re.search(rf"\|\|[^\|]*{re.escape(match)}[^\|]*\|\|", text):
                    # Add spaces around the link to prevent Discord from including | in the link itself when it's inside spoiler tags
                    replaced_link = f"|| {replaced_link} ||"
                results.append(replaced_link)

        return results

    def replace_link(self, link):
        """
        Replaces the original domain in a single link with the replacement domain, and returns first valid replacement link or None if no valid replacement is found.
        """
        for replacement_domain in self.replacement_domain:
            replaced_link = link.replace(self.original_domain, replacement_domain)

            if self.is_valid_link(replaced_link):
                logger.warning(
                    f"Replacement link {replaced_link} for {self.name} does not return a 200 status code. Skipping."
                )
                continue

            logger.info(f"Replaced link {link} with {replaced_link} for {self.name}.")
            return replaced_link

        return None

    def is_valid_link(self, url, timeout=10):
        headers = {
            # Present to be discordbot: https://support.discord.com/hc/en-us/articles/42500550752919-About-Discord-Link-Previews-and-the-Discordbot
            "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
        }

        try:
            # Some embed services redirect to the original domain for users, so disable redirects
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False)

            if response.status_code == 200:
                html_content = response.text
                logger.debug(f"HTML content for {url}: {html_content}")

                if self.is_valid_open_graph_object(html_content):
                    print(f"Valid embed payload found! Status Code: {response.status_code}")
                    return True
                else:
                    print("URL loaded, but lacks proper Open Graph metadata tags for an embed.")
                    return False
            else:
                print(f"Server returned an error status code: {response.status_code}")
                return False

        except requests.RequestException as e:
            print(f"Network error trying to fetch the embed: {e}")
            return False

    def is_valid_open_graph_object(self, html_content):
        """
        Checks if the HTML content contains mandatory Open Graph metadata tags.
        https://ogp.me/
        """
        return (
            '<meta property="og:title"' in html_content
            and '<meta property="og:type"' in html_content
            # and '<meta property="og:image"' in html_content # While the documentation says this is required, some embeds don't have an image and still work fine.
            and '<meta property="og:url"' in html_content
        )


async def setup(bot):
    await bot.add_cog(EmbedCog(bot))
