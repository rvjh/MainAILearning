import os
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Create Hugging Face client
client = InferenceClient(provider="hf-inference")

# --------------------------------------------------
# 1. SENTENCE
# --------------------------------------------------

source_sentence = "That is a happy person"

sentences = [
    "That is a happy dog",
    "That is a very happy person",
    "Today is a sunny day"
]


# --------------------------------------------------
# 2. GENERATE EMBEDDING
# --------------------------------------------------

print("=" * 60)
print("GENERATING EMBEDDING")
print("=" * 60)

embedding = client.feature_extraction(
    source_sentence,
    model="Octen/Octen-Embedding-0.6B"
)

print(f"\nSentence:")
print(source_sentence)

print(f"\nEmbedding type:")
print(type(embedding))

print(f"\nEmbedding:")
print(embedding)

# If it is a list/array, show its dimension
try:
    print(f"\nEmbedding dimension: {len(embedding)}")
except TypeError:
    print("\nCould not determine embedding dimension.")


# --------------------------------------------------
# 3. CALCULATE SENTENCE SIMILARITY
# --------------------------------------------------

print("\n" + "=" * 60)
print("CALCULATING SENTENCE SIMILARITY")
print("=" * 60)

similarity_scores = client.sentence_similarity(
    source_sentence,
    other_sentences=sentences,
    model="Octen/Octen-Embedding-0.6B"
)


# --------------------------------------------------
# 4. DISPLAY RESULTS
# --------------------------------------------------

print(f"\nSource sentence:")
print(f"  {source_sentence}\n")

for sentence, score in zip(sentences, similarity_scores):
    print(f"Similarity: {score:.4f}")
    print(f"Sentence:   {sentence}")
    print("-" * 60)
