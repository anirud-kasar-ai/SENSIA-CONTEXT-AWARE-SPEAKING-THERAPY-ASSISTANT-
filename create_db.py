import streamlit as st
import os
import json
from langchain_text_splitters import TokenTextSplitter
from langchain_chroma import Chroma

from embeddings_config import get_embedding_model
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv
load_dotenv()

CHROMA_DB_DIR = "New_DB"

def load_jsonl_text(jsonl_path):
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        records = json.loads(content)  # JSON array format
    except json.JSONDecodeError:
        records = [json.loads(line) for line in content.strip().splitlines()]  # JSONL format

    texts = [
        f"Instruction: {record['instruction']}\nInput: {record['input']}\nOutput: {record['output']}"
        for record in records
    ]
    return texts

def create_vector_db_from_jsonl(jsonl_path, persist_dir=CHROMA_DB_DIR, batch_size=5000):
    texts = load_jsonl_text(jsonl_path)
    splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=50)
    embeddings = get_embedding_model()

    vectordb = None
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        chunks = []
        for text in batch:
            chunks.extend(splitter.split_text(text))

        st.info(f"Processing batch {i} to {i + len(batch)} with {len(chunks)} chunks")

        if vectordb is None:
            vectordb = Chroma.from_texts(chunks, embedding=embeddings, persist_directory=persist_dir)
        else:
            vectordb.add_texts(chunks)

    return vectordb

# --- Streamlit UI ---
st.title("🔍 JSONL to Chroma Vector DB")
st.write("Upload a `.jsonl` file and convert it into a Chroma vector store.")

uploaded_file = st.file_uploader("Upload your JSONL file", type=["jsonl"])

if uploaded_file:
    with NamedTemporaryFile(delete=False, suffix=".jsonl") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name

    persist_dir = os.path.abspath(CHROMA_DB_DIR)

    if st.button("Create Chroma Vector DB"):
        with st.spinner("Processing..."):
            vectordb = create_vector_db_from_jsonl(tmp_path, persist_dir=persist_dir)
        st.success(f"Chroma DB created and saved to: `{persist_dir}`")
