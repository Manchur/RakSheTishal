# Gemini Playwright Automation

A robust, programmatic way to interact with Google's Gemini AI (gemini.google.com) locally via an automated browser—no official API keys required. It handles Gemini's complex UI and circumvents headless browser detection by utilizing off-screen window placement.

## Features
- **Zero API Keys:** Interacts directly with the web interface. 
- **Headless Mode Bypass:** Uses an off-screen window technique to bypass Google's strict anti-bot detection that usually blocks true headless browsers.
- **Persistent Sessions:** Saves your Google Account login state. You only need to log in manually on the very first execution.
- **Support for "Gems":** Easily pass a specific Gem ID (e.g., `p2e2b3b`) or URL to query custom Gems.
- **File Input:** Supports reading lengthy prompts directly from local txt files.

## Prerequisites
This project requires Python 3.7+ and Playwright. 

To install the necessary dependencies, run:
```bash
pip install playwright
playwright install chromium
```

## First-Time Setup
Since this interacts with the actual Gemini web app, you must be logged into a Google account. 

1. Run the script with the `--headful` flag to make the browser visible:
```bash
python gemini_automation.py --headful "Hello Gemini!"
```
2. A Chromium browser window will open and navigate to Gemini. 
3. You will be redirected to the Google log-in page. **Log in manually** to your Google account.
4. Once logged in, the script will detect the URL change, automatically type the test prompt, and save your session cookies to a new local folder (`chrome-user-data`).
5. For all subsequent runs, you can omit the `--headful` flag, and the script will run invisibly in the background.

## Usage

### Running Directly from the CLI
You can run the script directly from your terminal, passing arguments:

**Basic Prompt:**
```bash
python gemini_automation.py "Write a haiku about web scraping"
```

**Read Prompt from File:**
```bash
python gemini_automation.py -f my_prompt.txt
```

**Query a Specific Gem:**
```bash
python gemini_automation.py -g xyz12345 "Analyze this idea"
```

### Importing into Your Own Projects
You can easily import the `GeminiAutomation` class to utilize Gemini in your own Python pipelines.

#### Basic Text Prompt
```python
import asyncio
from gemini_automation import GeminiAutomation

async def main():
    # Initialize the automated session
    bot = GeminiAutomation(headless=True)
    
    # Send a prompt to Gemini
    response = await bot.get_response("Write a haiku about Python.")
    print("Gemini says:", response)

asyncio.run(main())
```

#### Prompting a Specific "Gem"
```python
import asyncio
from gemini_automation import GeminiAutomation

async def main():
    bot = GeminiAutomation(headless=True)
    
    # You can provide the hash ID or the full URL of the Gem
    my_gem = "https://gemini.google.com/g/xyz12345" 
    
    response = await bot.get_response("Hello Gem!", gem_id=my_gem)
    print("Gem responses:", response)

asyncio.run(main())
```

#### Reading Prompts from a File
If you have a very long prompt or prefer to manage prompts externally, you can pass a file path:
```python
import asyncio
from gemini_automation import GeminiAutomation

async def main():
    bot = GeminiAutomation(headless=True)
    
    # The script will read the file and paste its contents into the chat
    response = await bot.get_response(prompt_file="my_daily_report.txt")
    print(response)

asyncio.run(main())
```

## Important Notes
- **UI Changes:** Google frequently updates their DOM and CSS class names. If the script suddenly times out or fails to locate the chat box or the response text, the CSS selectors in `gemini_automation.py` (specifically `chat_input_selector` and the `query_selector_all` for the response) may need to be updated.
- **Rate Limiting:** Because this is interacting via the web UI, sending prompts too fast in a loop may trigger Google's CAPTCHA or temporarily rate-limit your account.
