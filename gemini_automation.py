import argparse
import asyncio
import os
from playwright.async_api import async_playwright

class GeminiAutomation:
    """
    A class to interact with Google Gemini programmatically via Playwright.
    Supports a headless mode for invisible execution, and connecting to specific "Gems".
    """
    def __init__(self, headless: bool = True, user_data_dir: str = None):
        """
        :param headless: Run the browser in the background. Note: For the first run, 
                         you must set this to False to authenticate manually.
        :param user_data_dir: Directory to save the browser profile and cookies.
        """
        self.headless = headless
        if user_data_dir is None:
            # Save the session to a folder named 'chrome-user-data' in the active directory
            self.user_data_dir = os.path.join(os.getcwd(), "chrome-user-data")
        else:
            self.user_data_dir = user_data_dir
        
    async def get_response(self, prompt: str = None, prompt_file: str = None, gem_id: str = None) -> str:
        """
        Sends a prompt to Gemini and returns the extracted response text.
        
        :param prompt: The text message to send.
        :param prompt_file: Optional path to a file containing the prompt.
        :param gem_id: Optional ID of a specific Gemini "Gem". This can either be 
                       just the ID from the URL (e.g. "p2e2b3b") or the full URL.
        :return: Response text from Gemini or an error message.
        """
        if prompt_file:
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt = f.read()
            except Exception as e:
                return f"Error reading prompt file: {e}"
                
        if not prompt:
            return "Error: Either 'prompt' or 'prompt_file' must be provided."

        async with async_playwright() as p:
            # When headless is True, we actually use a headful browser but push it off-screen.
            # Google actively blocks real headless modes from loading the Gemini chat UI.
            args = ['--disable-blink-features=AutomationControlled']
            if self.headless:
                args.extend(['--window-position=-32000,-32000', '--window-size=1920,1080'])
            
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False, # Always False to avoid bot detection, we rely on window-position to hide it
                args=args
            )
            
            page = await browser_context.new_page()
            page.set_default_timeout(60000)
            
            # Determine the target URL based on whether a Gem ID is provided
            target_url = "https://gemini.google.com/app"
            if gem_id:
                if gem_id.startswith("http"):
                    target_url = gem_id
                else:
                    target_url = f"https://gemini.google.com/g/{gem_id}"
            
            print(f"[System] Navigating to Gemini ({target_url})...")
            await page.goto(target_url, wait_until="domcontentloaded")
            
            # --- 1. Login Handling ---
            if "accounts.google.com" in page.url or "Sign in" in await page.content():
                if self.headless:
                    msg = "Error: Login required. Please run this script with headless=False to log in manually first."
                    print(f"[!] {msg}")
                    await browser_context.close()
                    return msg
                else:
                    print("\n[!] Please log in to your Google Account in the opened browser window.")
                    print("[!] Waiting for login to complete... (Script will resume once on the Gemini page)")
                    
                    # Wait indefinitely until the URL is no longer Google Accounts
                    await page.wait_for_url("https://gemini.google.com/**", timeout=0)
                    print("[System] Login detected. Proceeding...")

            # --- 2. Input Prompt ---
            chat_input_selector = 'div.ql-editor.textarea'
            
            try:
                await page.wait_for_selector(chat_input_selector, state="visible", timeout=30000)
            except Exception:
                 msg = "Error: Could not find chat input box. The page might not have loaded correctly."
                 print(f"[!] {msg}")
                 await browser_context.close()
                 return msg
                 
            print(f"[System] Typing prompt...")
            await page.fill(chat_input_selector, prompt)
            
            # Submit the prompt
            await page.keyboard.press("Enter")
            
            # --- 3. Wait for the Response ---
            print("[System] Waiting for Gemini to finish generating...")
            await page.wait_for_timeout(2000)  # Short delay to allow the "Stop generating" button to appear
            
            try:
                # Look for the 'Stop generating' button. Wait for it to disappear.
                stop_btn_selector = 'button[aria-label*="Stop generating"]'
                if await page.query_selector(stop_btn_selector):
                     await page.wait_for_selector(stop_btn_selector, state="hidden", timeout=90000)
                else:
                     # Check if it's still responding through network or other means.
                     await page.wait_for_timeout(8000)
            except Exception:
                print("[!] Timeout waiting for generation to finish. Attempting to extract text anyway...")

            # --- 4. Extract Text ---
            response_text = None
            try:
                # Gemini text is often in elements with the class 'message-content' or 'message-text'
                responses = await page.query_selector_all('.message-content, message-content, .message-text, [class*="message-content"]')
                
                if responses:
                    latest_response = responses[-1]
                    response_text = await latest_response.inner_text()
                else:
                    response_text = "Error: Could not locate the response text within expected <message-content> tags."
            except Exception as e:
                response_text = f"Error extracting text: {e}"
                
            await browser_context.close()
            return response_text

async def main():
    parser = argparse.ArgumentParser(description="Interact with Google Gemini via Playwright.")
    parser.add_argument("prompt", nargs="?", default=None, help="The prompt to send to Gemini.")
    parser.add_argument("-f", "--file", default=None, help="Path to a text file containing the prompt.")
    parser.add_argument("-g", "--gem", default=None, help="Optional ID or URL of a specific Gemini 'Gem'.")
    parser.add_argument("--headful", action="store_true", help="Run with the browser visible (required for first-time login).")
    args = parser.parse_args()

    if not args.prompt and not args.file:
        print("Error: You must provide either a text prompt or a file path.")
        print("Usage examples:")
        print("  python gemini_automation.py \"Write a joke about cats\"")
        print("  python gemini_automation.py -f my_prompt.txt")
        print("  python gemini_automation.py --headful \"Log me in\"")
        return

    bot = GeminiAutomation(headless=not args.headful)
    
    response = await bot.get_response(prompt=args.prompt, prompt_file=args.file, gem_id=args.gem)
    
    print("\n" + "="*50)
    print("🤖 GEMINI RESPONSE:")
    print("="*50)
    print(response)
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
