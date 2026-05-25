import streamlit as st
import json
from datetime import datetime
from langchain_core.documents import Document
from langchain_chroma import Chroma
from dotenv import load_dotenv

from embeddings_config import get_embedding_model
load_dotenv()

st.set_page_config(page_title="HUMAN IN THE LOOP", layout="centered")

LOG_FILE = "conversation_log.txt"

CHROMA_DB_DIR = "New_DB"

# --- Functions ---
def load_conversation(log_file=LOG_FILE):
    with open(log_file, "r") as f:
        return [json.loads(line.strip()) for line in f.readlines()]

def save_to_db(entries, vectordb, in_streamlit=True):
    for entry in entries:
        revision = entry.get("user_revision", "").strip()

        # Prepare content
        if revision:
            text = f"User Question: {entry['user_input']}\nRevised Answer: {revision}"
            source = "user_revision"
            label = "📝 Revised"
            answer_snippet = revision
        else:
            text = f"User Question: {entry['user_input']}\nAnswer: {entry['gpt_response']}"
            source = "gpt_auto_approved"
            label = "✅ Original (accepted)"
            answer_snippet = entry['gpt_response']

        timestamp = datetime.utcnow().isoformat()

        doc = Document(
            page_content=text,
            metadata={
                "source": source,
                "timestamp": timestamp
            }
        )

        vectordb.add_documents([doc])

        # Show feedback
        if in_streamlit:
            st.success(f"{label} saved:\n\n🧍 Q: {entry['user_input']}\n📥 Snippet: {answer_snippet[:500]}...")
        else:
            print(f"\n{label}")
            print(f"🧍 Question: {entry['user_input']}")
            print(f"📥 Saved Answer Snippet: {answer_snippet[:500]}...")

def load_existing_vector_db(persist_dir=CHROMA_DB_DIR):
    embeddings = get_embedding_model()
    vectordb = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
    return vectordb

# --- Streamlit App ---
st.title("🧠 Conversation Review & Save")

conversation = load_conversation()
revised_conversation = []

st.markdown("### 📝 Review and revise GPT responses")

for i, entry in enumerate(conversation):
    st.markdown(f"#### Q{i+1}: {entry['user_input']}")
    st.markdown(f"🤖 GPT Answer:\n> {entry['gpt_response']}")
    
    default_val = entry.get("user_revision", "")
    revision = st.text_area(f"✏️ Enter revision for Q{i+1} (leave empty to accept):", value=default_val, key=f"rev_{i}")
    
    entry["user_revision"] = revision
    revised_conversation.append(entry)

# Save Button
if st.button("✅ Save All to Vector DB"):
    vectordb = load_existing_vector_db()
    save_to_db(revised_conversation, vectordb, in_streamlit=True)
    st.success("✅ All reviewed entries saved to the vector DB.")
