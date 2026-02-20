VECTOR_VQL = """
VQL supports embedding model-powered functions capable of performing similarity search operations with vector embedding fields, by comparing them with a search string.
For example, VECTOR_DISTANCE can search for the query 'black car' in embedding vectors of images to retrieve the N most relevant rows of images that contain black cars in them.
Embedding-based search is superior to keyword-based search.
When working with similarity search a limit must always be imposed for N. Default should be 5 unless otherwise specified.

    - VECTOR_DISTANCE(<target vector:vector>, <search query:text> [, <distance metric:text>]):float. Embedding-powered. Returns the distance between a textual search query and an embedding vector to filter by similarity. Most similar results will have the smallest distance, so order ASC to obtain most similar.
    - EMBED_AI(<search query:text> [, <embedding model:text>]):vector. Embeds a given text to obtain it's vector representation.
    - VECTOR_COSINE_DISTANCE(<vector1:vector>, <vector2:vector>):float. Calculates the distance between two vectors using cosine distance.
    - VECTOR_L1_DISTANCE(<vector1:vector>, <vector2:vector>):float. Calculates the distance between two vectors using L1 distance.
    - VECTOR_L2_DISTANCE(<vector1:vector>, <vector2:vector>):float.Calculates the distance between two vectors using L2 distance.
    """
