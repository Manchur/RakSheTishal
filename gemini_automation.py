import argparse
import asyncio
import os
import sys
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
            
        self.playwright = None
        self.browser_context = None
        self.page = None

    async def start_session(self, gem_id: str = None) -> bool:
        """Starts the browser session and navigates to the AI interface."""
        self.playwright = await async_playwright().start()
        
        args = ['--disable-blink-features=AutomationControlled']
        if self.headless:
            args.extend(['--window-position=-32000,-32000', '--window-size=1920,1080'])
        
        self.browser_context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=False, # Always False to avoid bot detection, we rely on window-position to hide it
            args=args
        )
        
        self.page = await self.browser_context.new_page()
        self.page.set_default_timeout(60000)
        
        # Determine the target URL based on whether a Gem ID is provided
        target_url = "https://gemini.google.com/app"
        if gem_id:
            if gem_id.startswith("http"):
                target_url = gem_id
            else:
                target_url = f"https://gemini.google.com/g/{gem_id}"
        
        print(f"[System] Waking up Igor and Nabu ...")
        await self.page.goto(target_url, wait_until="domcontentloaded")
        
        # --- 1. Login Handling ---
        if "accounts.google.com" in self.page.url or "Sign in" in await self.page.content():
            if self.headless:
                msg = "Error: Login required. Please run this script with headless=False to log in manually first."
                print(f"[!] {msg}")
                await self.close_session()
                return False
            else:
                print("\n[!] Please log in to your Google Account in the opened browser window.")
                print("[!] Waiting for login to complete... (Script will resume once on the chat page)")
                
                # Wait indefinitely until the URL is no longer Google Accounts
                await self.page.wait_for_url("https://gemini.google.com/**", timeout=0)
                print("[System] Login detected. Proceeding...")
        return True

    async def send_message(self, prompt: str) -> str:
        """Sends a message in the active session and returns the extracted response text."""
        if not self.page:
            return "Error: Session not started."
            
        chat_input_selector = 'div.ql-editor.textarea'
        
        try:
            await self.page.wait_for_selector(chat_input_selector, state="visible", timeout=30000)
        except Exception:
             return "Error: Could not find chat input box. The page might not have loaded correctly."
             
        print(f"[System] Passing message to Igor and Nabu...")
        # Fill clears existing text implicitly
        await self.page.fill(chat_input_selector, prompt)
        
        # Submit the prompt
        await self.page.keyboard.press("Enter")
        
        # --- 3. Wait for the Response ---
        print("[System] Waiting for Igor and Nabu to reply...")
        await self.page.wait_for_timeout(2000)  # Short delay to allow the "Stop generating" button to appear
        
        try:
            # Look for the 'Stop generating' button. Wait for it to disappear.
            stop_btn_selector = 'button[aria-label*="Stop generating"]'
            if await self.page.query_selector(stop_btn_selector):
                 await self.page.wait_for_selector(stop_btn_selector, state="hidden", timeout=90000)
            else:
                 # Check if it's still responding through network or other means.
                 await self.page.wait_for_timeout(8000)
        except Exception:
            print("[!] Timeout waiting for reply. Attempting to extract text anyway...")

        # --- 4. Extract Text ---
        response_text = None
        try:
            # Gemini text is often in elements with the class 'message-content' or 'message-text'
            responses = await self.page.query_selector_all('.message-content, message-content, .message-text, [class*="message-content"]')
            
            if responses:
                latest_response = responses[-1]
                response_text = await latest_response.inner_text()
            else:
                response_text = "Error: Could not locate the response text within expected <message-content> tags."
        except Exception as e:
            response_text = f"Error extracting text: {e}"
            
        return response_text

    async def close_session(self):
        """Closes the browser session."""
        if self.browser_context:
            await self.browser_context.close()
            self.browser_context = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
            self.page = None

    async def get_response(self, prompt: str = None, prompt_file: str = None, gem_id: str = None) -> str:
        """
        Original single-shot method.
        Sends a prompt to the AI and returns the extracted response text.
        """
        if prompt_file:
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt = f.read()
            except Exception as e:
                return f"Error reading prompt file: {e}"
                
        if not prompt:
            return "Error: Either 'prompt' or 'prompt_file' must be provided."

        success = await self.start_session(gem_id=gem_id)
        if not success:
            return "Failed to start session."
            
        response_text = await self.send_message(prompt)
        
        await self.close_session()
        return response_text

async def main():
    parser = argparse.ArgumentParser(description="Interact with the Experts via Playwright.")
    parser.add_argument("prompt", nargs="?", default=None, help="The prompt to send.")
    parser.add_argument("-f", "--file", default=None, help="Path to a text file containing the prompt.")
    parser.add_argument("-g", "--gem", default=None, help="Optional ID or URL of a specific 'Gem'.")
    parser.add_argument("--headful", action="store_true", help="Run with the browser visible (required for first-time login).")
    parser.add_argument("-c", "--continuous", action="store_true", help="Start a continuous chat session.")
    args = parser.parse_args()

    # Determine the initial prompt if provided
    initial_prompt = args.prompt
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                initial_prompt = f.read()
        except Exception as e:
            print(f"Error reading prompt file: {e}")
            return

    if not args.continuous and not initial_prompt:
        print("Error: You must provide either a text prompt, a file path, or use -c flag for continuous chat.")
        print("Usage examples:")
        print("  python gemini_automation.py \"Write a joke about cats\"")
        print("  python gemini_automation.py -f my_prompt.txt")
        print("  python gemini_automation.py --headful \"Log me in\"")
        print("  python gemini_automation.py -c")
        return

    bot = GeminiAutomation(headless=not args.headful)
    
    if args.continuous:
        print("[System] Starting continuous chat session with Igor and Nabu...")
        success = await bot.start_session(gem_id=args.gem)
        if not success:
            return
            
        prompt_text = initial_prompt
        try:
            while True:
                if not prompt_text:
                    prompt_text = await asyncio.to_thread(input, "\nYou: ")
                    
                if prompt_text.strip().lower() in ['exit', 'quit']:
                    print("Ending chat session.")
                    break
                    
                if prompt_text.strip():
                    response = await bot.send_message(prompt_text)
                    print("\n" + "="*50)
                    print("🧠 IGOR AND NABU, THE EXPERTS:")
                    print("="*50)
                    print(response)
                    print("="*50 + "\n")
                    
                prompt_text = None
        except (KeyboardInterrupt, EOFError):
            print("\nEnding chat session.")
        finally:
            await bot.close_session()
    else:
        # Existing single-shot behavior
        response = await bot.get_response(prompt=initial_prompt, gem_id=args.gem)
        
        print("\n" + "="*50)
        print("🧠 IGOR AND NABU, THE EXPERTS:")
        print("="*50)
        print(response)
        print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
