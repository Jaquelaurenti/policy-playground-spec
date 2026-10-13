# Requirements — Policy Playground

## Document Information

- **Feature Name**: Policy Playground
- **Version**: 1.1 (revision under review; 1.0 approved)
- **Status**: Requirements 1.0 approved. Design 1.0 and Tasks draft exist. Revision 1.1 (see *Revision History*) awaits approval; no implementation has started.
- **Approval**: Requirements 1.0 approved with all 16 requirements
- **Context source**: AWS Builders League hackathon; SYN credit-policy environment

## Introduction

Policy Playground is an interactive environment that lets a credit policy specialist explore an existing SYN credit policy, formulate and test hypotheses, understand their impact through evidence produced by existing deterministic studies, select a promising change, and prepare a code change plus a pull request that follows existing SYN repository conventions.

The product exists to shorten the end-to-end lead time of a credit policy change. Today, moving from a business hypothesis (for example, raising a minimum-income threshold) to trustworthy evidence requires technical translation, code changes, study execution, and manual iteration, which depends on other people and creates a bottleneck. There is also a discovery gap: investigations tend to cover only the questions people already know to ask, leaving rule interactions, edge cases, and unexpected behavior unexplored.

The guiding principle is **AI proposes, studies prove, humans decide**. AI may interpret intent, structure hypotheses, select tools, propose investigations, analyze study outputs, and explain findings. AI must not invent impact calculations, present unsupported hypotheses as proven, approve policy changes, or modify production policy. The existing studies and the `Motivo de Decisão` dataset remain the source of truth for impact. The specialist is always responsible for deciding whether a change advances. This feature accelerates the existing SYN workflow; it is not a parallel policy platform.

### Feature Summary

An interactive, evidence-based environment for exploring SYN credit policies, testing hypotheses against existing deterministic studies, discovering overlooked scenarios with AI assistance, and preparing a human-reviewed code change and pull request.

### Scope

**In scope (MVP):**

- Consuming and validating a previously consolidated Policy Spec JSON that represents the policy and gathers the relevant variables, rules, and relationships across the four SYN areas. Producing/consolidating that artifact is not the Playground's responsibility in this phase.
- Interactive exploration of an existing SYN policy and its rules, variables, dependencies, and context, based on that consolidated Policy Spec.
- Two entry points: visual exploration, and starting from a business question or hypothesis.
- A hybrid interaction model combining visual controls for known, supported parameters with natural-language interaction for more complex hypotheses.
- Human confirmation of any AI-proposed modification before it is applied to an experimental scenario.
- Hypothesis structuring and identification of the policy rules, variables, and stages needed to evaluate it.
- A reusable impact-analysis capability that executes the relevant policy chain deterministically (respecting the DAG dependency order) and compares the result against `Motivo de Decisão`, with real execution as the preferred MVP path. The current `analise de impacto de estudos` file is a functional reference, not a required integration.
- Baseline-versus-scenario comparison with calculated impacts and traceable evidence.
- AI-assisted investigation of additional scenarios (conflicts, gaps, edge cases, unexpected combinations).
- Turning a relevant finding into an investigable scenario.
- Distinguishing evidence-backed conclusions from unsupported or inconclusive hypotheses, including communicating when available studies cannot answer a question.
- Human review and selection of a promising change.
- **Demonstrative tail (stretch, gated):** generation of code and appropriate tests consistent with existing SYN repository structure and conventions, and opening a pull request for human review. In the MVP this is demonstrated as a labeled, non-submitted change artifact; generating SYN-consistent code and opening a real pull request are delivered only if SYN repository access is confirmed (OQ-9). This aligns with the Working Backwards document, which places implementation (step 9) after the MVP core.
- Keeping the domain-context artifact aligned with relevant policy changes.

**Out of scope (MVP):**

- Generating or consolidating the Policy Spec JSON itself; the Playground consumes and validates a Policy Spec produced upstream, and does not rebuild the whole policy or regenerate its Policy Spec during each investigation.
- Creating new deterministic studies.
- Automatically changing policy in production.
- Any merge, deployment, or authorization to change production policy. Opening a pull request is not approval, merge, or deployment.
- Autonomous code generation without a human-selected, human-reviewed scenario.

**Deliberately deferred to Design (not decided here):**

- The final internal representation of a policy.
- The editor implementation.
- The mechanism that translates a modification into an executable study.
- The agent orchestration architecture.
- Specific AWS services, frameworks, data-access guarantees, and schemas.

### Confirmed decisions vs. open items

The requirements below separate three things explicitly, so Design does not inherit guesses as facts:

- **Confirmed** product decisions are stated as numbered requirements with acceptance criteria.
- **Assumptions** and **Constraints** are collected in their own sections and may be corrected at the approval gate.
- **Open Questions** list decisions that are not yet made; where a requirement depends on one, it is marked. Requirements needing technical feasibility validation are flagged `[Feasibility: Design]`.

### Actors

