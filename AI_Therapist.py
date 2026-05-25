"""
Legacy Streamlit entry point — replaced by Sensia React UI + FastAPI.

Run the new stack (two terminals from D:\\Sensia):

  .\\run_backend.ps1    # API on http://127.0.0.1:8000
  .\\run_ui.ps1          # UI on http://localhost:5173 (typical Vite port)

Or manually:
  uvicorn api_server:app --host 127.0.0.1 --port 8000 --reload
  cd sensia_ui-main && npm install && npm run dev
"""

if __name__ == "__main__":
    print(__doc__)
