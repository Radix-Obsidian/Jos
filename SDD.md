Architecture: Joy V1 Sales Rep

Inference: MLX with local LLM on Apple Silicon
Orchestration: LangGraph state machine with conditional edges
Scraping: requests + BeautifulSoup4
Email: SMTP (smtplib)
LinkedIn: Placeholder API client (manual for V1)
Scheduling: Calendly API for demo booking
Payments: Stripe payment links for self-serve

Data Flow:
Web Scrape -> Lead List -> LLM Qualifier -> Score/Tier ->
  [qualified] -> LLM Outreach Writer -> Message Sender ->
  [no response] -> Follow-Up Queue -> Re-send ->
  [interested] -> Closer (book demo or payment link)

State: SalesState TypedDict flows through all LangGraph nodes
Ledger: Console + file log of every action with timestamps
Storage: Local JSON files for lead database and follow-up queue