| Actor | Goal in the Playground |
|------|------------------------|
| **Credit policy specialist** (primary) | Explore a policy, form and test hypotheses without writing code, understand impact with evidence, decide whether a change is promising, and initiate a reviewed code change. |
| **Policy / risk approver** (secondary) | Review traceable evidence to judge whether a proposed change should advance. |
| **Study / data analyst** (secondary) | Benefit from reuse of governed studies and fewer ad-hoc requests. |
| **Decision-engine / SYN engineer** (secondary) | Receive an unambiguous proposed change as a reviewable pull request following SYN conventions. |
| **AI agent capability** (system actor) | Interpret intent, structure hypotheses, select studies/tools, propose investigations, analyze outputs, explain findings — never calculate impact or decide. |

Throughout this document, "the Playground" is the system under specification.

## Requirements

### Requirement 1: Policy exploration

**User Story:** As a credit policy specialist, I want to open an existing SYN policy and see its rules, variables, dependencies, and context, so that I understand what I can investigate before forming a hypothesis.

#### Acceptance Criteria

1. WHEN a specialist selects a policy that is available in the Playground THEN the Playground SHALL present that policy's rules, variables, dependencies, and supporting context sourced from its consolidated Policy Spec (Requirement 16).
2. WHERE a policy element originates in one of the four SYN areas (Extraction, ETL, Hard filters, Final base) THEN the Playground SHALL indicate which area the element belongs to.
3. IF the selected policy cannot be loaded or its context is unavailable THEN the Playground SHALL inform the specialist that the policy cannot be explored and SHALL NOT present partial content as if it were complete.
4. WHEN a specialist views a policy element THEN the Playground SHALL make the originating evidence or definition for that element traceable (viewable or linkable), rather than presenting it without provenance.

- **Priority**: High
- **Dependencies**: Requirement 16 (consolidated Policy Spec). Open Question OQ-1 (which policy). Open Question OQ-18 (mapping of Policy Spec stages to the four SYN areas, for criterion 2). `[Feasibility: Design]` for how policy content is sourced from the Policy Spec.

### Requirement 2: Two entry points into an investigation

**User Story:** As a credit policy specialist, I want to begin either by exploring a policy visually or by stating a business question, so that I can start from whichever matches how I am thinking.

#### Acceptance Criteria

1. WHEN a specialist starts a new investigation THEN the Playground SHALL allow starting from visual policy exploration or from a stated business question/hypothesis.
2. WHEN a specialist starts from a business question THEN the Playground SHALL assist in translating that question into a testable investigation without requiring the specialist to write SQL, Python, or other code.
3. WHEN a specialist starts from visual exploration THEN the Playground SHALL allow the specialist to choose a policy element as the subject of an investigation.
4. THE Playground SHALL support both visual controls for known, supported parameters and natural-language interaction for more complex hypotheses, as a single hybrid interaction model.
5. THE Playground SHALL present testing a specialist's own hypothesis and AI-assisted challenge of the policy as one unified experience, and SHALL NOT require the specialist to choose between them up front.

- **Priority**: High
- **Dependencies**: Requirement 1. Open Question OQ-5 (depth and generality of visual editing — which parameters are visually editable).

### Requirement 3: Hypothesis structuring

**User Story:** As a credit policy specialist, I want the AI to turn my intent into a structured, testable hypothesis, so that I can evaluate it against existing studies.

#### Acceptance Criteria

1. WHEN a specialist expresses an intent in natural language or through visual editing THEN the Playground SHALL produce a structured representation of the hypothesis that names the policy elements involved and the change being tested.
2. WHEN the Playground structures a hypothesis THEN it SHALL identify the existing study or studies needed to evaluate it.
3. IF the specialist's intent is ambiguous or incomplete THEN the Playground SHALL request clarification rather than assuming a specific interpretation.
4. WHEN a hypothesis has been structured THEN the Playground SHALL present it to the specialist for confirmation before it is used to build an experimental scenario.
5. THE Playground SHALL treat a structured hypothesis as a proposal only, and SHALL NOT treat it as evidence or as a proven conclusion.

- **Priority**: High
- **Dependencies**: Open Question OQ-3 (hypothesis-to-study cardinality and the unanswerable case). `[Feasibility: Design]` for study identification.

### Requirement 4: Human confirmation of AI-proposed modifications

**User Story:** As a credit policy specialist, I want to review and confirm any modification the AI proposes before it is applied to a scenario, so that I stay in control of what gets tested.

#### Acceptance Criteria

1. WHEN the AI proposes a modification to a policy rule or parameter THEN the Playground SHALL present that proposed modification to the specialist for explicit confirmation before applying it to an experimental scenario.
2. IF the specialist does not confirm a proposed modification THEN the Playground SHALL NOT apply it to a scenario.
3. WHEN a specialist edits a modification before confirming THEN the Playground SHALL use the specialist's edited version, not the original AI proposal.
4. THE Playground SHALL confine every AI-proposed modification to an experimental scenario and SHALL NOT apply any modification to a production policy.

