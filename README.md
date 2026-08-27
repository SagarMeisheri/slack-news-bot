# 🌐 Real-Time News Intelligence & Scenario Analysis Multi-Agent Platform

An autonomous, multi-agent intelligence console built strictly on the **Google Agent Development Kit (ADK)** (`google-adk`, [https://adk.dev/](https://adk.dev/)), powered by **Google Gemini LLMs** and the **Parallel Web Search API**.

The platform ingests breaking headlines, policy circulars, or corporate events, enforces legal & safety red-line triage (including Sub Judice, Defamation under BNS, SEBI/RBI regulations), executes context-driven web searches under a **strict 1-tool-call budget per agent**, captures **live callback-based observability telemetry**, and synthesizes:
1. A date-grounded **Baseline Intelligence Brief**.
2. **10 to 20 high-signal Speculative & Strategic Inquiries** across 8 distinct archetypes with clickable source links.

---

## 🏛️ Architecture & Multi-Agent Workflow

```mermaid
graph TD
    User([User Query / Breaking Statement]) --> SafetyAgent[1. Safety & Triage Agent<br/>Legal Red Lines & Suppression Check]
    
    SafetyAgent -->|Clear / Partial| BreakingAgent[2. Breaking & Fallout Investigator<br/>Stage 1: Ground Truth 0-7d OR<br/>Stage 2: Fallout & Stakeholders 0-7d]
    
    BreakingAgent --> PrecedentAgent[3. Precedent & Counter Investigator<br/>Stage 3: Statutory History OR<br/>Stage 4: Critics OR Stage 5: Analogous]
    
    PrecedentAgent --> CalendarAgent[4. Forward Calendar Investigator<br/>Stage 6: Milestone Dates OR<br/>Stage 7: Primary Site Filings]
    
    CalendarAgent --> SynthesisAgent[5. Synthesis & Neutrality Auditor<br/>Baseline Brief + 8 Archetype Inquiries<br/>Clickable Markdown Source Links]
    
    SynthesisAgent --> StreamlitUI([Interactive Split-Screen Console & Exports])
```

### 5 Specialized ADK Agents

| Agent | ADK Class | Responsibility | Output State Key |
| :--- | :--- | :--- | :--- |
| **1. Safety & Triage** | `LlmAgent` | Evaluates Universal Red Lines (emergencies, personal health, penny stocks, uncharged crimes) & Jurisdiction Legal Red Lines (Sub Judice, Defamation, Communal Harmony, SEBI/RBI). Emits `FULL_SUPPRESSION`, `PARTIAL_SUPPRESSION`, or `NO_SUPPRESSION`. | `safety_result` |
| **2. Breaking & Fallout** | `LlmAgent` | Evaluates context and executes 1 search call (Stage 1: Ground Truth or Stage 2: Immediate Fallout). | `stages_1_2` |
| **3. Precedent & Counter** | `LlmAgent` | Evaluates context and executes 1 search call (Stage 3: Precedent, Stage 4: Critics/Dissent, or Stage 5: Analogous Base Rates). | `stages_3_5` |
| **4. Forward Calendar** | `LlmAgent` | Evaluates context and executes 1 search call (Stage 6: Forward Calendar Dates or Stage 7: Primary Source Gazettes/Circulars). | `stages_6_7` |
| **5. Synthesis & Audit** | `LlmAgent` | Generates date-grounded **Baseline Intelligence Brief** and 10–20 **Speculative Inquiries** with clickable source links, enforcing strict neutrality. | `synthesis_output` |
| **Orchestrator** | `SequentialAgent` | Composes the 5 agents into a deterministic ADK execution pipeline. | `session.state` |

---

## 📊 Where to See Agent Observability & Tracking

The system provides **three transparent ways** to observe and inspect what each agent did, what tools were called, argument parameters, execution latencies, and output states:

### 1. Live Streamlit Split-Screen UI
When you run the Streamlit app (`uv run streamlit run app.py`):
* **Left Screen: 🔍 Live Multi-Agent Workspace**
  * **Agent Execution Cards**: Collapsible sections for each of the 5 agents showing:
    * **Active Status**: `PENDING`, `RUNNING`, `COMPLETED`, `WARNING`, `SUPPRESSED`.
    * **Execution Duration**: Precise agent runtime in seconds (e.g. `• 1.42s`).
    * **Tool Executions (1-Call Budget)**: Exact search tool chosen by the agent, latency in milliseconds, input arguments JSON, and returned result summaries.
    * **LLM Calls**: Model name (`gemini-2.5-flash`), prompt snippets, response previews, and latency.
    * **Output State**: State keys produced and stored in `session.state`.
  * **7-Stage Evidence Explorer**: Inspect search queries sent to Parallel API and raw article excerpts.
  * **ADK Pipeline Telemetry Drawer**: Summary metrics (Total Duration, Tool Calls, Model Calls, Pipeline Health).
  * **💾 Download Observability Trace JSON**: 1-click download of the complete Pydantic telemetry trace file.

* **Right Screen: 📋 Synthesized Intelligence Brief**
  * Date-grounded Baseline Brief.
  * 10–20 Speculative Inquiries with **clickable inline source links** (e.g., `*(source: [Stage 1](https://...))*`).
  * Dedicated **Verified Source References** list.

### 2. Terminal & Console Logs
During pipeline execution, real-time structured logs are emitted to the terminal:
```text
[ADK Observability] ▶ Starting Agent: Safety_Triage_Agent
[ADK Observability] ⏹ Completed Agent: Safety_Triage_Agent
[ADK Observability] ▶ Starting Agent: Breaking_Fallout_Investigator
[ADK Observability] ⚡ Invoking Tool: `search_stage_1_ground_truth` for Agent: `Breaking_Fallout_Investigator` (Call #1)
[ADK Observability] ⏹ Completed Agent: Breaking_Fallout_Investigator
[ADK Guardrail] 🛑 Agent 'Breaking_Fallout_Investigator' exceeded tool call budget (max 1) -> Intercepted
```

### 3. Programmatic Telemetry (`PipelineObservabilityReport`)
Exported in Python or downloaded as JSON:
```json
{
  "pipeline_name": "NewsIntelligencePipeline",
  "topic": "RBI digital lending guidelines",
  "total_duration_seconds": 6.84,
  "total_tool_calls": 3,
  "total_model_calls": 5,
  "agent_traces": {
    "Breaking_Fallout_Investigator": {
      "agent_name": "Breaking_Fallout_Investigator",
      "status": "completed",
      "duration_seconds": 1.85,
      "tool_calls": [
        {
          "tool_name": "search_stage_1_ground_truth",
          "arguments": {"topic": "RBI digital lending", "custom_focus": "NBFC capital norms"},
          "duration_ms": 420.5,
          "result_summary": "RBI issues master direction on digital lending..."
        }
      ]
    }
  }
}
```

---

## 🔍 Contextual Search Framework (1-Call Budget per Agent)

Each search agent evaluates the topic and context to execute **exactly one** high-value search stage:

| Stage | Target Window | Focus / Objective | Primarily Feeds |
| :--- | :--- | :--- | :--- |
| **1. Breaking Ground Truth** | Strict: 0–7 days | Primary event, official filings, regulatory orders, PIB statements | Baseline Brief |
| **2. Immediate Fallout** | Strict: 0–7 days | Market reactions, sectoral impact, official counter-statements | Baseline Brief; Second-Order Impact |
| **3. Precedent & Regulatory** | All-time | Statutory history, tribunal doctrines, policy cycles, root causes | Statutory context; Precedent Base Rates |
| **4. Adversarial / Counter** | 0–30 days | Critics, opposing stakeholders, competitors, dissenting officials | "Why X?" Incentives & Timing |
| **5. Analogous / Cross-Domain** | All-time | Structurally similar cases in other sectors/countries + base rates | "Blindspot / What If" Tail Risks |
| **6. Forward Calendar** | Now–90 days | Concrete near-term dates: hearings, earnings, regulatory deadlines | "What to Watch" Leading Indicators |
| **7. Primary Source Filings** | Conditional | Direct official filings (`site:pib.gov.in`, `site:sebi.gov.in`, `site:rbi.org.in`) | Primary citation grounding |

---

## 🎯 8 Speculative & Strategic Inquiry Archetypes

Each generated inquiry is a single, falsifiable sentence traceable to a search stage:
1. **The "Why X?" (Incentives & Strategic Timing)** — *fed by Stage 4*
2. **The "What It Means" (Second-Order Impact)** — *fed by Stage 2*
3. **The "Who Benefits / Who Loses" (Distributional Impact)** — *fed by Stage 2/4*
4. **The "Blindspot / What If" (Tail Risks & Base Rates)** — *fed by Stage 5*
5. **The "What Doesn't Add Up" (Inconsistency Probe)** — *fed by conflicting stages*
6. **The "What to Watch" (Leading Indicators & Concrete Dates)** — *fed by Stage 6*
7. **The "Precedent Says" (Historical Base-Rate Check)** — *fed by Stage 3/5*
8. **The "Cross-Border / Cross-Sector Spillover"** — *fed by Stage 5*

---

## 🚀 Complete Setup & Installation Guide

### 1. Prerequisites
* **Python**: `>=3.10` (Python 3.11 recommended)
* **Package Manager**: [uv](https://docs.astral.sh/uv/) (Astral's fast Python package manager)
  ```bash
  # Install uv (if not already installed)
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

---

### 2. Clone & Install Dependencies

```bash
git clone <repo-url> spec-agents
cd spec-agents

# Sync all dependencies automatically
uv sync
```

---

### 3. Environment Variables (`.env`)

Copy the example environment file and configure your API keys:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Google Gemini API Key (https://aistudio.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here

# Parallel Web Search API Key (https://parallel.ai/)
PARALLEL_API_KEY=your_parallel_api_key_here

# Slack Bolt Configuration (Socket Mode)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
```

---

### 4. Slack App Setup Guide (1-Click Manifest)

The Slack Bot runs in **Socket Mode** (`AsyncSocketModeHandler`), establishing an outbound WebSocket connection directly to Slack's servers. **No public IP, Cloud Run deployment, or ngrok tunnel is required.**

#### Step 4.1: Create App from Manifest
1. Navigate to **[api.slack.com/apps](https://api.slack.com/apps)** and click **Create New App**.
2. Select **From an app manifest**.
3. Select your Slack Workspace.
4. Copy the entire contents of [`slack_manifest.json`](file:///Users/sagarmeisheri/Apps/spec-agents/slack_manifest.json) into the JSON editor and click **Create**.

#### Step 4.2: Generate `SLACK_APP_TOKEN` (`xapp-...`)
1. In the left sidebar, navigate to **Settings $\rightarrow$ Basic Information**.
2. Scroll down to the **App-level tokens** section and click **Generate Token and Scopes**.
3. Set Token Name to `socket-token`, click **Add Scope**, and check **`connections:write`**.
4. Click **Generate** and copy the token starting with `xapp-...`.
5. Paste it into `.env` as `SLACK_APP_TOKEN`.

#### Step 4.3: Install to Workspace & Get `SLACK_BOT_TOKEN` (`xoxb-...`)
1. In the left sidebar, navigate to **Features $\rightarrow$ OAuth & Permissions**.
2. Scroll to the top and click **Install to Workspace** (or **Reinstall to Workspace**).
3. Authorize the requested permissions (`chat:write`, `chat:write.public`, `app_mentions:read`, `commands`, `im:history`, `im:read`, `im:write`, `channels:join`, `channels:read`, `canvases:write`, `canvases:read`).
4. Copy the **Bot User OAuth Token** starting with `xoxb-...`.
5. Paste it into `.env` as `SLACK_BOT_TOKEN`.

#### Step 4.4: Get `SLACK_SIGNING_SECRET`
1. In the left sidebar, click **Settings $\rightarrow$ Basic Information**.
2. Scroll to **App Credentials** $\rightarrow$ Click **Show** next to **Signing Secret**.
3. Paste it into `.env` as `SLACK_SIGNING_SECRET`.

---

## 🖥️ Running the Applications

### Option A: Start the Slack Bot (Socket Mode)
```bash
uv run python slack_app.py
```
Output:
```text
=================================================================
⚡ ADK News Intelligence Slack Bot running in Socket Mode...
👂 Listening for @bot mentions, DMs, and /news commands...
=================================================================
⚡️ Bolt app is running!
```

#### How to Interact in Slack:
* **Slash Command**: Type `/news <topic>` in any channel (e.g. `/news RBI draft guidelines for digital lending`).
* **Channel Mention**: `@NewsBot Analyze TSMC Taiwan tariff impact on semiconductor supply chains`.
* **Direct Messages (DMs)**: Open a 1-on-1 chat with **NewsBot** and send any query or breaking headline.
* **Auto-Join**: The bot automatically joins public channels. For private channels, invite the bot once: `/invite @NewsBot`.

---

### Option B: Start the Streamlit Web Console
```bash
uv run streamlit run app.py
```
Open **`http://localhost:8501`** in your browser to access the split-screen console with live multi-agent execution cards and telemetry explorer.

---

### Option C: Run the Unit & Integration Test Suite
```bash
PYTHONPATH=. uv run --with pytest pytest tests/ -v
```
Runs all 24 automated tests covering model configs, prompt caching, search tools, 1-call guardrails, storage, and Slack Block Kit builders.


---

```
spec-agents/
├── README.md                      # Documentation & Observability guide
├── pyproject.toml                 # Dependencies & project metadata
├── .env.example                   # Environment variable template
├── slack_manifest.json            # 1-Click Slack App Manifest
├── slack_app.py                   # Slack Bolt Bot (Socket Mode service)
├── slack_ui.py                    # Slack Block Kit formatters & modal views
├── parallel_client.py             # Parallel Search API client (https://api.parallel.ai)
├── app.py                         # Split-Screen Streamlit app with live telemetry
├── prompts/                       # Dedicated Agent Prompts Directory
│   ├── loader.py                  # Pydantic PromptRegistry with caching & formatting
│   ├── safety_agent.md            # Agent 1 prompt (Legal red-lines & suppression)
│   ├── breaking_agent.md          # Agent 2 prompt (Stages 1-2 & 1-call budget)
│   ├── precedent_agent.md         # Agent 3 prompt (Stages 3-5 & 1-call budget)
│   ├── calendar_agent.md          # Agent 4 prompt (Stages 6-7 & 1-call budget)
│   └── synthesis_agent.md         # Agent 5 prompt (Brief & 8 Archetypes)
├── schemas/
│   └── models.py                  # Pydantic domain, findings & observability models
├── observability/
│   └── tracker.py                 # ADK Callback hooks (before/after agent, tool, model)
├── tools/
│   ├── search_tool.py             # Search query generators & citation consolidators
│   └── adk_tools.py               # Google ADK FunctionTools wrapping Parallel API
├── agents/
│   ├── guardrails.py              # Hardcoded tool budget callback guardrails
│   ├── safety_agent.py            # ADK LlmAgent for Safety Triage
│   ├── breaking_agent.py          # ADK LlmAgent for Ground Truth & Fallout
│   ├── precedent_agent.py         # ADK LlmAgent for Precedent & Counter
│   ├── calendar_agent.py          # ADK LlmAgent for Calendar & Primary Sources
│   ├── synthesis_agent.py         # ADK LlmAgent for Synthesis & Neutrality Audit
│   └── pipeline.py                # Assembles ADK SequentialAgent and InMemoryRunner
├── ui/
│   ├── components.py              # Split-screen components, telemetry inspector, citations
│   └── styles.py                  # Clean, minimalist dark styling
└── tests/
    ├── test_pipeline.py           # Offline unit tests for queries & formatting
    ├── test_adk_pipeline.py       # Offline unit tests for ADK agents, prompts & guardrails
    └── test_slack_bot.py          # Offline unit tests for Slack UI & Block Kit
```

