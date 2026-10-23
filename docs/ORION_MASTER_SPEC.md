# ORION — Master Product Vision & Execution Specification

**Project:** ORION (formerly Admin AI)  
**Product category:** AI Executive Intelligence / AI Chief of Staff / Business Intelligence Platform  
**Objective:** Build, validate, and publicly launch a complete, reliable, production-ready AI SaaS platform.

## 1. The Big Vision

ORION is not another chatbot, document-search tool, or basic AI wrapper.

ORION is an AI-powered Chief of Staff designed to help founders, executives, managers, and teams understand what is happening inside their businesses, why it is happening, what deserves attention, and what actions they should consider.

Most businesses already have enormous amounts of information scattered across documents, emails, spreadsheets, CRM systems, team conversations, and financial tools.

The problem is not simply accessing that information. The problem is turning fragmented information into useful, trustworthy decisions.

ORION should solve that problem.

**The ultimate experience:**

A founder creates an ORION account, sets up their company, connects the systems they already use, and ORION begins building an understanding of their business.

The founder should not have to manually explain every customer, project, financial metric, or operational problem.

ORION should gradually build that context from authorized company data.

The founder can then ask questions, request investigations, receive proactive insights, and make decisions with supporting evidence.

The final product should feel like having a knowledgeable, reliable AI Chief of Staff available whenever needed.

ORION must assist human decision-making, not replace executive judgment.

## 2. What the Finished Product Should Feel Like

Imagine a founder visiting the public ORION website.

### First experience: Sign up and create a company

The founder should be able to:

- Visit a polished public landing page.
- Understand ORION's value within seconds.
- Create an account and sign in securely.
- Create a company workspace.
- Enter basic company details.
- Invite teammates where supported.
- See a clear onboarding checklist.
- Explore a realistic demo without exposing private data.

The experience should feel simple and professional, not like configuring a developer tool.

### Second experience: Connect company knowledge

The founder should be able to connect supported systems such as Google Drive, Gmail, Slack, and selected business-data sources.

ORION should clearly distinguish between genuinely connected integrations and unavailable or planned integrations.

For each supported source, ORION should:

- Obtain authorization through an appropriate secure flow.
- Import only data the user is permitted to access.
- Normalize and process the data.
- Preserve source identities and provenance.
- Track import and synchronization status.
- Avoid duplicate logical records.
- Handle updated and deleted source content appropriately.
- Retry recoverable failures.
- Respect provider permissions and access revocation.
- Make it clear what information ORION has access to.

Connections should not require users to manually upload every document.

### Third experience: Ask ORION

A founder opens Ask and types:

"Why is our revenue lower this month?"

ORION should retrieve relevant information from authorized company data, identify the strongest available evidence, and explain the situation in understandable language.

It should distinguish facts from assumptions, cite its sources, and acknowledge missing information.

If the connected data does not support a conclusion, ORION must say so.

Other examples:

- Which customers are at risk of leaving?
- What changed in our sales pipeline?
- Which projects are falling behind?
- What are the biggest unresolved customer complaints?
- What did the team decide about our expansion plans?
- Which business metrics deserve attention?

The answers should be grounded in the company's actual data, not invented business narratives.

### Fourth experience: Investigate a business problem

The founder asks:

"Investigate why customer renewals are declining."

ORION should go beyond a single RAG response.

It should:

1. Understand the investigation objective.
2. Plan relevant analysis steps.
3. Select appropriate available tools.
4. Retrieve documents and structured business data.
5. Analyze trends, relationships, and possible explanations.
6. Evaluate competing hypotheses where evidence permits.
7. Produce evidence-backed findings.
8. Identify uncertainty and missing data.
9. Recommend reasonable next steps.
10. Save the investigation for later review.

A completed investigation should include an executive summary, supporting evidence, findings, limitations, and suggested actions.

Users should be able to inspect why ORION reached a conclusion.

### Fifth experience: Proactive intelligence

ORION should not depend entirely on users asking the right questions.

It should identify meaningful developments from authorized company data.

Examples:

- A significant customer account shows renewal-risk signals.
- Revenue has declined beyond a configured threshold.
- Multiple customers are reporting the same issue.
- A high-priority project has missed important milestones.
- A key operational metric has deteriorated.

ORION should provide useful alerts and executive briefings without overwhelming users with noise.

Each alert should explain what changed, why it matters, and what evidence supports it.

Proactive intelligence must use clear rules, confidence thresholds, and appropriate safeguards.

It must not invent causal explanations.

### Sixth experience: Take informed action

ORION should help users turn findings into next steps.

Depending on implemented integrations and permissions, it may:

- Draft an email.
- Prepare a meeting brief.
- Summarize a customer issue.
- Suggest follow-up tasks.
- Generate an executive report.
- Recommend an investigation.

Any external or consequential action, such as sending a message or modifying business data, should require explicit user approval.

Do not introduce uncontrolled autonomous actions.

## 3. Core Product Capabilities

The final product should include the following major systems.

### A. Authentication and company workspaces

Secure user authentication, workspace creation, membership, role-based authorization where required, and strict tenant isolation.

Every sensitive read and write must enforce the correct user and workspace permissions.

### B. Company onboarding

A guided setup experience that helps users create a workspace, connect data sources, understand ingestion status, and reach their first useful answer quickly.

### C. Data source and connector platform

A reusable ingestion architecture supporting manual uploads and real external integrations.

Initial integration targets:

- Google Drive
- Gmail
- Slack
- At least one relevant structured business-data source, selected based on feasibility and product value

Do not claim an integration works unless it has been implemented and tested against its actual provider behavior.

### D. Knowledge ingestion and retrieval

Support multi-format documents, structured data, parsing, chunking, embeddings, vector retrieval, metadata, provenance, and source lifecycle management.

Maintain workspace isolation throughout ingestion, indexing, retrieval, and citation generation.

### E. Business knowledge model

Represent useful business information such as entities, relationships, metrics, records, documents, and events.

Structured business knowledge should complement semantic retrieval, not be replaced by embeddings alone.

### F. Grounded AI assistant

Provide reliable question answering with citations, useful synthesis, conversation context where appropriate, and clear uncertainty handling.

### G. Agentic investigation engine

Support multi-step investigation planning, tool execution, evidence gathering, claim validation, investigation history, and interpretable findings.

### H. Proactive intelligence engine

Support meaningful business-signal detection, alerts, investigation suggestions, and executive briefings.

### I. Executive dashboard

Provide a coherent overview of workspace health, connected sources, investigations, important signals, and recent activity.

Do not fill the dashboard with fabricated metrics.

### J. Reliability and observability

Provide background job processing, failure recovery, structured logging, operational health checks, and appropriate monitoring.

### K. Security and privacy

Protect credentials and customer data, enforce authorization, prevent cross-tenant leakage, support revocation and deletion workflows, and defend against prompt injection from retrieved content.

### L. Public deployment

Provide a public landing page, working application, secure deployment configuration, HTTPS, and documented setup and operational procedures.

## 4. Existing Technology and Architecture

ORION already has substantial implementation history.

Current known stack:

- Python and FastAPI
- PostgreSQL and pgvector
- SQLAlchemy async
- Alembic
- Redis
- Celery
- MinIO
- Next.js
- React
- TypeScript
- Tailwind CSS
- OpenAI APIs
- Docker Compose

Preserve this architecture unless there is a compelling, demonstrated reason to change a component.

Do not rewrite working subsystems simply to introduce a preferred framework.

Before making changes, inspect the actual repository, current Git state, database migrations, services, tests, and frontend.

The repository is the source of truth for what currently exists.

Historical notes are context, not proof of completion.

## 5. Engineering Quality Requirements

ORION must be built as a serious software product.

### Backend

- Clear separation of API, domain logic, ingestion, retrieval, and orchestration.
- Consistent error handling.
- Secure authorization checks.
- Reliable background processing.
- Database constraints protecting critical invariants.
- Safe and reversible migrations where practical.

### AI engineering

- Grounded answers.
- Evidence provenance.
- Structured tool calls.
- Bounded agent execution.
- Explicit uncertainty.
- Evaluation datasets and measurable quality.
- Prompt-injection resistance.
- No fabricated evidence or tool results.

### Data integrity

- Idempotent source imports.
- Stable source-item identities.
- Incremental synchronization.
- Correct handling of updates and deletions.
- Safe retry behavior.
- Workspace-scoped persistence and retrieval.

### Frontend

- Consistent visual design.
- Responsive layouts.
- Clear loading, empty, success, and error states.
- Accessible interactions.
- Honest representation of integration status.
- Polished onboarding and navigation.

### Security

- Authentication and authorization.
- Tenant isolation.
- Secure credential storage.
- Appropriate OAuth scopes.
- Input validation.
- Secret management.
- Rate limiting where appropriate.
- No credentials committed to Git.
- No destructive operations without approval.

### Testing

- Unit tests.
- API and integration tests.
- Migration tests.
- Workspace-isolation tests.
- Ingestion and synchronization tests.
- Retrieval and grounded-answer evaluation.
- Investigation workflow tests.
- End-to-end product acceptance.

A feature is not complete simply because its code compiles.

## 6. What Publicly Launched ORION Should Include

The final launch should have:

- A professional public landing page.
- Secure signup and login.
- Working company onboarding.
- A polished application interface.
- Real, clearly documented supported integrations.
- Reliable company data ingestion and synchronization.
- Grounded Ask functionality.
- Evidence-backed Investigate functionality.
- Proactive business alerts and briefings.
- A coherent dashboard.
- Strong tenant isolation.
- Operational monitoring and error handling.
- A public demo or safe demonstration environment.
- Deployment documentation.
- A comprehensive GitHub README.
- Architecture diagrams.
- Automated test results.
- Measured evaluation results.
- A recorded product demonstration.
- Honest documentation of remaining limitations.

Public accessibility is not the same as production readiness. ORION should only be described as production-ready once its security, reliability, and operational requirements have been verified.

## 7. What Success Looks Like

A successful ORION launch should allow a new user to complete this journey:

1. Open ORION's public website.
2. Sign up securely.
3. Create a company workspace.
4. Connect an actual supported data source.
5. Watch ORION import and index authorized company information.
6. Ask a business question and receive a grounded, cited answer.
7. Launch a multi-step investigation.
8. Review findings and supporting evidence.
9. Receive a meaningful proactive insight.
10. Return later and find the workspace, data, history, and source synchronization working reliably.

The user should not need to run terminal commands or manually modify database records.

The experience must work beyond a preconfigured developer demo.

## 8. Execution Strategy for Claude Code

You are responsible for helping plan and implement the complete product vision.

Do not interpret this specification as permission to immediately rewrite the repository or implement everything in one enormous change.

### Stage 1 — Repository audit

Inspect the existing codebase and identify:

- Implemented features.
- Partially implemented features.
- Missing capabilities.
- Broken workflows.
- Technical debt.
- Security risks.
- Deployment blockers.
- Existing test coverage.
- Reusable architecture.

### Stage 2 — Gap analysis

Compare the actual implementation with the complete product vision.

Classify every requirement as:

- Complete and verified.
- Implemented but unverified.
- Partially implemented.
- Missing.
- Blocked by external dependencies.

Provide concrete evidence for each classification.

### Stage 3 — Master implementation roadmap

Build a dependency-aware roadmap covering all missing requirements.

For each milestone, specify:

- Objective.
- Scope.
- Existing components to reuse.
- Files or modules likely to change.
- Database migration requirements.
- Security implications.
- Automated tests.
- Manual acceptance criteria.
- External credentials or provider setup required.
- Estimated effort.
- Definition of done.

Prioritize foundational dependencies before dependent features.

### Stage 4 — Implementation

Implement approved milestones in sequence.

Preserve existing working functionality.

Run focused tests throughout development.

Do not introduce unrelated features or expand scope without explanation.

### Stage 5 — Integration and evaluation

Validate complete user journeys, not just individual modules.

Measure:

- Retrieval relevance.
- Grounded-answer quality.
- Citation correctness.
- Investigation success.
- Cross-workspace isolation.
- Ingestion and synchronization reliability.
- Relevant performance and operational metrics.

Do not fabricate benchmark numbers.

### Stage 6 — Production hardening

Complete the necessary authentication, authorization, security, reliability, deployment, and observability work.

### Stage 7 — Public launch readiness

Prepare the deployed application, documentation, architecture diagrams, demo, evaluation report, and final release checklist.

Only declare ORION complete when the agreed acceptance criteria are satisfied.

## 9. Operating Rules

- Never destroy existing data or Docker volumes without explicit approval.
- Never reset or overwrite Git history without explicit approval.
- Never silently modify existing migration history.
- Never expose secrets or customer information.
- Never purchase services or incur costs without approval.
- Never claim an external integration works based solely on mocks.
- Never declare tests passed without executing them.
- Never silently skip unfinished requirements.
- Never commit, push, merge, or deploy without approval.
- Never substitute a visual mockup for working functionality.
- Always explain architectural decisions and important tradeoffs.
- Keep the owner informed of progress and blockers.
- Work autonomously within approved milestones, but stop at security-sensitive or irreversible actions.

## 10. Final Instruction

Treat ORION as a serious AI product with genuine startup potential and as a flagship AI engineering portfolio project.

Optimize for correctness, maintainability, security, usefulness, and demonstrable engineering depth.

The owner wants the complete vision implemented, not an arbitrarily reduced MVP.

You may organize the work into milestones for safety and efficiency, but do not silently discard major product requirements or rename them as future versions.

At the same time, be realistic about effort, API access, provider approvals, cloud infrastructure, and verification.

Your immediate task is to understand the repository and produce the complete execution roadmap.

Do not modify code until the repository audit and implementation roadmap have been reviewed and approved.

Lets build this beast