- **Priority**: High
- **Dependencies**: Requirement 3.

### Requirement 5: Impact analysis via deterministic execution over the policy chain

**User Story:** As a credit policy specialist, I want the impact of an experimental scenario to be calculated by deterministic execution of the relevant policy chain against governed historical data, so that I can trust the numbers without being limited to running one specific existing analysis file.

#### Acceptance Criteria

1. WHEN a confirmed scenario is evaluated THEN the Playground SHALL obtain its impact from deterministic execution over the relevant policy chain, comparing the resulting final base against the historical decisions in `Motivo de Decisão`, and SHALL NOT generate impact numbers by any means other than that deterministic execution.
2. THE Playground SHALL provide impact analysis as a reusable capability driven by the scenario under test, rather than being conceptually limited to directly invoking or transforming the current `analise de impacto de estudos` file; that file is a functional reference for the behavior, not the required execution path.
3. WHEN a scenario is defined from a hypothesis or analysis objective THEN the Playground SHALL identify which policy rules, variables, and stages across the four SYN areas (Extraction, ETL, Hard filters, Final base) are required to answer it, using the consolidated Policy Spec (Requirement 16) as the structured source of context together with the execution capabilities and dependencies identified in Design. Dependency discovery MAY start from the desired result/objective, and SHALL NOT require rebuilding the whole policy or regenerating the Policy Spec during the investigation.
4. WHEN the experimental flow is executed THEN the Playground SHALL respect the valid dependency order of the policy DAG, regardless of how the required dependencies were discovered.
5. THE Playground SHALL treat real deterministic execution as the preferred MVP path for calculating impact.
6. WHEN a deterministic execution produces a result THEN the Playground SHALL associate that result with the scenario and hypothesis that triggered it.
7. IF a deterministic execution fails or does not complete THEN the Playground SHALL report that the impact could not be calculated and SHALL NOT substitute an estimated or AI-generated value.
8. WHERE real deterministic execution proves infeasible for the MVP and recorded or simulated results are used as a fallback THEN the Playground SHALL label those results clearly as recorded/simulated and SHALL NOT represent them as real calculated results.
9. WHERE a scenario is executed THEN the Playground SHALL keep the experimental execution isolated from the production policy, using governed data, so that no experimental run affects production.
10. THE Playground SHALL keep AI reasoning and deterministic calculation separable, so that no AI-produced text is recorded as a calculated impact.

- **Priority**: High
- **Dependencies**: Requirement 3. `[Feasibility: Design]` for how the reusable impact-analysis capability is derived from the current analysis as a functional reference, how required dependencies are discovered from an objective, and how the DAG chain is executed in valid order (the current SYN workflow can recalculate impacts, but Playground integration is not yet built; see OQ-4 and OQ-14).

### Requirement 6: Baseline-versus-scenario comparison

**User Story:** As a credit policy specialist, I want to compare the original policy baseline with my proposed scenario, so that I can see what the change does.

#### Acceptance Criteria

1. WHEN impact results are available for a scenario THEN the Playground SHALL present a comparison between the original baseline and the proposed scenario.
2. WHEN presenting a comparison THEN the Playground SHALL show the calculated impacts together with the related rules and the relevant data context used.
3. THE Playground SHALL provide baseline-versus-scenario comparison as a reusable capability of the impact analysis (Requirement 5), applicable to any scenario it can execute, rather than a one-off tied to a single analysis file.
4. IF baseline results are not available THEN the Playground SHALL indicate that a comparison cannot be shown rather than presenting the scenario alone as if it were a comparison.

- **Priority**: High
- **Dependencies**: Requirement 5.

### Requirement 7: Evidence traceability and the proven/unproven distinction

**User Story:** As a credit policy specialist and as an approver, I want every conclusion to show its evidence and to be clearly marked as proven or unproven, so that I can trust what is backed by studies and treat the rest as a hypothesis.

#### Acceptance Criteria

1. WHEN the Playground presents a finding that is backed by a study result THEN it SHALL make the supporting study and relevant context traceable from that finding.
2. IF a claim lacks sufficient evidence from a study THEN the Playground SHALL label it as an unproven hypothesis and SHALL NOT present it as a proven fact.
3. WHEN available studies cannot answer a question THEN the Playground SHALL communicate that limitation to the specialist.
4. WHERE a finding is displayed THEN the Playground SHALL make its status (evidence-backed or unproven) visible to the specialist.

- **Priority**: High
- **Dependencies**: Open Question OQ-6 (exact proven/unproven definition; whether partial-evidence states exist).

### Requirement 8: AI-assisted discovery of additional scenarios

**User Story:** As a credit policy specialist, I want the AI to surface a manageable set of scenarios I did not think to ask about, so that I can catch rule conflicts, edge cases, and unexpected combinations before production without being overwhelmed.

#### Acceptance Criteria

