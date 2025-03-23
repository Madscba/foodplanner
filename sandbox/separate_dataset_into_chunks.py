import pandas as pd
import numpy as np
#load
# dataset = pd.read_csv(r"C:\Users\MadsChristianBerggre\Downloads\archive (3)\RAW_recipes.csv")
# # Split the dataset into 5 chunks
# chunks = np.array_split(dataset, 2)
# # Save each chunk to a separate file
# for i, chunk in enumerate(chunks):
#     chunk.to_csv(f"recipe_chunk_{i}.csv", index=False)
#
# dataset = pd.read_csv(r"C:\Users\MadsChristianBerggre\Downloads\archive (3)\RAW_interactions.csv")
# # Split the dataset into 5 chunks
# chunks = np.array_split(dataset, 2)
# # Save each chunk to a separate file
# for i, chunk in enumerate(chunks):
#     chunk['review'] = chunk['review'].astype(str)
#     chunk['review'] = chunk['review'].apply(lambda x: f'"{x}"')
#     #encapsulate the review in double quotes
#
#     chunk.to_csv(f"user_interaction_chunk_{i}.csv", index=False)

dataset = pd.read_csv(r"C:\Users\MadsChristianBerggre\Documents\Development\foodplanner\foodplanning\recipes.csv")
#encaupsulate the recipe in double quotes
