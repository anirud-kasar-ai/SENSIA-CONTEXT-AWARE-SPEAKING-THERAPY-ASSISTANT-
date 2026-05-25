# Sensia — Quick Start (commands only)

Use **PowerShell** from the project folder. Paths assume the repo is at `d:\Sensia`.

---

## 1. Go to the project

```powershell
Set-Location d:\Sensia
```

---

## 2. Create a virtual environment (once)

```powershell
python -m venv .venv
```

If `python` is not found, try:

```powershell
py -3.11 -m venv .venv
```

(Use **Python 3.11+** if you have it; 3.10 usually works too.)

---

## 3. Activate the virtual environment

**PowerShell** (recommended):

```powershell
Set-Location d:\Sensia
.\.venv\Scripts\Activate.ps1
```

If execution policy blocks activation:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then run the `Activate.ps1` line again.

**Command Prompt (`cmd.exe`)** instead of PowerShell:

```cmd
cd /d d:\Sensia
.venv\Scripts\activate.bat
```

---

## 4. Upgrade pip (optional, recommended)

```powershell
python -m pip install --upgrade pip
```

---

## 5. Install dependencies

```powershell
Set-Location d:\Sensia
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 6. Environment variables

Create `d:\Sensia\.env` with your API key:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

(No command required; use your editor or Notepad.)

---

## 7. Build the vector database (first time, before the therapist)

With the venv **activated**:

```powershell
Set-Location d:\Sensia
.\.venv\Scripts\Activate.ps1
streamlit run create_db.py
```

In the browser: upload `data.jsonl`, click **Create Chroma Vector DB**, wait until it finishes.

---

## 8. Run the AI Therapist

```powershell
Set-Location d:\Sensia
.\.venv\Scripts\Activate.ps1
streamlit run AI_Therapist.py
```

---

## 9. (Optional) Review conversations and save to the vector DB

```powershell
Set-Location d:\Sensia
.\.venv\Scripts\Activate.ps1
streamlit run review.py
```

---

## 10. Deactivate the venv (when done)

```powershell
deactivate
```

---

## Copy-paste session (new terminal, full flow)

After the venv exists and `.env` is set:

```powershell
Set-Location d:\Sensia
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run AI_Therapist.py
```

First-time setup from scratch (no `.venv` yet):

```powershell
Set-Location d:\Sensia
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Then create `.env`, run `streamlit run create_db.py` once, then `streamlit run AI_Therapist.py`.