1. WHEN an investigation is underway THEN the Playground SHALL be able to propose additional investigation scenarios, including potential conflicts, gaps, edge cases, and unexpected rule combinations.
2. WHEN the Playground proposes additional scenarios THEN it SHALL present a bounded set of suggestions for the specialist to review, rather than an open-ended or unbounded stream.
3. WHEN the Playground proposes an additional scenario THEN it SHALL present it as a suggestion for the specialist to accept or reject, not as a decision or a proven result.
4. WHEN a specialist marks a proposed scenario or finding as relevant or irrelevant THEN the Playground SHALL record that assessment.
5. WHEN a scenario changes a parameter THEN the Playground SHALL derive candidate findings deterministically from the Policy Spec, covering at least (a) rules outside the changed path that read the same input variables as the changed rule, and (b) rule branches or lookup entries that become unreachable, or newly reachable, under the scenario compared with the baseline; these candidates SHALL be produced by analysis of the Policy Spec, not by the AI model.
6. WHEN the Playground ranks suggestions THEN it SHALL take into account the relevance assessments previously recorded under criterion 4, so that the specialist's feedback influences which suggestions are shown first.

- **Priority**: Medium
- **Scope note**: The MVP requires a bounded, human-reviewed set of suggestions. It does not require a sophisticated autonomous red-team system or complex configurable investigation limits. Criteria 5 and 6 make discovery reach beyond the changed path (the Working Backwards "o que ninguém perguntou" problem) and make feedback useful for prioritization, as promised in the Working Backwards FAQ, without adding an autonomous loop.
- **Dependencies**: Known concern — excessive/low-value findings.

### Requirement 9: Turning a finding into an investigable scenario

**User Story:** As a credit policy specialist, I want to turn a relevant finding into a scenario I can investigate, so that discovery feeds directly back into testing.

#### Acceptance Criteria

1. WHEN a specialist chooses to investigate a relevant finding THEN the Playground SHALL create an investigable scenario from that finding.
2. WHEN a scenario is created from a finding THEN the Playground SHALL route it through the same confirmation, study-based evaluation, and evidence rules as any other scenario (Requirements 4, 5, 7).
3. THE Playground SHALL require the same human confirmation before evaluating a finding-derived scenario as for any other scenario, and SHALL NOT auto-advance a finding to a committed change. (Open Question OQ-8: whether creating the scenario triggers study execution automatically or on explicit specialist action.)

- **Priority**: Medium
- **Dependencies**: Requirements 7, 8.

### Requirement 10: Human decision on whether a change advances

**User Story:** As a credit policy specialist, I want to accept or reject findings and decide whether a proposed change is promising, so that the human remains the decision-maker.

#### Acceptance Criteria

1. WHEN evidence for a scenario is available THEN the Playground SHALL allow the specialist to accept or reject the associated findings.
2. WHEN a specialist decides a change is promising THEN the Playground SHALL allow the specialist to select that scenario for the code-generation step.
3. THE Playground SHALL NOT advance a change toward code generation unless a specialist has explicitly selected it.
4. THE Playground SHALL NOT interpret acceptance of a finding as approval to change production policy.

- **Priority**: High
- **Dependencies**: Requirements 6, 7.

### Requirement 11: Code and test generation following SYN conventions

**User Story:** As a decision-engine/SYN engineer, I want a selected change to produce code and tests that follow existing SYN repository structure and conventions, so that the output is reviewable and consistent with how SYN works.

#### Acceptance Criteria

1. WHEN a specialist has selected a human-reviewed scenario THEN the Playground SHALL be able to generate corresponding functional policy code and appropriate tests consistent with the existing SYN repository structure and conventions, as an intended end-to-end MVP outcome.
2. THE Playground SHALL generate code only for a scenario that a human has selected, and SHALL NOT generate production-bound code autonomously from an unselected scenario.
3. WHERE existing SYN skills or conventions apply to a stage of this workflow THEN the Playground SHALL reuse them where possible rather than reimplementing equivalent capability.
4. THE Playground SHALL NOT assume that the existing SYN documentation-generation skill already produces functional policy code; functional code generation is a distinct capability subject to feasibility validation. `[Feasibility: Design]`

- **Priority**: Medium — demonstrative tail (stretch). The MVP delivers a labeled, non-submitted change artifact; criterion 1 against the real SYN repository is delivered only if OQ-9 confirms access.
- **Dependencies**: Requirement 10. Open Question OQ-9 (which SYN skills/repos are reachable). `[Feasibility: Design]`

### Requirement 12: Pull request creation for human review

**User Story:** As a decision-engine/SYN engineer and as an approver, I want generated changes to arrive as a pull request for review, so that nothing reaches production without human review.

#### Acceptance Criteria

