# Business Strategy Study

Use a multi-agent workflow to research a strategic question. The workflow is defined in `./README.md`. Agents must answer the `Strategic Question` after completing the workflow. Agents must also read `Attentions` and `Constraints`. The `Attentions` section lists the business areas the agents must focus on. The `Constraints` section states the boundaries the agents must respect.

The `Research Materials` section lists reference sources the agents can consult to support their conclusions.

## Objectives
- Evaluate and test 3–5 strategic options to halt broadband churn and accelerate MVNO mobile attach rates.
- Assess the operational feasibility and margin trade-offs of fixed-mobile convergence (FMC), AI-driven CX/churn reduction, and LEO satellite partnerships.
- Subject all options to rigorous barrier testing and financial guardrails to deliver a defensible final recommendation.

## Strategic Question
The U.S. connectivity market is hyper-competitive and mature. Subscriber population growth has slowed significantly in recent years, so a new customer for one operator is likely a loss for another. To differentiate and attract customers, operators constantly experiment with technologies (e.g., FWA, LEO satellite, DOCSIS 4.0/FDX), pricing models (e.g., service bundling), service offerings, and subsidies. 

Our company is a major U.S. cable operator (multiple-system operator, MSO) running an MVNO mobile service with low single-digit mobile penetration across a large base of broadband subscribers. We face intense pressure from MNO fiber and fixed wireless access (FWA) expansion.

**Core Decision:** How can our MSO leverage our wireline broadband infrastructure and unpenetrated subscriber base to halt broadband churn and accelerate MVNO mobile attach rates through super-bundling? Within this strategy, the workflow must evaluate:

1. **Wireline Asset Leveraging:** How to package fixed-mobile convergence (FMC) and streaming super-bundles to lock in households (balancing MVNO wholesale cost vs. broadband LTV retention).
2. **AI & Operational Efficiency:** What AI technologies in customer experience (CX), predictive churn analytics, and network operations to adopt to strengthen our position against MNOs.
3. **LEO Satellite Partnerships:** Does partnering with low Earth orbit (LEO) operators (e.g., Starlink or alternatives) provide a viable competitive moat for rural/remote footprint expansion or niche node backhaul, given our $50M CAPEX guardrail?

## Attentions

- **Retention over Gross-Adds:** Prioritize reducing broadband churn via mobile and streaming bundling over fighting expensive price wars for gross subscriber additions.
- **Convergence Margin Trade-offs:** Evaluate the gross margin trade-offs of wholesale MVNO cost structures and ARPU dilution versus the lifetime retention lift on high-margin broadband subscribers.
- **Super-Bundling Economics:** Examine consumer appetite and billing integration mechanics (e.g., Bango-style platforms) for unified billing of broadband, mobile, and streaming services as a retention mechanism.

## Constraints

- **Financial Guardrails:** Strategies must protect EBITDA margins, operate within strict CAPEX/OPEX limits (avoiding speculative multi-year infrastructure builds greater than $50M without clear 24-month payback), and maintain strong cash flow.
- **Regulatory Compliance:** Must respect FCC guidelines on net neutrality, MVNO wholesale access rights, and spectrum/regulatory frameworks.

## Research Materials

### Super-Bundling & FMC Economics
- https://www.streamtvinsider.com/sponsored/super-bundling-revolutionizing-subscriber-economy-consumers-and-telcos
- https://developingtelecoms.com/subscription-bundling-for-telcos-new-report-from-bango.html
- https://bangoinvestor.com/strategy
- https://www.parksassociates.com/blogs/in-the-news/parks-prime-video-has-lowest-churn-rate?page=783
- https://www.analysysmason.com/research/content/articles/fmc-financial-benefits-rdcs0/

### AI & Churn Analytics
- https://www.mckinsey.com/industries/technology-media-and-telecommunications/our-insights/reducing-churn-in-telecom-through-advanced-analytics
- https://www.pwc.com/gx/en/industries/tmt/telecommunications/ai-performance.html

### Alternative Access & Broadcasting Technologies
- https://www.xgnglobal.com/5g-broadcasting-atsc30
- https://www.gsertel.com/5gbroadcast-over-atsc3
- https://s21.q4cdn.com/184289198/files/doc_financials/2026/q2/SpaceX-Reports-Second-Quarter-2026-Results.pdf

### Competitor & Market Benchmarks (2026 Earnings)
- https://www.verizon.com/about/news/verizon-delivers-record-2q26-results
- https://investor.t-mobile.com/static-files/19e97e8f-de79-4c42-98a4-f48182b23d21
- https://about.att.com/story/2026/2q-earnings.html
- https://investors.optimum.com/news-events/press-releases/detail/239/optimum-reports-second-quarter-2026-results
- https://ir.charter.com/news-releases/news-release-details/charter-announces-second-quarter-2026-results
- https://www.cmcsa.com/news-releases/news-release-details/comcast-reports-2nd-quarter-2026-results

## Project Blueprint

Use the `.pi/AGENTS.md` file as a blueprint for development.
