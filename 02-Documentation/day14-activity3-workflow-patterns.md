# Activity 3 – Workflow and orchestration patterns

A **workflow** follows code paths fixed in advance (the program decides the next step); an **agent** lets the model decide
its next action in a loop. Prefer the simplest pattern that solves the task.

| Pattern | How it works | When it is useful | Advantages | Limitations | Example |
|---|---|---|---|---|---|
| Prompt chaining | A fixed sequence of LLM calls; each step's output feeds the next, with optional programmatic gates between steps | The task splits cleanly into ordered sub-steps | Each step is simpler and testable; gates catch errors early | Adds latency per step; errors can propagate; rigid order | classify → route → draft reply → quality gate (this activity) |
| Routing | A classifier (LLM with structured output, or rules) picks one specialised handler | Distinct input types need different prompts, tools or models | Specialised prompts; cheap model for easy cases; clear separation | A misclassification sends the request down the wrong path; needs a safe fallback | Billing / tech / other router (this activity) |
| Parallelization | Independent sub-tasks run at the same time (sectioning) or the same task runs several times (voting) and results are combined | Sub-tasks do not depend on each other, or several opinions improve reliability | Lower latency; diverse checks | More concurrent calls/cost; results must be merged; rate limits | asyncio.gather of billing and tech handlers (2.0 s → 1.0 s scripted) |
| Orchestrator-workers | A central LLM decides at run time which sub-tasks are needed, delegates them to workers and combines the results | Sub-tasks cannot be predicted in advance | Flexible decomposition | Harder to test and bound; more calls; orchestration errors | A coding assistant deciding which files to change |
| Evaluator-optimizer | One LLM produces, another evaluates against criteria and returns feedback; loop until good enough | Clear evaluation criteria and iterative improvement pays off | Measurably better outputs | Several rounds of cost/latency; needs a stop condition | Draft a customer email, critique it for tone and policy, revise |

## Choosing the simplest adequate pattern

1. Can a single, well-prompted LLM call (with retrieval or examples) do it? Use that.
2. Are the steps known in advance? Use a **workflow**: chaining for ordered steps, routing for different input types,
   parallelization for independent parts. Workflows are predictable, cheaper and easier to test.
3. Only if the number and order of steps truly depend on intermediate results, use an **agent** (orchestrator-workers or
   a tool-calling loop), and then add guardrails: step limits, typed tools, human approval for writes (as in the lab).

The billing/tech/other router is a fixed workflow: its steps are known, so an autonomous agent would only add cost and risk.