1. WHEN code and tests have been generated for a selected scenario THEN the Playground SHALL be able to open a pull request against the appropriate SYN repository for human review.
2. THE Playground SHALL treat opening a pull request as a request for review only, and SHALL NOT merge, deploy, or otherwise apply the change to production.
3. IF the pull request cannot be created THEN the Playground SHALL report the failure to the specialist and SHALL NOT indicate that a change was delivered.
4. WHERE a pull request is opened THEN the Playground SHALL make its link to the originating scenario, evidence, and human selection traceable.

- **Priority**: Medium — demonstrative tail (stretch). The MVP presents the pull-request intent and its traceable package without opening a real PR; criterion 1 is delivered only if OQ-9 confirms repository access.
- **Dependencies**: Requirement 11. `[Feasibility: Design]` for repository access and PR mechanics.

### Requirement 13: Domain-context freshness

**User Story:** As a credit policy specialist, I want the domain context used by the Playground to reflect the current policy, so that I am not reasoning over stale explanations.

#### Acceptance Criteria

1. WHERE the Playground relies on a generated domain-context artifact that explains policy concepts, variables, and relationships across the four SYN areas THEN the Playground SHALL aim to use a representation that reflects the current state of the policy it describes.
2. IF the Playground cannot confirm the domain-context artifact is current (for example, relevant policy changes may have occurred since it was produced) THEN the Playground SHALL make that uncertainty visible to the specialist and SHALL NOT silently use the potentially outdated artifact as if it were current.
3. WHERE existing SYN capabilities make regeneration of the domain-context artifact straightforward THEN the Playground MAY refresh it for the MVP; otherwise automated regeneration is a possible future evolution rather than an MVP requirement. `[Feasibility: Design]` for how staleness is detected and whether straightforward regeneration exists.

- **Priority**: Medium
- **Dependencies**: Open Question OQ-2.

### Requirement 14: Traceability and auditability of the investigation

**User Story:** As an approver, I want the chain from hypothesis to decision to be recorded, so that a decision can be audited and justified.

#### Acceptance Criteria

1. WHEN an investigation progresses THEN the Playground SHALL record the hypothesis, the studies used, the supporting data context, the findings, and the human decisions associated with it.
2. WHEN a finding is presented THEN the Playground SHALL make its originating hypothesis and study traceable.
3. WHERE a change is advanced to code generation or a pull request THEN the Playground SHALL make the trace from that change back to its evidence and human selection available.

- **Priority**: High
- **Scope note**: The MVP requires a recorded, traceable investigation history. It does not require building an immutable-audit platform unless a demonstrated need arises.
- **Dependencies**: Requirements 7, 10, 12. Open Question OQ-10 (audit depth for the MVP: recorded in-app history vs. exportable records).

### Requirement 15: Governed data access and privacy

**User Story:** As an approver responsible for compliance, I want data access to be governed and personal data minimized, so that the Playground respects LGPD and existing data governance.

#### Acceptance Criteria

1. WHERE the Playground accesses `Motivo de Decisão` or other credit data THEN it SHALL use only governed data access rather than ungoverned copies.
2. WHEN the Playground interacts with an AI model THEN it SHALL minimize exposure of personal data in those interactions.
3. IF a specialist is not permitted to access a given policy or dataset THEN the Playground SHALL NOT expose that policy or dataset to them. `[Feasibility: Design]` and Open Question OQ-11 (whether access control reuses an existing identity/role mechanism or a simplified demo role set).

- **Priority**: High
- **Scope note**: Governed access and privacy are required, but the MVP does not require building a full enterprise identity platform; reuse of existing governance is preferred and the demo may use a simplified role set.
- **Dependencies**: Known concern — LGPD / governed data.

### Requirement 16: Consuming and validating a consolidated Policy Spec

**User Story:** As a credit policy specialist, I want the Playground to work from a previously consolidated Policy Spec of my policy, so that I can explore and investigate it without the Playground having to rebuild the policy on every investigation.

#### Acceptance Criteria

1. WHEN a policy is made available to the Playground THEN the Playground SHALL consume a previously consolidated Policy Spec (a structured JSON artifact) that represents the policy and gathers the relevant variables, rules, and relationships across the four SYN areas (Extraction, ETL, Hard filters, Final base).
2. WHEN the Playground loads a Policy Spec THEN it SHALL validate the artifact before using it, and IF the Policy Spec is missing, unreadable, or fails validation THEN the Playground SHALL inform the specialist and SHALL NOT proceed with exploration or investigation on an invalid Policy Spec.
3. THE Playground SHALL treat the Policy Spec as an input produced upstream, and SHALL NOT be responsible for generating or consolidating it, nor for rebuilding the whole policy or regenerating the Policy Spec during an investigation.
4. WHEN investigating dependencies for an analysis objective THEN the Playground SHALL use the Policy Spec as the structured source of context (per Requirement 5), alongside the execution capabilities and dependencies identified in Design.
5. THE Playground SHALL NOT treat the Policy Spec alone as a guarantee that a modification is executable; executability depends on the execution capabilities and dependency order identified in Design (Requirement 5).

