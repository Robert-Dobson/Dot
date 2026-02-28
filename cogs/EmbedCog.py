import re

import discord
from discord.ext import commands
import logging

logger = logging.getLogger(__name__)

class EmbedCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.link_providers = [
            LinkProvider("Reddit", "reddit.com", "rxddit.com"),
            LinkProvider("Instagram", "instagram.com", "fxstagram.com"),
        ]
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        
        # Filter out messages that don't have links
        if 'https://' not in message.content and 'http://' not in message.content:
            return
        

        # Process each link provider, e.g. Reddit, Instagram, etc.
        replaced_links = []
        for provider in self.link_providers:
            # Skip if the message doesn't contain the provider's domain
            if provider.original_domain not in message.content:
                continue

            replaced_links.extend(provider.replace_link(message.content))
        
        if not replaced_links:
            return

        # Delete embeds on the original message]
        try:
            await message.edit(suppress=True)
        except discord.Forbidden:
            logger.warning(f"Failed to suppress embeds for message {message.id} in channel {message.channel.id} due to insufficient permissions.")

        # Reply with new links, preserving spoiler formatting if applicable
        await message.reply(content='\n'.join(replaced_links))  


class LinkProvider():
    def __init__(self, name, original_domain, replacement_domain):
        self.name = name
        self.original_domain = original_domain
        self.replacement_domain = replacement_domain
        self.regex = rf'(https?:\/\/(?:www\.)?{re.escape(original_domain)}\/[^\s|]+)'
    
    def replace_link(self, text):
        """
        Finds all links matching the provider's domain in the text, replaces the domain, and preserves spoiler formatting if applicable.
        """
        matches = re.findall(self.regex, text)
        results = []
        for match in matches:
            replaced_link = match.replace(self.original_domain, self.replacement_domain)
            if re.search(rf'\|\|[^\|]*{re.escape(match)}[^\|]*\|\|', text):
                replaced_link = f'||{replaced_link}||'
            results.append(replaced_link)
        return results

async def setup(bot):
    await bot.add_cog(EmbedCog(bot))
