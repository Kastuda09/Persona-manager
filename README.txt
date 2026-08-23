PERSONA MANAGER - DEPLOYMENT NOTES

What this is:
A working prototype website. Home page, a “Create Post” form (real moment or fictional story), an approval queue, and a history page. It uses the Gemini API to write captions in your learned voice, and falls back to a safe template if the API key is missing or a call fails.

To deploy on Railway:

	1.	Create a new project, choose “Deploy from GitHub repo”.
	2.	Set one environment variable: GEMINI_API_KEY, with your key as the value.
	3.	Railway will detect the Procfile and requirements.txt automatically and deploy.
	4.	Once live, Railway gives you a public URL, that is your website.

Notes:

	•	Right now all drafts are stored in memory, meaning if the app restarts, the queue clears. Fine for testing, will need a real database before real use.
	•	Only one demo profile (“joy”) exists right now. Multi-user accounts, login, and real Instagram/TikTok posting are the next layers to build.