- **Priority**: High
- **Scope note**: Consuming and validating the Policy Spec is in scope; producing/consolidating it is explicitly out of scope for the MVP. This requirement does not fix the JSON schema, representation, or execution mechanism — those belong to Design.
- **Dependencies**: Requirements 1, 5. Open Question OQ-2, OQ-15. `[Feasibility: Design]` for the Policy Spec's structure, validation, and how it feeds dependency discovery and execution.

## Non-Functional Requirements

These are stated as observable expectations. Concrete thresholds are open questions, not invented here.

### Primary objective — lead-time reduction

1. THE Playground SHALL serve the central objective of reducing the end-to-end lead time for delivering a credit policy change, by letting a specialist move from policy intent to trustworthy evidence (and toward a reviewed change) without the technical-translation handoffs required today. No numeric target is asserted here; how end-to-end lead-time reduction would be measured is Open Question OQ-13.
2. WHEN a hypothesis is submitted and later reaches its first deterministic result THEN the Playground SHALL record both timestamps, so that the in-app hypothesis-to-evidence time can be reported. This in-app measure is an instrumented proxy for the lead-time objective, not the end-to-end business metric.
3. WHEN a specialist records a relevance assessment on a finding (Requirement 8.4) THEN the Playground SHALL make the share of findings marked relevant reportable per session.

### Usability

1. THE Playground SHALL allow a specialist to formulate and test a hypothesis without writing SQL, Python, or other code (restates the central usability goal; see Requirement 2).

### Performance / responsiveness

1. WHEN a specialist runs an investigation THEN the Playground SHALL keep the specialist informed of progress while studies execute. (A specific latency target is Open Question OQ-12 and is not asserted as a requirement.)

### Cost control (FinOps)

1. WHILE a session is active THEN the Playground SHALL control the volume of AI investigations so that inference cost per hypothesis is bounded. (Whether the bound is a concrete number is Open Question OQ-7.)

### Reliability / integrity

1. IF any study, data source, or external capability is unavailable THEN the Playground SHALL communicate the limitation and SHALL NOT fabricate a result to fill the gap (reinforces Requirements 5, 7).

### Security / governance

1. Governed data access and personal-data minimization are specified as Requirement 15.

## Constraints and Assumptions

### Technical Constraints

- Impact calculations must come from deterministic execution over SYN policy logic, compared against the `Motivo de Decisão` dataset; the Playground must not compute impact by other means.
- The current `analise de impacto de estudos` file (which compares the produced final base against `Motivo de Decisão`) is a **functional reference** for the impact-analysis behavior. It is specific and has coupled logic; it is not a required architecture, and the Playground must not be constrained to directly integrating, wrapping, or transforming it into an API. The chosen direction is to extract its concept and functional behavior into a generic, reusable impact-analysis capability.
- The Playground must accelerate the existing SYN workflow and reuse SYN knowledge, conventions, and capabilities where appropriate, rather than introducing a parallel policy platform.
- The existing policy logic is distributed across the four SYN areas (Extraction, ETL, Hard filters, Final base) and can be extracted as needed. Extracting that source logic or producing a structured representation of it does not by itself make interactive modifications executable; the representation and the execution mechanism for modifications are still being designed and must not be assumed to follow automatically from extraction.
- For the MVP, the structured representation of the policy is a **consolidated Policy Spec JSON supplied upstream**, which the Playground consumes and validates (Requirement 16). Its generation/consolidation is out of scope for the Playground in this phase, and its concrete schema is not decided here. The Policy Spec is a source of structured context for reverse dependency discovery; it is not, by itself, proof that a modification is executable.
- Experimental execution must stay isolated from production policy and use governed data; a scenario run must not affect production.
- The internal policy representation, editor, study-translation mechanism, agent orchestration, and specific AWS services/frameworks are intentionally undecided and belong to Design.

### Business Constraints

- Opening a pull request does not constitute approval, merge, deployment, or authorization to change production policy. Production changes must not happen autonomously.
- Creating new deterministic studies is out of scope for the MVP.

### Assumptions (to confirm at the approval gate)

- **A-1**: A specialist can select from one or more existing SYN policies made available for the demo; the specific policy is a configurable demonstration choice, not a hardcoded product rule (ties to OQ-1).
- **A-2**: The success metrics in the Working Backwards proposal are proposed business targets, not acceptance criteria, unless explicitly promoted (ties to OQ-13). They are therefore not encoded as pass/fail criteria in this document.
- **A-3**: "AI challenge" (red-team) behavior and the specialist's own hypothesis testing share one session and one experience (from product context).
- **A-4**: A hybrid interaction model (visual controls for known parameters plus natural language for complex hypotheses) is a confirmed MVP requirement (Requirement 2). What remains open is only the depth and generality of visual editing — which parameters are visually editable (OQ-5).
- **A-5**: Real study execution is the preferred MVP path (Requirement 5). Recorded or simulated results are an acceptable fallback only if real execution proves infeasible, and only when clearly labeled as such.

