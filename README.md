# 🗂️ **wdid** — _What Did I Do?_  
_Daily-notes aggregation & AI summarisation_

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/github/license/yourname/wdid.svg)](LICENSE)

## ✨ Features
- 🔍 **Scan** your Obsidian-style daily notes by filename (`11th-apr-2025.md`)  
- 📑 **Concatenate** any date range into a single Markdown report  
- 🤖 **Summarise** the report with a local Ollama LLM (`llama3`, `phi3`, …)  
- 🖥️ **Interactive** `choose` wizard **or** fully scriptable CLI  
- ⚙️ Cross-platform; zero cloud upload – your notes stay local

---

## 🚀 Installation

```bash
# 1. Create venv (optional but recommended)
python -m venv .venv && source .venv/bin/activate

# 2. Install from PyPI
pip install wdid
# or from GitHub
pip install git+https://github.com/yourname/wdid.git

Depends on: Python 3.9 +, Ollama running on localhost:11434.
```
```
⸻

### 🔧 First-time setup

Tell wdid where your daily notes live

```bash
wdid config set-path ~/Notes/Daily
```

Check the setting:

```bash
wdid config show-path
```


⸻

## ⚡ Quick start

Interactive picker

```bash
wdid choose reports/apr-mid.md --summarize
```

This will:
	1.	Pick a month 🗓️
	2.	Select all days or a custom range
	3.	Get reports/apr-mid.md (LLM summary included if --summarize)



Scripted range

```bash
wdid generate reports/q2-week2.md \
  --start 2025-04-14 --end 2025-04-20
```



Summarise later

```bash
wdid summarize reports/q2-week2.md reports/q2-week2-summary.md
```


⸻

## 📚 Command Reference

| Command                                                                                   | Description                             |
|-------------------------------------------------------------------------------------------|-----------------------------------------|
| `wdid config set-path <dir>`                                                              | Save notes directory in config          |
| `wdid choose <out.md> [--summarize]`                                                      | Interactive month/day picker            |
| `wdid generate <out.md> --month YYYY-MM [--start-day N --end-day M]`                      | Generate report for a specific month    |
| `wdid generate <out.md> --start YYYY-MM-DD --end YYYY-MM-DD`                              | Generate report for arbitrary date span |
| `wdid summarize <in.md> <out.md>`                                                         | Summarise an existing report            |

> 💡 Use `-m <model>` to select a different Ollama model (default: `llama3:8b`)



⸻

📜 License

MIT – do whatever you want, just give credit.

⸻

“Stop guessing what you did last week. Let wdid tell you.” 📈

