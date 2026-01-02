import discord
from discord.ext import commands
import os
import asyncio
import logging
from dotenv import load_dotenv
from bot import config

load_dotenv()
discord.utils.setup_logging(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or(*config.PREFIXES), intents=intents)

@bot.event
async def on_ready():
	logging.info(f"[.] Logged in as {bot.user} (ID: {bot.user.id})")
	logging.info("------")

@bot.event
async def on_command_error(ctx, error):
	if isinstance(error, commands.CommandNotFound):
		return
	elif isinstance(error, commands.MissingPermissions):
		await ctx.reply("You do not have permission to use this command.")
	else:
		logging.error(f"Ignoring exception in command {ctx.command}:", exc_info=error)

async def load_extensions():
	for filename in os.listdir('./cogs'):
		if filename.endswith('.py'):
			extension_name = f'cogs.{filename[:-3]}'
			try:
				await bot.load_extension(extension_name)
				logging.info(f"[.] Loaded extension: {extension_name}")
			except Exception as e:
				logging.error(f"[X] Failed to load extension {extension_name}", exc_info=e)

async def main():
	token = os.getenv("DISCORD_TOKEN")
	if not token:
		logging.critical("[X] DISCORD_TOKEN not found in .env file. Bot cannot start.")
		return

	async with bot:
		await load_extensions()
		await bot.start(token)

if __name__ == '__main__':
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