## Open Questions

Each item is a decision not yet made. Where a requirement depends on one, the requirement references it.

- **OQ-1**: Which policy/policies and which existing studies are in scope for the MVP demo? (Affects R1, R3, A-1.)
- **OQ-2**: The MVP consumes a consolidated Policy Spec JSON supplied upstream (Requirement 16). What is the agreed source/owner and availability of that artifact, and how does its freshness relate to the domain-context artifact (R13)? (Affects R1, R13, R16.)
- **OQ-15**: What minimal structure and validation must the Policy Spec satisfy for the Playground to consume it, and how does it feed reverse dependency discovery (R5) without the Playground regenerating it? The concrete schema is deferred to Design. (Affects R5, R16. `[Feasibility: Design]`.)
- **OQ-3**: Can one hypothesis map to multiple studies, and is "no existing study can answer this" a required explicit outcome? (Affects R3, R7.)
- **OQ-4**: Can real deterministic execution over the policy chain be integrated into the Playground for the MVP (the preferred path), and if not, what is the clearly-labeled recorded/simulated fallback? (Affects R5. `[Feasibility: Design]`.)
- **OQ-14**: How are the required dependencies (rules, variables, stages) of a desired analysis discovered from the objective, and how is the policy DAG executed in valid dependency order? What can be reused from the current `analise de impacto de estudos` file as a functional reference without inheriting its coupled logic? (Affects R5, R6. `[Feasibility: Design]`.)
- **OQ-5**: What is the depth and generality of visual editing for the MVP — which policy parameters are visually editable versus handled through natural language? (Affects R2.)
- **OQ-6**: What exactly qualifies a finding as evidence-backed vs. unproven; are there partial-evidence states? (Affects R7.)
- **OQ-7**: For cost control, is a simple bound on AI investigations per session sufficient for the MVP, and what is that bound? (Affects NFR cost control. R8 already requires only a bounded, human-reviewed suggestion set, so no complex configurable limit is required.)
- **OQ-8**: When a finding becomes a scenario, does study execution start automatically or on explicit specialist action? (Affects R9.)
- **OQ-9**: Which SYN skills and repositories are reachable for structuring, code generation, and PR creation during the hackathon? (Affects R11, R12. `[Feasibility: Design]`.)
- **OQ-10**: What audit depth is required for the MVP — recorded in-app history, or additionally exportable records? (Affects R14. An immutable-audit platform is explicitly not required unless a need is demonstrated.)
- **OQ-11**: Does access control reuse an existing identity/role mechanism or model a simplified role set for the demo? (Affects R15. A full enterprise identity platform is explicitly out of scope. `[Feasibility: Design]`.)
- **OQ-12**: Is there an interactive latency target for an investigation run, or is it out of scope for the MVP? (Affects NFR performance.)
- **OQ-13**: How would end-to-end lead-time reduction (the central objective) be measured for the MVP, and should any Working Backwards success metric become an acceptance criterion? If so, how is each measured? (Affects Primary-objective NFR; no numeric target is invented here.) *Partially addressed in 1.1:* the in-app hypothesis-to-evidence time and the relevant-finding share are instrumented (Primary objective NFR 2–3); the end-to-end business baseline and targets remain open.
- **OQ-18**: How do the stages of a real Policy Spec map to the four SYN areas (Extraction, ETL, Hard filters, Final base) required by R1.2? The synthetic fixture uses different stage names (Extração, Elegibilidade, Oferta, Consolidação) and declares a provisional mapping in `stages[].syn_area`; the real mapping must be confirmed against the real contract. (Affects R1.2, R16.)

## Requirements Needing Feasibility Validation in Design

The following are flagged `[Feasibility: Design]` above and must be validated technically before being committed as achievable:

- Sourcing and representing policy content from SYN, and whether/how interactive modifications become executable (R1, R13) — note that extracting source logic does not by itself make modifications executable.
- Consuming and validating the upstream consolidated Policy Spec, and using it as the structured context for reverse dependency discovery from an analysis objective, without regenerating it per investigation (R16, R5) — reverse dependency discovery remains an objective subject to technical validation.
- Deriving a generic, reusable impact-analysis capability from the current `analise de impacto de estudos` file as a functional reference (not a direct integration), including discovering the required dependencies of a desired analysis from its objective and executing the policy DAG in valid dependency order; and defining a clearly-labeled recorded/simulated fallback if real execution is infeasible (R3, R5, R6).
- Reuse of existing SYN skills, and whether functional policy-code generation (distinct from the existing documentation-generation skill) is achievable within SYN conventions (R11).
- Repository access and pull-request creation mechanics (R12).
- Detecting domain-context staleness, and whether straightforward regeneration exists for the MVP (R13).
- Governed data access and reuse of existing governance/identity, without building a full identity platform (R15).

## Glossary

