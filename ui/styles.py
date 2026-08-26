"""
UI Styling and CSS Design System.
Provides a clean, simple, minimalist theme with high-contrast typography and clear layout borders.
"""

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

code, pre {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Header Banner - Clean and Simple */
.main-header {
    background: #161922;
    padding: 1.25rem 1.75rem;
    border-radius: 10px;
    border: 1px solid #2d333b;
    margin-bottom: 1.25rem;
}

.main-header h1 {
    font-size: 1.6rem;
    font-weight: 700;
    color: #f3f4f6;
    margin: 0 0 0.35rem 0;
    letter-spacing: -0.01em;
}

.main-header p {
    color: #94a3b8;
    font-size: 0.9rem;
    margin: 0;
    line-height: 1.4;
}

/* Stepper Pill Badges */
.step-card {
    padding: 0.65rem 0.85rem;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    background: #1a1e26;
    border: 1px solid #2d333b;
    color: #94a3b8;
    margin-bottom: 0.5rem;
}

.step-card.pending {
    background: #161922;
    border-color: #2d333b;
    color: #64748b;
}

.step-card.running {
    background: #172554;
    border-color: #3b82f6;
    color: #93c5fd;
}

.step-card.completed {
    background: #064e3b;
    border-color: #10b981;
    color: #6ee7b7;
}

.step-card.warning {
    background: #451a03;
    border-color: #f59e0b;
    color: #fcd34d;
}

.step-card.suppressed {
    background: #450a0a;
    border-color: #ef4444;
    color: #fca5a5;
}

/* Split Screen Columns */
.split-column-box {
    background: #161922;
    border: 1px solid #2d333b;
    border-radius: 10px;
    padding: 1.25rem;
    min-height: 520px;
}

.split-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #f3f4f6;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #2d333b;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* Output Report View - Simple and Clean */
.report-card {
    background: #161922;
    border: 1px solid #2d333b;
    border-radius: 10px;
    padding: 1.5rem;
    color: #f3f4f6;
    line-height: 1.6;
    font-size: 0.93rem;
}

.report-card h3 {
    color: #38bdf8;
    font-size: 1.2rem;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
}

.report-card strong {
    color: #e2e8f0;
}

.report-card a {
    color: #38bdf8;
    text-decoration: underline;
    text-underline-offset: 3px;
}

.report-card a:hover {
    color: #7dd3fc;
}

/* Citation Chip */
.citation-chip {
    display: inline-block;
    background: #1e2430;
    border: 1px solid #334155;
    color: #38bdf8;
    padding: 0.3rem 0.6rem;
    border-radius: 6px;
    font-size: 0.78rem;
    text-decoration: none;
    margin: 0.2rem;
}

.citation-chip:hover {
    background: #283244;
    border-color: #38bdf8;
    color: #7dd3fc;
}

/* Agent Action Log Card */
.agent-action-box {
    background: #1a1e26;
    border: 1px solid #2d333b;
    border-radius: 8px;
    padding: 0.85rem 1rem;
    margin-bottom: 0.75rem;
}

.agent-action-box h5 {
    margin: 0 0 0.25rem 0;
    font-size: 0.88rem;
    color: #e2e8f0;
}

.agent-action-box p {
    margin: 0;
    font-size: 0.8rem;
    color: #94a3b8;
}
</style>
"""
