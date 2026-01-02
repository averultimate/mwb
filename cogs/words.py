import discord
from collections import defaultdict
from discord.ext import commands
from github import Github
from dotenv import load_dotenv
from bot.queuemaid import save_queue, load_queue
from utils.ngrams import get_ngrams
from bot import config
import os
import traceback
import requests

load_dotenv()

class WordList(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.gh = Github(os.getenv("GITHUB_TOKEN"))
		self.repo = self.gh.get_repo(config.REPO_NAME)
		self.pending_adds, self.pending_dels, self.contributors = load_queue()


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

		if payload.channel_id == config.ADD_CHANNEL_ID and str(payload.emoji) == config.CONFIRM_EMOJI:
			self.pending_adds.add(word)
			self.contributors.add(str(message.author.id))
			await self.grant_role(contributor, role)

		elif payload.channel_id == config.DEL_CHANNEL_ID and str(payload.emoji) == config.CONFIRM_EMOJI:
			self.pending_dels.add(word)
			self.contributors.add(str(message.author.id))
			await self.grant_role(contributor, role)

		save_queue(self.pending_adds, self.pending_dels, self.contributors)


	@commands.command(name="syncwords", aliases=['add-all', 'sync-all', 'sync-words', 'add-words', 'aa', 'aw'])
	@commands.has_role(config.MOD_ROLE_ID)
	async def sync_all(self, ctx):
		if not self.pending_adds and not self.pending_dels:
			return await ctx.send("Queue is empty.")

		msg = await ctx.send("<a:processing:1456577308038271079> Connecting to word list database...")

		try:
			response = requests.get(config.RAW_URL + config.WORDS_PATH)
			if response.status_code != 200:
				return await msg.edit(content="❌ Failed to download the current list.")

			ngrams_old = requests.get(config.RAW_URL + config.NGRAMS_PATH)
			if ngrams_old.status_code != 200:
				return await msg.edit(content="❌ Failed to download the current list.")
			ngrams_file = self.repo.get_contents(config.NGRAMS_PATH, ref=config.BRANCH)
			existing_words = set(response.text.splitlines())
			existing_ngrams = set(ngrams_old.text.splitlines())
			old_ngrams = defaultdict(int)
			for line in existing_ngrams:
				s = line.split(':')
				old_ngrams[s[0]] = int(s[1])
			file_metadata = self.repo.get_contents(config.WORDS_PATH, ref=config.BRANCH)
			sha = file_metadata.sha

			await msg.edit(content="<a:processing:1456577308038271079> Processing words...")
			updated_set = (existing_words | self.pending_adds) - self.pending_dels
			new_content = "\n".join(sorted(list(updated_set)))
			solve_counts = defaultdict(int)

			await msg.edit(content="<a:processing:1456577308038271079> Generating N-grams...")
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
				path=config.WORDS_PATH,
				message=sync_message,
				content=new_content,
				sha=sha,
				branch=config.BRANCH
			)

			self.repo.update_file(
				path=config.NGRAMS_PATH,
				message=sync_message,
				content=ngrams_content,
				sha=ngrams_file.sha,
				branch=config.BRANCH
			)

			mention_list = " ".join([f"<@{uid}>" for uid in self.contributors])
			announcement_channel = self.bot.get_channel(config.ANN_CHANNEL_ID)
			if announcement_channel:
				keys1 = set(old_ngrams.keys())
				keys2 = set(solve_counts.keys())

				prompts = ""

				only_in_d1 = keys1 - keys2
				if only_in_d1:
					for key in only_in_d1:
						# Removed prompts
						prompts += f'{key} ({old_ngrams[key]} -> 0). '

				only_in_d2 = keys2 - keys1
				if only_in_d2:
					for key in only_in_d2:
						prompts += f'{key} (0 -> {solve_counts[key]}). '

				common_keys = keys1.intersection(keys2)
				diff_values = {key: (old_ngrams[key], solve_counts[key]) for key in common_keys if old_ngrams[key] != solve_counts[key]}
				if diff_values:
					for key, values in diff_values.items():
						if (old_ngrams[key] <= 8 and solve_counts[key] > 8) or (solve_counts[key] >= 9 and old_ngrams[key] <= 8) or (solve_counts[key] <= 8):
							prompts += f'{key} ({old_ngrams[key]} -> {solve_counts[key]}). '

				embed=discord.Embed(title="📚 New words added", description=f"There are now a total of {len(updated_set)} words in the list, this iteration adding {len(self.pending_adds)} and removing {len(self.pending_dels)} words. Here are the prompt changes, summarized:")
				embed.add_field(name="Prompts", value=prompts.upper(), inline=True)
				embed.add_field(name="Contributors", value=mention_list, inline=True)
				await announcement_channel.send(f'<@&{config.ANN_ROLE_ID}>', embed=embed)

			self.pending_adds.clear()
			self.pending_dels.clear()
			self.contributors.clear()
			save_queue(self.pending_adds, self.pending_dels, self.contributors)
			await msg.edit(content=f":ballot_box_with_check: **Success!** {len(updated_set)} words are now live.")

		except Exception as e:
			traceback.print_exc()
			await msg.edit(content=f"❌ **Sync Failed:** {e}")


	async def grant_role(self, member, role):
		if member and role and role not in member.roles:
			try: await member.add_roles(role)
			except: pass

async def setup(bot):
	await bot.add_cog(WordList(bot))
