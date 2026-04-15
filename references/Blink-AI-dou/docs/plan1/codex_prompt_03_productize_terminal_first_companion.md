Read README.md, docs/development_guide.md, local companion CLI/runtime files, and operator console docs first.

Then productize Blink-AI around the terminal-first companion path.

What to do:
1. Treat `uv run local-companion` as the hero daily-use path.
2. Improve startup UX for terminal-first use.
3. Ensure the browser console is clearly secondary and optional.
4. Improve `/status`, help, startup summaries, and user guidance for the terminal experience.
5. Add one concise `docs/companion_quickstart.md` focused on terminal-first daily use.
6. Make companion-relevant commands discoverable without reading the whole README.
7. Preserve the browser console as an inspection, approval, and operator surface.

Constraints:
- Do not remove the console.
- Do not add flashy TUI complexity unless it clearly helps.
- Favor reliability, clarity, and speed.

Definition of done:
- A new user can launch Blink-AI in terminal and start using it quickly.
- The terminal path feels intentional, not secondary.
- The browser remains valuable but optional.

Validation:
- uv run pytest
- smoke the local-companion path if possible

At the end, return:
- UX changes made
- docs added or updated
- any remaining rough edges for terminal-first use
