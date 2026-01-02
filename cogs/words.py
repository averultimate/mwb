import discord
from discord.ext import commands
from github import Github
from dotenv import load_dotenv
from bot.queuemaid import save_queue, load_queue
from utils.ngrams import get_ngrams
from bot import config
import os

load_dotenv()

class WordList(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.gh = Github(os.getenv("GITHUB_TOKEN"))
		self.repo = self.gh.get_repo(config.REPO_NAME)
		self.pending_adds, self.pending_dels = load_queue()


	@commands.Cog.listener()
	async def on_raw_reaction_add(self, payload):
		if payload.user_id == self.bot.user.id:
			return

		if payload.channel_id not in [config.ADD_CHANNEL_ID, config.DEL_CHANNEL_ID]:
			return

		channel = self.bot.get_channel(payload.channel_id)
		message = await channel.fetch_message(payload.message_id)
		word = message.content.strip()
		guild = self.bot.get_guild(payload.guild_id)

		contributor = guild.get_member(message.author.id)
		role = guild.get_role(config.CONTRIBUTOR_ROLE_ID)

		if payload.channel_id == config.ADD_CHANNEL_ID and str(payload.emoji) == config.ADD_EMOJI:
			self.pending_adds.add(word)
			await self.grant_role(contributor, role)

		elif payload.channel_id == config.DEL_CHANNEL_ID and str(payload.emoji) == config.DEL_EMOJI:
			self.pending_dels.add(word)
			await self.grant_role(contributor, role)

		save_queue(self.pending_adds, self.pending_dels)


	async def grant_role(self, member, role):
		if member and role and role not in member.roles:
			try:
				await member.add_roles(role)
			except discord.Forbidden:
				print(f"Error: Bot lacks permission to give roles to {member.name}")


	@commands.command(name="syncwords", aliases=['add-all', 'sync-all', 'sync-words', 'add-words', 'aa', 'aw'])
	@commands.has_role(config.MOD_ROLE_ID)
	async def sync_all(self, ctx):
		if not self.pending_adds and not self.pending_dels:
			return await ctx.send("Queue is empty.")

		msg = await ctx.send("🔄 Connecting to GitHub...")

		try:
			file = self.repo.get_contents(config.WORDS_PATH, ref=config.BRANCH)
			ngrams_file = self.repo.get_contents(config.NGRAMS_PATH, ref=config.BRANCH)
			existing_words = set(file.decoded_content.decode('utf-8').splitlines())

			updated_set = (existing_words | self.pending_adds) - self.pending_dels
			new_content = "\n".join(sorted(list(updated_set)))
			solve_counts = defaultdict(int)

			for word in updated_set:
				for ngram in get_ngrams(word):
					if "'" in ngram or "-" in ngram:
						continue

					solve_counts[ngram] += 1

			ngrams_content = ""
			for ngram, count in sorted(solve_counts.items(), key=lambda x: x[1]):
				ngrams_content += f"{ngram}:{count}\n"

			sync_message = f"Sync: +{len(self.pending_adds)} / -{len(self.pending_dels)} words"

			self.repo.update_file(
				path=file.path,
				message=sync_message,
				content=new_content,
				sha=file.sha,
				branch=config.BRANCH
			)

			self.repo.update_file(
				path=ngram_file.path,
				message=sync_message,
				content=ngrams_content,
				sha=ngram_file.sha,
				branch=config.BRANCH
			)

			self.pending_adds.clear()
			self.pending_dels.clear()
			save_queue(self.pending_adds, self.pending_dels)
			await msg.edit(content="🚀 **GitHub Updated!** The list has been merged and sorted.")

		except Exception as e:
			await msg.edit(content=f"❌ **Sync Failed:** {e}")

async def setup(bot):
	await bot.add_cog(WordList(bot))
