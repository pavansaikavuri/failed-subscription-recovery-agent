# 5-Minute Pitch Video Script
## Razorpay AI Buildathon – Track 3: Failed Subscription Recovery Agent

---

### [0:00 – 0:25] The ₹ Problem as a Hard Number
*(Visual: Camera on presenter or clean slide displaying ₹98,952.00 at risk)*

> "In India's subscription economy, failed recurring payments are rarely just 'insufficient funds.' Between RBI e-mandate guidelines, UPI AutoPay MPIN friction, 24-hour pre-debit notice compliance, and card expiry cycles, Indian merchants lose between 15 to 30 percent of recurring subscription revenue every single month.
>
> In our benchmark dataset of just 40 recurring transactions, over **₹98,952** in merchant revenue was sitting at risk across SaaS, OTT, EdTech, and fitness subscriptions."

---

### [0:25 – 0:45] What We Built
*(Visual: Switch screen to terminal inside `recovery_agent/`)*

> "To solve this, we built an intelligent, bounded Recovery Agent designed specifically for Indian payment rails. It classifies the root cause across 9 India-specific failure reasons, chooses the single optimal bounded intervention, and logs every step in a tamper-evident audit trail."

---

### [0:45 – 2:45] Live Demo: Full 40-Row Batch
*(Visual: Screen recording of terminal. Type and run the command)*

**Command:**
```bash
python pipeline.py --rules-only
```
*(Presenter speaks over terminal output scrolling)*

> "Let’s run our 40-row batch through the pipeline.
>
> Notice how the agent doesn't blindly retry every transaction. 
> - When it sees a `upi_pin_failure`, it triggers `send_upi_pin_nudge` so the customer can enter their MPIN.
> - When it detects a `card_expired`, it routes to `send_card_update_link` instead of retrying a dead card and incurring gateway penalties.
> - For transient `gateway_timeout` or `pre_debit_notice_not_acked`, it safely schedules `retry_now`.
>
> And look at the final summary:
> - **Total Processed**: 40 records
> - **Amount at Risk**: ₹98,952.00
> - **Recovered**: ₹35,150.94
> - **Recovery Rate**: **35.5%** recovered completely hands-free."

---

### [2:45 – 3:45] Live Demo: Failure Safety Modes
*(Visual: Run the demo command for Retry Exhaustion)*

**Command:**
```bash
python pipeline.py --demo-retry-exhaustion
```

> "Real-world fintech systems must fail gracefully. We built three explicit safety modes into this agent.
>
> Here, running `--demo-retry-exhaustion`, the agent identifies transactions that have already reached 4 or more attempts. Instead of spamming the user or wasting merchant fees, it forces a terminal `stop_and_writeoff`.
>
> Similarly, if an off-rail or malformed reason comes in—like an unhandled cheque bounce—running:
```bash
python pipeline.py --demo-out-of-scope
```
> The system logs a `rejected_out_of_scope` audit entry without crashing the pipeline."

---

### [3:45 – 4:30] Architecture & The Hybrid Choice
*(Visual: Display the Mermaid Architecture diagram or clean README overview)*

> "Our architecture is deliberately hybrid:
> 1. **Pydantic v2 Contract**: Strictly enforces data integrity and limits actions to a bounded set (`retry_now`, `send_upi_pin_nudge`, `request_mandate_reissue`, `send_card_update_link`, `escalate_to_human`, `stop_and_writeoff`).
> 2. **Google Gemini Flash + Deterministic Fallback**: Gemini provides deep semantic reasoning on customer notes and merchant history, outputting structured JSON. But if the API faces downtime or rate limits, our zero-downtime rule engine seamlessly takes over.
> 3. **Confidence-Based Human-in-the-Loop**: If confidence drops below 0.60 or a customer disputes unauthorized charges, it automatically flags `escalate_to_human`."

---

### [4:30 – 5:00] Recap & What's Next
*(Visual: Camera back to presenter with final summary stats on screen)*

> "To recap:
> - **₹35,151 recovered** from **₹98,952 at risk**
> - **35.5% recovery rate** across 40 transactions
> - **Zero downtime** with dual LLM + rule-based resilience
>
> With more time, the obvious next step is turning this batch engine into a live FastAPI service that consumes Razorpay webhooks (`payment.failed`, `subscription.halted`) and triggers real WhatsApp interactive messages. We deliberately stayed in batch mode this week so we could prove measured recovery, graceful failure modes, and a clean audit trail first.
>
> Thank you!"
