def get_ngrams(word, nv=(2,3)):
	for n in nv:
		for i in range(len(word) - n + 1):
			yield word[i:i + n]
