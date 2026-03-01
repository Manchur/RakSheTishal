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

    def _cleanup_zombie_processes(self):
        """Kills any existing Chrome processes locked to our user data dir to prevent hangs."""
        import subprocess
        import platform
        if platform.system() == "Windows":
            try:
                # Use powershell to find and kill chrome processes matching the user_data_dir path
                cmd = "Get-CimInstance Win32_Process -Filter \\\"Name='chrome.exe'\\\" | Where-Object {$_.CommandLine -match 'chrome-user-data'} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
                subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

    async def start_session(self, gem_id: str = None) -> bool:
        """Starts the browser session and navigates to the AI interface."""
        self._cleanup_zombie_processes()
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

    async def send_message(self, prompt: str, file_path: str = None) -> str:
        """Sends a message in the active session, optionally with a file, and returns the response text."""
        if not self.page:
            return "Error: Session not started."
            
        chat_input_selector = 'div.ql-editor, rich-textarea [contenteditable="true"], [data-test-id="chat-input"], [aria-label="Message Gemini"]'
        
        try:
            # wait_for_selector on a comma-separated list will return when ANY of them is visible
            await self.page.wait_for_selector(chat_input_selector, state="visible", timeout=30000)
        except Exception:
             return "Error: Could not find chat input box. The page might not have loaded correctly."
             
        print(f"[System] Passing message to Igor and Nabu...")
        
        # Use insert_text to instantly paste the prompt (bypasses slow per-character typing)
        await self.page.locator(chat_input_selector).first.click()
        await self.page.keyboard.insert_text(prompt)
        
        # Submit the prompt
        await self.page.keyboard.press("Enter")
        
        # --- 3 & 4. Wait for the Response and Extract Text ---
        print("[System] Waiting for Igor and Nabu to reply...")
        
        # We will poll the text content of the latest model-response.
        # Once it stops changing for 3 seconds, we assume generation is complete.
        response_text = ""
        stable_count = 0
        
        # Define JS script to safely locate the LAST top-level response string without nested child interference
        js_extractor = """() => {
            let responses = document.querySelectorAll('model-response, message-content, [class*="message-content"], [data-test-id="model-response"]');
            let topLevel = Array.from(responses).filter(el => {
                let parent = el.parentElement;
                while(parent) {
                    if (['model-response', 'message-content'].includes(parent.tagName.toLowerCase()) || 
                        (parent.className && typeof parent.className === 'string' && parent.className.includes('message-content'))) {
                        return false; // It's a nested child paragraph, skip!
                    }
                    parent = parent.parentElement;
                }
                return true;
            });
            if (topLevel.length > 0) {
                return topLevel[topLevel.length - 1].innerText;
            }
            return "";
        }"""
        
        for _ in range(180): # Max wait 180 seconds
            await self.page.wait_for_timeout(1000)
            
            try:
                current_text = await self.page.evaluate(js_extractor)
            except Exception as e:
                print(f"[!] Error executing JS extraction: {e}")
                current_text = ""
                
            if current_text and len(current_text.strip()) > 10:
                if current_text == response_text:
                    stable_count += 1
                    if stable_count >= 3:
                        # Text hasn't changed in 3 seconds. It's done!
                        print("[System] Received complete response.")
                        break
                else:
                    stable_count = 0
                    response_text = current_text
            else:
                # Still waiting for response to appear or grow
                pass
                
        if not response_text or not response_text.strip():
            response_text = "Error: Could not locate the response text within expected DOM tags."
            # Dump the DOM so we can inspect what elements Google is actually using right now
            try:
                html_content = await self.page.content()
                with open("dom_dump.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("[!] Saved page source to dom_dump.html for debugging.")
            except Exception as dump_e:
                print(f"Failed to dump DOM: {dump_e}")
                
        # Clean up Gemini's new custom Gem UI header that gets prepended to the text
        if response_text:
            lines = response_text.strip().split('\n')
            
            # The header can span many lines now (name, "Gem", "data analysis", "query complete", then "said")
            # We look for the line containing "אמר" (said) or "said" within the first 10 lines
            header_end_idx = -1
            for i in range(min(10, len(lines))):
                line_lower = lines[i].lower().strip()
                # Match if line contains "אמר" (said in Hebrew) — this is the definitive end-of-header marker
                if 'אמר' in line_lower or ('said' in line_lower and ('igor' in line_lower or 'nabu' in line_lower or 'gemini' in line_lower)):
                    header_end_idx = i
                    break
            
            if header_end_idx != -1:
                # Discard the header lines and any immediate blank lines following it
                response_text = '\n'.join(lines[header_end_idx + 1:]).strip()
            
        return response_text

    async def new_chat(self) -> bool:
        """Clicks the 'New Chat' button in the Gemini UI to clear context."""
        if not self.page:
            return False
            
        print("[System] Attempting to start a new chat session...")
        try:
            # We look for the new chat button using its common data attributes or href
            # Works across languages since it's structural
            clicked = await self.page.evaluate("""() => {
                let newChatBtn = document.querySelector('a[href="/app"], a[data-test-id="new-chat"]');
                if (newChatBtn) {
                    newChatBtn.click();
                    return true;
                }
                return false;
            }""")
            
            if clicked:
                await self.page.wait_for_timeout(2000) # Wait for UI to reset
                return True
            else:
                # Fallback: Just navigate to /app which forces a new chat
                await self.page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                await self.page.wait_for_timeout(2000)
                return True
        except Exception as e:
            print(f"[!] Error starting new chat: {e}")
            return False

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
            
        response_text = await self.send_message(prompt, file_path=None)
        
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
