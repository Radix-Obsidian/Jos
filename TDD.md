Vertical Slice TDD Plan (test-first for each slice):

Slice 1 (Lead Scanner): Failing test for scraping leads by keyword -> code -> pass.
Slice 2 (Lead Qualifier): Failing test for scoring lead 0-1 and assigning tier -> code -> pass.
Slice 3 (Outreach Writer): Failing test for personalized email/LinkedIn msg -> code -> pass.
Slice 4 (Message Sender): Failing test for SMTP send + LinkedIn DM -> code -> pass.
Slice 5 (Follow-Up): Failing test for 3-touch follow-up sequence -> code -> pass.
Slice 6 (Closer): Failing test for demo booking + payment link -> code -> pass.
Full Pipeline Test: 10 mock leads through entire pipeline -> 100% success.