| Term | Definition |
|------|------------|
| **SYN** | The existing internal credit-policy environment and knowledge base containing policy definitions, studies, and domain knowledge; the environment this feature makes more accessible. |
| **DM-outside-DM ("DM fora do DM")** | A separate initiative holding decision logic extracted from FICO Decision Manager to run outside the FICO DM runtime. Distinct from SYN; not assumed to be the Playground's data source. |
| **Policy** | A credit policy in SYN, organized across four areas: Extraction, ETL, Hard filters, Final base. |
| **`Motivo de Decisão`** | The existing dataset of historical production credit decisions used as the data basis for analyses. |
| **Study** | An existing deterministic SYN computation that produces impact results; the source of truth for impact. |
| **Impact analysis** | The deterministic capability of executing the relevant policy chain for a scenario and comparing the produced final base against `Motivo de Decisão`. In the MVP this is a generic, reusable capability; the current `analise de impacto de estudos` file is its functional reference, not its required implementation. |
| **`analise de impacto de estudos`** | The existing, specific SYN file (with coupled logic) that compares a produced final base against `Motivo de Decisão`. Used as a functional reference for the impact-analysis behavior, not as a mandated integration or architecture. |
| **Policy DAG** | The dependency graph of policy logic across the four SYN areas (Extraction, ETL, Hard filters, Final base); experimental execution must respect its valid dependency order. |
| **Policy Spec (JSON)** | A previously consolidated, structured JSON artifact that represents a policy and gathers its relevant variables, rules, and relationships across the four SYN areas. For the MVP it is supplied upstream; the Playground consumes and validates it but does not generate it. Its concrete schema is deferred to Design. |
| **Hypothesis** | A proposed, testable policy change expressed by the specialist or structured by the AI; a proposal, not evidence. |
| **Scenario** | A confirmed experimental configuration (a hypothesis applied to a policy) that can be evaluated by studies. |
| **Finding** | An AI-surfaced observation or proposed investigation; evidence-backed when supported by a study result, otherwise unproven. |
| **Evidence-backed** | A conclusion supported by a traceable deterministic study result. |
| **Unproven hypothesis** | A claim lacking sufficient study evidence; must not be presented as fact. |
| **The Playground** | The system under specification in this document. |

## Approval Gate

This document is the Requirements phase deliverable. Per the Kiro Specs workflow, Design will not begin until this is explicitly approved. The summary and the decision request are provided in the chat response, not in this file.

**Status: Requirements 1.0 APPROVED** with all 16 requirements. **Revision 1.1 pending approval** (see *Revision History*).

### Design-phase investigation directives (approved scope for Design)

Design must investigate and resolve the following before any `tasks.md` or implementation. These are investigation goals, not pre-decided solutions:

1. **Reuse check** — Inspect the pre-existing `design.md` in this spec folder before deciding whether to build on it, replace it, or discard it; state the decision and why.
2. **Policy Spec JSON provenance** — Investigate the origin, owner/producer, and availability (and freshness) of the upstream consolidated Policy Spec JSON (R16, OQ-2, OQ-15).
3. **Generic impact-analysis capability** — Design the generic, reusable impact-analysis capability using the current `analise de impacto de estudos` file as a functional reference, not a required integration (R5, R6).
4. **Reverse dependency discovery + DAG execution** — Investigate how to discover the dependencies required by a desired analysis (reverse, from the objective) and execute the policy DAG in valid dependency order (R5, OQ-14, OQ-15).
5. **Demonstrative end-to-end feasibility** — Validate the feasibility of the full demonstrative journey, including functional code generation, tests, and a real pull request, without assuming it is already solved (R11, R12, OQ-9).

The design must preserve the separation between functional requirements and implementation decisions, and must not treat integrated execution, reverse dependency discovery, or code/PR generation as technically proven until validated.

## Revision History

| Version | Change | Reason |
|---------|--------|--------|
| 1.0 | Initial approved requirements (R1–R16 + NFRs). | — |
| 1.1 | R11 and R12 reclassified from High to Medium as a demonstrative, gated tail; MVP scope line updated accordingly. | Requirements, Design (§9.2, §14.1), Tasks (C2/C3) and the Working Backwards document disagreed on whether code/PR generation is MVP core. |
| 1.1 | R8 criteria 5–6 added: deterministic candidate findings beyond the changed path, and feedback-aware ranking. | Discovery previously relied only on the model; the Working Backwards FAQ promises that relevance feedback prioritizes later suggestions. |
| 1.1 | Primary-objective NFR 2–3 added: instrumented in-app hypothesis-to-evidence time and relevant-finding share. | Gives the lead-time objective a measurable proxy without inventing a business target (OQ-13 stays open for the end-to-end metric). |
| 1.1 | OQ-18 added: mapping of Policy Spec stages to the four SYN areas. | The fixture stage names differ from the four areas named in R1.2. |
| 1.1 | Status header corrected. | The 1.0 header said no tasks.md would exist before Design approval, while tasks.md already exists. |
