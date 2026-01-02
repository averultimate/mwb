import os
import traceback
import requests
import discord

from collections import defaultdict
from discord.ext import commands
from github import Github
from dotenv import load_dotenv

from bot.queuemaid import load_queue, save_queue
from utils.ngrams import get_ngrams
from bot import config

load_dotenv()

class WordList(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.gh = Github(os.getenv("GITHUB_TOKEN"))
		self.repo = self.gh.get_repo(config.REPO_NAME)
		self.pending_adds, self.pending_dels, self.contributors = load_queue()


	# ------------------------------------#
	# 				Reactions			  #
	# ------------------------------------#

	@commands.Cog.listener()
	async def on_raw_reaction_add(self, payload):
		if payload.user_id == self.bot.user.id:
			return

		if payload.channel_id not in {config.ADD_CHANNEL_ID, config.DEL_CHANNEL_ID}:
			return

		if str(payload.emoji) != config.CONFIRM_EMOJI:
			return

		channel = self.bot.get_channel(payload.channel_id)
		message = await channel.fetch_message(payload.message_id)

		word = message.content.strip()
		author_id = str(message.author.id)
		guild = self.bot.get_guild(payload.guild_id)

		member = guild.get_member(message.author.id)
		role = guild.get_role(config.CONTRIBUTOR_ROLE_ID)

		if payload.channel_id == config.ADD_CHANNEL_ID:
			self.pending_adds.add(word)
		else:
			self.pending_dels.add(word)

		self.contributors.add(author_id)
		await self.grant_role(member, role)

		save_queue(self.pending_adds, self.pending_dels, self.contributors)


	# ------------------------------------ #
	# 				Commands			   #
	# ------------------------------------ #

	@commands.command(
		name="syncwords",
		aliases=["add-all", "sync-all", "sync-words", "add-words", "aa", "aw"]
	)
	@commands.has_role(config.MOD_ROLE_ID)
	async def sync_all(self, ctx):
		if not (self.pending_adds or self.pending_dels):
			return await ctx.send("Queue is empty.")

		status = await ctx.send("<a:processing:1456577308038271079> Connecting...")

		try:
			existing_words = self.fetch_word_list(config.WORDS_PATH)
			old_ngrams = self.fetch_ngram_counts()

			updated_words = (existing_words | self.pending_adds) - self.pending_dels
			new_words_content = "\n".join(sorted(updated_words))

			await status.edit(content="<a:processing:1456577308038271079> Generating N-grams...")

			new_ngrams = self.generate_ngrams(updated_words)
			new_ngrams_content = self.format_ngrams(new_ngrams)

			commit_msg = f"Sync: +{len(self.pending_adds)} / -{len(self.pending_dels)} words"

			self.update_repo_file(config.WORDS_PATH, new_words_content, commit_msg)
			self.update_repo_file(config.NGRAMS_PATH, new_ngrams_content, commit_msg)

			await self.send_announcement(ctx.guild, updated_words, old_ngrams, new_ngrams)

			self.clear_queue()
			await status.edit(content=f"✅ **Success!** {len(updated_words)} words are now live.")

		except Exception as e:
			traceback.print_exc()
			await status.edit(content=f"❌ **Sync Failed:** {e}")


	# ------------------------------------ #
	# 				Helpers				   #
	# ------------------------------------ #

	def fetch_word_list(self, path):
		resp = requests.get(config.RAW_URL + path)
		resp.raise_for_status()
		return set(resp.text.splitlines())

	def fetch_ngram_counts(self):
		resp = requests.get(config.RAW_URL + config.NGRAMS_PATH)
		resp.raise_for_status()

		counts = defaultdict(int)
		for line in resp.text.splitlines():
			key, value = line.split(":")
			counts[key] = int(value)
		return counts

	def generate_ngrams(self, words):
		counts = defaultdict(int)
		for word in words:
			for ngram in get_ngrams(word):
				if "'" in ngram or "-" in ngram:
					continue
				counts[ngram] += 1
		return counts

	def format_ngrams(self, ngrams):
		return "\n".join(
			f"{k}:{v}" for k, v in sorted(ngrams.items(), key=lambda x: x[1])
		)

	def update_repo_file(self, path, content, message):
		meta = self.repo.get_contents(path, ref=config.BRANCH)
		self.repo.update_file(
			path=path,
			message=message,
			content=content,
			sha=meta.sha,
			branch=config.BRANCH,
		)

	async def send_announcement(self, guild, words, old, new):
		channel = self.bot.get_channel(config.ANN_CHANNEL_ID)
		if not channel:
			return

		changes = []
		for key in sorted(old.keys() | new.keys()):
			before = old.get(key, 0)
			after = new.get(key, 0)
			if before != after:
				changes.append(f"{key} ({before} → {after})")

		contributors = " ".join(f"<@{uid}>" for uid in self.contributors)

		embed = discord.Embed(
			title="📚 Word List Updated",
			description=f"Total words: **{len(words)}** (+{len(self.pending_adds)} / -{len(self.pending_dels)})"
		)
		embed.add_field(name="Prompt Changes", value=" ".join(changes).upper() or "None")
		embed.add_field(name="Contributors", value=contributors or "—")

		await channel.send(f"<@&{config.ANN_ROLE_ID}>", embed=embed)

	def clear_queue(self):
		self.pending_adds.clear()
		self.pending_dels.clear()
		self.contributors.clear()
		save_queue(self.pending_adds, self.pending_dels, self.contributors)

	async def grant_role(self, member, role):
		if member and role and role not in member.roles:
			try:
				await member.add_roles(role)
			except discord.Forbidden:
				pass


async def setup(bot):
	await bot.add_cog(WordList(bot))
