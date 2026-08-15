import os
import numpy as np

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEndpointEmbeddings

# --------------------------------------------------
# 1. LOAD ENVIRONMENT VARIABLES
# --------------------------------------------------

load_dotenv()

# --------------------------------------------------
# 2. CREATE LANGCHAIN EMBEDDING MODEL
# --------------------------------------------------

embeddings = HuggingFaceEndpointEmbeddings(model="Octen/Octen-Embedding-0.6B")


# --------------------------------------------------
# 3. SENTENCES
# --------------------------------------------------

source_sentence = "That is a happy person"

sentences = [
    "That is a happy dog",
    "That is a very happy person",
    "Today is a sunny day",
]


# --------------------------------------------------
# 4. GENERATE EMBEDDING FOR ONE SENTENCE
# --------------------------------------------------

print("=" * 60)
print("SINGLE SENTENCE EMBEDDING")
print("=" * 60)

source_embedding = embeddings.embed_query(source_sentence)

print("\nSentence:")
print(source_sentence)

print("\nEmbedding:")
print(source_embedding)

print("\nEmbedding dimension:")
print(len(source_embedding))


# --------------------------------------------------
# 5. GENERATE EMBEDDINGS FOR MULTIPLE SENTENCES
# --------------------------------------------------

print("\n" + "=" * 60)
print("MULTIPLE SENTENCE EMBEDDINGS")
print("=" * 60)

sentence_embeddings = embeddings.embed_documents(sentences)

for sentence, vector in zip(sentences, sentence_embeddings):
    print("\nSentence:")
    print(sentence)

    print(f"Embedding dimension: {len(vector)}")
    print(f"First 5 values: {vector[:5]}")


# --------------------------------------------------
# 6. COSINE SIMILARITY FUNCTION
# --------------------------------------------------

def cosine_similarity(vector1, vector2):
    vector1 = np.array(vector1)
    vector2 = np.array(vector2)

    return np.dot(vector1, vector2) / (
        np.linalg.norm(vector1) * np.linalg.norm(vector2)
    )


# --------------------------------------------------
# 7. CALCULATE SIMILARITY
# --------------------------------------------------

print("\n" + "=" * 60)
print("SEMANTIC SIMILARITY")
print("=" * 60)

for sentence, vector in zip(sentences, sentence_embeddings):

    score = cosine_similarity(
        source_embedding,
        vector
    )

    print(f"\nSimilarity: {score:.4f}")
    print(f"Sentence:   {sentence}")


# --------------------------------------------------
# 8. FIND THE MOST SIMILAR SENTENCE
# --------------------------------------------------

scores = []

for sentence, vector in zip(sentences, sentence_embeddings):

    score = cosine_similarity(
        source_embedding,
        vector
    )

    scores.append((sentence, score))


scores.sort(key=lambda x: x[1], reverse=True)

print("\n" + "=" * 60)
print("MOST SIMILAR SENTENCE")
print("=" * 60)

best_sentence, best_score = scores[0]

print(f"\nSentence: {best_sentence}")
print(f"Score:    {best_score:.4f}")
